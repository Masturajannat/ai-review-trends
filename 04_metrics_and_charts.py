"""
STEP 4 - Confusion matrix, precision / recall / F1, ROC and other charts.

Reads  : analysis/labeled_set_scored.csv     (made by 03_score_labeled_set.py)
Writes : analysis/ folder
           table_5_metrics.csv                 TP FP TN FN, accuracy, precision, recall, specificity, F1, AUCs + 95% CIs
           table_6_threshold_sweep.csv         precision / recall / F1 at many thresholds
           table_7_metrics_by_length.csv       recall and specificity by review length
           fig_5_confusion_matrices.png
           fig_6_metrics_bars.png
           fig_7_roc_curve.png
           fig_8_precision_recall_curve.png
           fig_9_threshold_sweep.png
           fig_10_score_distributions.png
           fig_11_by_length.png

Run:  python 04_metrics_and_charts.py            (needs only pandas, numpy, matplotlib; no internet)
      python 04_metrics_and_charts.py --threshold 0.5     (0.5 matches your original run)

Definitions (positive = AI):
  TP = AI review flagged as AI        FN = AI review missed (called human)
  TN = human review called human      FP = human review wrongly flagged as AI
  precision   = TP / (TP + FP)   of the reviews flagged, how many really were AI
  recall      = TP / (TP + FN)   of the AI reviews, how many were caught
  specificity = TN / (TN + FP)   of the human reviews, how many were left alone
  F1          = 2PR / (P + R)
The labeled set is 50% AI / 50% human, so precision here is higher than it would be on real data,
where AI reviews are a minority. Use recall and specificity (which do not depend on the mix) as the headline numbers.
"""
import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

BASE = Path(__file__).resolve().parent
OUT = BASE / "analysis"
IN_FILE = OUT / "labeled_set_scored.csv"

ap = argparse.ArgumentParser()
ap.add_argument("--threshold", type=float, default=0.5)
ap.add_argument("--boot", type=int, default=2000)
args = ap.parse_args()
THR = args.threshold

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
})

df = pd.read_csv(IN_FILE, encoding="utf-8-sig")
df = df.dropna(subset=["roberta_ai_prob"]).copy()
GROUPS = [("All reviews", df),
          ("Bengali/Banglish (translated)", df[df.path == "translated"]),
          ("Original English", df[df.path == "english"])]
GROUPS = [(n, g) for n, g in GROUPS if len(g) and g.label.nunique() == 2]
GCOL = [C1, C2, C3]


# ---------------------------------------------------------------- metric helpers
def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def confusion(y, p, thr):
    pred = p >= thr
    tp = int(((y == 1) & pred).sum()); fn = int(((y == 1) & ~pred).sum())
    fp = int(((y == 0) & pred).sum()); tn = int(((y == 0) & ~pred).sum())
    return tp, fp, tn, fn


def prf(tp, fp, tn, fn):
    prec = tp / (tp + fp) if tp + fp else np.nan
    rec = tp / (tp + fn) if tp + fn else np.nan
    spec = tn / (tn + fp) if tn + fp else np.nan
    f1 = 2 * prec * rec / (prec + rec) if prec == prec and rec == rec and (prec + rec) > 0 else np.nan
    acc = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) else np.nan
    return dict(accuracy=acc, precision=prec, recall=rec, specificity=spec, f1=f1)


def roc_auc(y, p):
    """AUC = probability a random AI review scores above a random human one (ties count half)."""
    r = pd.Series(p).rank().to_numpy()
    n1, n0 = int((y == 1).sum()), int((y == 0).sum())
    if n1 == 0 or n0 == 0:
        return np.nan
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def roc_curve(y, p):
    ths = np.r_[np.inf, np.sort(np.unique(p))[::-1]]
    tpr = [((p >= t) & (y == 1)).sum() / (y == 1).sum() for t in ths]
    fpr = [((p >= t) & (y == 0)).sum() / (y == 0).sum() for t in ths]
    return np.array(fpr), np.array(tpr)


def pr_curve(y, p):
    ths = np.sort(np.unique(p))[::-1]
    prec, rec = [], []
    for t in ths:
        tp = ((p >= t) & (y == 1)).sum(); fp = ((p >= t) & (y == 0)).sum()
        prec.append(tp / (tp + fp) if tp + fp else 1.0)
        rec.append(tp / (y == 1).sum())
    prec, rec = np.array(prec), np.array(rec)
    ap_ = float(np.sum(np.diff(np.r_[0, rec]) * prec))          # average precision
    return rec, prec, ap_


def pair_arrays(g):
    """Human score and AI score for each pair (every pair has exactly one of each)."""
    piv = g.pivot_table(index="pair_id", columns="label", values="roberta_ai_prob", aggfunc="first").dropna()
    return piv[0].to_numpy(), piv[1].to_numpy()


def boot_ci(g, fn, n_boot, seed=0):
    """Pair bootstrap: resample whole human/AI pairs so twins stay together. fn(human_probs, ai_probs)."""
    rng = np.random.default_rng(seed)
    hp, ap_ = pair_arrays(g)
    n = len(hp)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        v = fn(hp[idx], ap_[idx])
        if v == v:
            vals.append(v)
    return (np.percentile(vals, 2.5), np.percentile(vals, 97.5)) if vals else (np.nan, np.nan)


def f1_from_pairs(hp, ap_):
    tp = int((ap_ >= THR).sum()); fn = len(ap_) - tp; fp = int((hp >= THR).sum()); tn = len(hp) - fp
    return prf(tp, fp, tn, fn)["f1"]


def auc_from_pairs(hp, ap_):
    return roc_auc(np.r_[np.zeros(len(hp)), np.ones(len(ap_))], np.r_[hp, ap_])


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- Table 5: metrics
rows, cms = [], {}
for name, g in GROUPS:
    y, p = g.label.to_numpy(), g.roberta_ai_prob.to_numpy()
    tp, fp, tn, fn = confusion(y, p, THR)
    cms[name] = (tp, fp, tn, fn)
    m = prf(tp, fp, tn, fn)
    _, _, ap_ = pr_curve(y, p)
    f1_lo, f1_hi = boot_ci(g, f1_from_pairs, args.boot)
    auc_lo, auc_hi = boot_ci(g, auc_from_pairs, args.boot)
    row = dict(group=name, threshold=THR, n_human=int((y == 0).sum()), n_ai=int((y == 1).sum()),
               TP=tp, FP=fp, TN=tn, FN=fn)
    for key, k, n in (("accuracy", tp + tn, len(y)), ("precision", tp, tp + fp),
                      ("recall", tp, tp + fn), ("specificity", tn, tn + fp)):
        lo, hi = wilson(k, n)
        row.update({key: round(m[key], 3), f"{key}_ci_low": round(lo, 3), f"{key}_ci_high": round(hi, 3)})
    row.update(f1=round(m["f1"], 3), f1_ci_low=round(f1_lo, 3), f1_ci_high=round(f1_hi, 3),
               roc_auc=round(roc_auc(y, p), 3), roc_auc_ci_low=round(auc_lo, 3), roc_auc_ci_high=round(auc_hi, 3),
               pr_auc=round(ap_, 3))
    rows.append(row)
t5 = pd.DataFrame(rows)
t5.to_csv(OUT / "table_5_metrics.csv", index=False)
show = ["group", "n_human", "n_ai", "TP", "FP", "TN", "FN", "accuracy", "precision", "recall", "specificity", "f1", "roc_auc"]
print(f"\nTable 5 - metrics at threshold {THR}\n", t5[show].to_string(index=False))

# ---------------------------------------------------------------- Table 6: threshold sweep
THS = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
rows = []
for name, g in GROUPS:
    y, p = g.label.to_numpy(), g.roberta_ai_prob.to_numpy()
    for t in THS:
        m = prf(*confusion(y, p, t))
        rows.append(dict(group=name, threshold=t, **{k: round(v, 3) for k, v in m.items()}))
t6 = pd.DataFrame(rows)
t6.to_csv(OUT / "table_6_threshold_sweep.csv", index=False)

# ---------------------------------------------------------------- Table 7: by length
LB = [(1, 9, "under 10 words"), (10, 19, "10-19 words"), (20, 39, "20-39 words"), (40, 10**6, "40+ words")]  # human-original length
rows = []
# Bin by the length of the HUMAN original in each pair, so human and AI twins always land in the same bin.
df["pair_len"] = df.pair_id.map(df[df.label == 0].set_index("pair_id").word_count)
print("\nAverage words per review - human: %.1f | AI rewrite: %.1f  (AI text that is longer is itself a clue "
      "detectors can pick up; mention it in the report)" % (df[df.label == 0].word_count.mean(),
                                                         df[df.label == 1].word_count.mean()))
for lo_w, hi_w, lab in LB:
    s = df[(df.pair_len >= lo_w) & (df.pair_len <= hi_w)]
    y, p = s.label.to_numpy(), s.roberta_ai_prob.to_numpy()
    tp, fp, tn, fn = confusion(y, p, THR)
    m = prf(tp, fp, tn, fn)
    rows.append(dict(length=lab, n_human=int((y == 0).sum()), n_ai=int((y == 1).sum()),
                     recall=round(m["recall"], 3) if m["recall"] == m["recall"] else np.nan,
                     specificity=round(m["specificity"], 3) if m["specificity"] == m["specificity"] else np.nan,
                     recall_ci_low=round(wilson(tp, tp + fn)[0], 3), recall_ci_high=round(wilson(tp, tp + fn)[1], 3),
                     spec_ci_low=round(wilson(tn, tn + fp)[0], 3), spec_ci_high=round(wilson(tn, tn + fp)[1], 3)))
t7 = pd.DataFrame(rows)
t7.to_csv(OUT / "table_7_metrics_by_length.csv", index=False)
print("\nTable 7 - by length\n", t7[["length", "n_human", "n_ai", "recall", "specificity"]].to_string(index=False))

# ---------------------------------------------------------------- Fig 5: confusion matrices
cmap = LinearSegmentedColormap.from_list("blue", ["#fcfcfb", "#86b6ef", "#2a78d6", "#184f95"])
fig, axes = plt.subplots(1, len(GROUPS), figsize=(4.6 * len(GROUPS), 4.6))
axes = np.atleast_1d(axes)
for ax, (name, g) in zip(axes, GROUPS):
    tp, fp, tn, fn = cms[name]
    mat = np.array([[tn, fp], [fn, tp]])
    rowp = mat / mat.sum(axis=1, keepdims=True)
    ax.imshow(rowp, cmap=cmap, vmin=0, vmax=1)
    ax.grid(False)
    tags = [["TN", "FP"], ["FN", "TP"]]
    for i in range(2):
        for j in range(2):
            col = "white" if rowp[i, j] > 0.55 else INK
            ax.text(j, i - 0.12, f"{mat[i, j]}", ha="center", va="center", fontsize=22, fontweight="bold", color=col)
            ax.text(j, i + 0.2, f"{tags[i][j]} · {100 * rowp[i, j]:.0f}% of row", ha="center", va="center",
                    fontsize=9.5, color=col)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Predicted\nHUMAN", "Predicted\nAI"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["Actual\nHUMAN", "Actual\nAI"])
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title(f"{name}\n(n={len(g)})", fontsize=11.5)
fig.suptitle(f"Confusion matrices at threshold {THR}", x=0.01, ha="left", fontsize=14, fontweight="bold")
save(fig, "fig_5_confusion_matrices.png")

# ---------------------------------------------------------------- Fig 6: metric bars
MET = ["accuracy", "precision", "recall", "specificity", "f1"]
MLAB = ["Accuracy", "Precision", "Recall", "Specificity", "F1"]
fig, ax = plt.subplots(figsize=(10, 4.8))
w = 0.8 / len(GROUPS)
for j, (name, _) in enumerate(GROUPS):
    r = t5[t5.group == name].iloc[0]
    vals = np.array([r[m] for m in MET], dtype=float)
    lo = np.array([r[f"{m}_ci_low"] for m in MET], dtype=float)
    hi = np.array([r[f"{m}_ci_high"] for m in MET], dtype=float)
    x = np.arange(len(MET)) + (j - (len(GROUPS) - 1) / 2) * w
    ax.bar(x, vals, w * 0.92, color=GCOL[j], label=f"{name} (n={int(r.n_human + r.n_ai)})", zorder=3)
    ax.errorbar(x, vals, yerr=[vals - lo, hi - vals], fmt="none", ecolor=INK2, capsize=2.5, lw=1, zorder=4)
    for xi, v, h in zip(x, vals, hi):
        if v == v:
            ax.text(xi, min(h, 1.0) + 0.015, f"{v:.2f}", ha="center", va="bottom", fontsize=8.5, color=INK2)
ax.set_xticks(np.arange(len(MET))); ax.set_xticklabels(MLAB)
ax.set_ylim(0, 1.18); ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0]); ax.set_ylabel("Score (0-1)")
ax.axhline(1.0, color=GRID, lw=1)
ax.set_title(f"RoBERTa detector performance on the labeled set (threshold {THR})", pad=24)
ax.text(0, 1.02, "Whiskers: 95% CI (Wilson for proportions, pair bootstrap for F1). Set is 50% human / 50% AI.",
        transform=ax.transAxes, fontsize=9, color=INK2)
ax.legend(frameon=False, loc="upper center", ncol=len(GROUPS), bbox_to_anchor=(0.5, 1.0), fontsize=9.5)
save(fig, "fig_6_metrics_bars.png")

# ---------------------------------------------------------------- Fig 7: ROC
fig, ax = plt.subplots(figsize=(6.2, 5.6))
ax.plot([0, 1], [0, 1], color=INK2, lw=1, ls="--", label="Random guessing")
for j, (name, g) in enumerate(GROUPS):
    y, p = g.label.to_numpy(), g.roberta_ai_prob.to_numpy()
    fpr, tpr = roc_curve(y, p)
    auc = roc_auc(y, p)
    ax.plot(fpr, tpr, color=GCOL[j], lw=2, label=f"{name}  (AUC {auc:.2f})")
    tp, fp, tn, fn = cms[name]
    ax.plot(fp / max(fp + tn, 1), tp / max(tp + fn, 1), "o", ms=9, mfc=GCOL[j], mec=SURFACE, mew=2, zorder=5)
ax.set_xlabel("False-positive rate (human reviews wrongly flagged)")
ax.set_ylabel("True-positive rate (recall)")
ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
ax.set_title("ROC curve")
ax.text(0.98, 0.04, f"Dots = operating point at threshold {THR}", ha="right", fontsize=9, color=INK2)
ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1.0, 0.1), fontsize=9)
save(fig, "fig_7_roc_curve.png")

# ---------------------------------------------------------------- Fig 8: PR
fig, ax = plt.subplots(figsize=(6.2, 5.6))
for j, (name, g) in enumerate(GROUPS):
    y, p = g.label.to_numpy(), g.roberta_ai_prob.to_numpy()
    rec, prec, ap_ = pr_curve(y, p)
    ax.plot(rec, prec, color=GCOL[j], lw=2, label=f"{name}  (AP {ap_:.2f})")
    tp, fp, tn, fn = cms[name]
    if tp + fp:
        ax.plot(tp / max(tp + fn, 1), tp / (tp + fp), "o", ms=9, mfc=GCOL[j], mec=SURFACE, mew=2, zorder=5)
ax.axhline(0.5, color=INK2, lw=1, ls="--", label="Random guessing (50% AI)")
ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
ax.set_title("Precision-recall curve")
ax.text(0.02, 0.04, f"Dots = operating point at threshold {THR}", fontsize=9, color=INK2)
ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0.0, 0.1), fontsize=9)
save(fig, "fig_8_precision_recall_curve.png")

# ---------------------------------------------------------------- Fig 9: threshold sweep
fig, axes = plt.subplots(1, len(GROUPS), figsize=(4.8 * len(GROUPS), 4.4), sharey=True)
axes = np.atleast_1d(axes)
for ax, (name, _) in zip(axes, GROUPS):
    s = t6[t6.group == name]
    for met, col, lab in (("precision", C1, "Precision"), ("recall", C2, "Recall"), ("f1", C3, "F1")):
        ax.plot(s.threshold, s[met], color=col, lw=2, marker="o", ms=6, mfc=col, mec=SURFACE, mew=1.5, label=lab)
    ax.axvline(THR, color=INK2, lw=1, ls="--")
    ax.set_title(name, fontsize=11.5)
    ax.set_xlabel("Decision threshold")
    ax.set_ylim(0, 1.05)
axes[0].set_ylabel("Score")
axes[0].legend(frameon=False, loc="lower left", fontsize=9)
fig.suptitle("Precision, recall and F1 as the threshold moves", x=0.01, ha="left", fontsize=14, fontweight="bold")
save(fig, "fig_9_threshold_sweep.png")

# ---------------------------------------------------------------- Fig 10: score distributions
panels = [(n, g) for n, g in GROUPS if n != "All reviews"] or GROUPS[:1]
fig, axes = plt.subplots(1, len(panels), figsize=(5.4 * len(panels), 4.4), sharey=True)
axes = np.atleast_1d(axes)
edges = np.linspace(0, 1, 21)
for ax, (name, g) in zip(axes, panels):
    for lab, col, nm in ((0, C1, "Human"), (1, C2, "AI rewrite")):
        s = g[g.label == lab].roberta_ai_prob
        ax.hist(s, bins=edges, weights=np.ones(len(s)) / max(len(s), 1) * 100, color=col, alpha=0.6,
                edgecolor=col, linewidth=1.3, histtype="stepfilled", label=f"{nm} (n={len(s)})", zorder=3)
    ax.axvline(THR, color=INK2, lw=1, ls="--")
    ax.set_title(name, fontsize=11.5)
    ax.set_xlabel("RoBERTa AI probability")
    ax.legend(frameon=False, loc="upper center", fontsize=9)
axes[0].set_ylabel("Share of reviews in bin (%)")
fig.suptitle("Do the two classes separate?", x=0.01, ha="left", fontsize=14, fontweight="bold")
save(fig, "fig_10_score_distributions.png")

# ---------------------------------------------------------------- Fig 11: by length
t7p = t7[(t7.n_human >= 5) & (t7.n_ai >= 5)]
fig, ax = plt.subplots(figsize=(8.5, 4.6))
x = np.arange(len(t7p)); w = 0.36
for j, (col, key, lab) in enumerate(((C2, "recall", "Recall (AI caught)"), (C1, "specificity", "Specificity (human left alone)"))):
    v = t7p[key].to_numpy(dtype=float)
    lo = t7p["recall_ci_low" if key == "recall" else "spec_ci_low"].to_numpy(dtype=float)
    hi = t7p["recall_ci_high" if key == "recall" else "spec_ci_high"].to_numpy(dtype=float)
    xs = x + (j - 0.5) * (w + 0.03)
    ax.bar(xs, v, w, color=col, label=lab, zorder=3)
    ax.errorbar(xs, v, yerr=[v - lo, hi - v], fmt="none", ecolor=INK2, capsize=3, lw=1, zorder=4)
    for xi, vi, hi_ in zip(xs, v, hi):
        ax.text(xi, min(hi_, 1) + 0.015, f"{vi:.2f}", ha="center", va="bottom", fontsize=9, color=INK2)
ax.set_xticks(x)
ax.set_xticklabels([f"{r.length}\n(human {r.n_human} / AI {r.n_ai})" for r in t7p.itertuples()], fontsize=9.5)
ax.set_ylim(0, 1.2); ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0]); ax.set_ylabel("Score (0-1)")
ax.set_title("Detector accuracy by review length", pad=8)
ax.legend(frameon=False, loc="upper center", ncol=2)
save(fig, "fig_11_by_length.png")

print(f"\nDone. Tables and charts are in: {OUT}")

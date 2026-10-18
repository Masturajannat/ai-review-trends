"""
STEP 5 - Estimate the TRUE share of AI reviews per period, correcting for the detector's mistakes.

Reads  : combined_reviews_detected_clean.csv     (from step 0; use --input to change, e.g. the raw csv)
         analysis/labeled_set_scored.csv         (from step 3)
Writes : analysis/table_8_corrected_ai_share.csv
         analysis/fig_12_corrected_ai_share.png
Run:   python 05_corrected_ai_share.py          (pandas, numpy, matplotlib only; no internet; ~10 seconds)

WHY: "8.4% flagged" is NOT "8.4% AI". Some flags are human reviews wrongly flagged (false positives) and
many AI reviews are missed. Using the error rates measured on the labeled set:
      observed flag rate  q  =  true AI share p * recall  +  (1 - p) * false_positive_rate
      =>  p = (q - FPR) / (recall - FPR)          (the Rogan-Gladen correction)
Recall and FPR come from the labeled set (step 3). q comes from your real reviews.

HOW the error bars are made: bootstrap. Each of 2000 rounds resamples (a) the real reviews of that period and
(b) the labeled PAIRS (so recall/FPR uncertainty is included), recomputes p, and we take the 2.5%-97.5% range.
Because the labeled set is small, the bars are wide. That is honest, not a bug.

Only reviews the labeled set represents are used: translated reviews with >= 10 words, original-English with >= 5 words
(shorter reviews were never tested and are almost never flagged). The English path has only ~35 pairs: treat as indicative.

TWO VERSIONS of the false-positive rate are used, side by side:
  A  "labeled"   FPR measured on the labeled human reviews (small sample).
  B  "baseline"  FPR = the flag rate of the REAL pre-2022 reviews (all human by construction, large sample). Preferred:
                 it matches your real data, so before-2022 is 0 by definition and only 2022 / after-2022 are estimated.
If A gives a clearly non-zero estimate for pre-2022 (which must be ~0), the labeled-set FPR does not match your real data:
say so, and trust B.

ASSUMPTION to state in the report: real AI reviews behave like our Gemini rewrites (same recall), and the real
human reviews of every period behave like the pre-2022 human reviews (same false-positive rate).
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
OUT = BASE / "analysis"
ap = argparse.ArgumentParser()
ap.add_argument("--input", default="combined_reviews_detected_clean.csv")
ap.add_argument("--threshold", type=float, default=0.5)
ap.add_argument("--boot", type=int, default=2000)
args = ap.parse_args()
THR, RNG = args.threshold, np.random.default_rng(42)
MINW = {"translated": 10, "original_english": 5}      # same minimums as step 2
PATHNAME = {"translated": "translated", "original_english": "english"}   # text_source -> labeled_set 'path'
PERIODS = ["pre_2022", "2022", "post_2022"]
LABEL = {"pre_2022": "Before 2022", "2022": "2022", "post_2022": "After 2022"}

rev = pd.read_csv(BASE / args.input, encoding="utf-8-sig").dropna(subset=["roberta_ai_prob"])
lab = pd.read_csv(OUT / "labeled_set_scored.csv", encoding="utf-8-sig").dropna(subset=["roberta_ai_prob"])


def pair_arrays(g):
    piv = g.pivot_table(index="pair_id", columns="label", values="roberta_ai_prob", aggfunc="first").dropna()
    return (piv[0].to_numpy() >= THR).astype(float), (piv[1].to_numpy() >= THR).astype(float)   # human flagged, AI flagged


def correct(q, fpr, rec):
    d = rec - fpr
    return np.nan if d <= 0.02 else (q - fpr) / d


rows, plot = [], []
for src, minw in MINW.items():
    hf, af = pair_arrays(lab[lab.path == PATHNAME[src]])
    fpr, rec = hf.mean(), af.mean()
    print(f"\n[{src}] labeled pairs={len(hf)}  false-positive rate={fpr:.3f}  recall={rec:.3f}")
    for per in PERIODS:
        g = rev[(rev.text_source == src) & (rev.period == per) & (rev.word_count >= minw)]
        flags = (g.roberta_ai_prob.to_numpy() >= THR).astype(float)
        q = flags.mean()
        p = correct(q, fpr, rec)
        bs = []
        for _ in range(args.boot):
            qb = flags[RNG.integers(0, len(flags), len(flags))].mean()
            ih, ia = RNG.integers(0, len(hf), len(hf)), RNG.integers(0, len(af), len(af))
            bs.append(correct(qb, hf[ih].mean(), af[ia].mean()))
        bs = np.array(bs)
        ok = bs[~np.isnan(bs)]
        lo, hi = np.percentile(ok, [2.5, 97.5])
        # version B: FPR = pre-2022 real flag rate (bootstrapped too)
        pre_fl = (rev[(rev.text_source == src) & (rev.period == "pre_2022") & (rev.word_count >= minw)].roberta_ai_prob.to_numpy() >= THR).astype(float)
        pB = correct(q, pre_fl.mean(), rec)
        bB = np.array([correct(flags[RNG.integers(0, len(flags), len(flags))].mean(),
                               pre_fl[RNG.integers(0, len(pre_fl), len(pre_fl))].mean(),
                               af[RNG.integers(0, len(af), len(af))].mean()) for _ in range(args.boot)])
        okB = bB[~np.isnan(bB)]
        loB, hiB = np.percentile(okB, [2.5, 97.5]) if len(okB) else (np.nan, np.nan)
        rows.append(dict(text_source=src, period=per, n_reviews=len(g), baseline_est=round(float(np.clip(pB, 0, 1)), 4) if per != "pre_2022" else 0.0,
                         baseline_ci_low=round(float(np.clip(loB, 0, 1)), 4) if per != "pre_2022" else 0.0,
                         baseline_ci_high=round(float(np.clip(hiB, 0, 1)), 4) if per != "pre_2022" else 0.0,
                         baseline_unstable_draws=round(float(np.isnan(bB).mean()), 3), observed_flag_rate=round(q, 4),
                         false_positive_rate=round(fpr, 4), recall=round(rec, 4),
                         labeled_est_raw=round(p, 4), labeled_est_clipped=round(float(np.clip(p, 0, 1)), 4),
                         labeled_ci_low=round(float(np.clip(lo, 0, 1)), 4), labeled_ci_high=round(float(np.clip(hi, 0, 1)), 4),
                         labeled_unstable_draws=round(float(np.isnan(bs).mean()), 3)))
        if per != "pre_2022":
            plot.append((src, per, float(np.clip(pB, 0, 1)), float(np.clip(loB, 0, 1)), float(np.clip(hiB, 0, 1)), len(g)))
        if per == "pre_2022":
            print(f"  sanity check: version A estimate for pre-2022 = {p*100:.0f}% (should be ~0%; if far from 0 trust version B)")
    # post minus pre difference
    pre = rev[(rev.text_source == src) & (rev.period == "pre_2022") & (rev.word_count >= minw)].roberta_ai_prob.to_numpy() >= THR
    post = rev[(rev.text_source == src) & (rev.period == "post_2022") & (rev.word_count >= minw)].roberta_ai_prob.to_numpy() >= THR
    diffs = []
    for _ in range(args.boot):
        ih, ia = RNG.integers(0, len(hf), len(hf)), RNG.integers(0, len(af), len(af))
        f, r = hf[ih].mean(), af[ia].mean()
        diffs.append(correct(post[RNG.integers(0, len(post), len(post))].mean(), f, r)
                     - correct(pre[RNG.integers(0, len(pre), len(pre))].mean(), f, r))
    diffs = np.array(diffs)
    diffs = diffs[~np.isnan(diffs)]
    dl, dh = np.percentile(diffs, [2.5, 97.5])
    d0 = correct(post.mean(), fpr, rec) - correct(pre.mean(), fpr, rec)
    print(f"  after-2022 minus before-2022 AI share: {d0*100:+.1f} points  (95% range {dl*100:+.1f} to {dh*100:+.1f})")
    rows.append(dict(text_source=src, period="post_2022 minus pre_2022 (version A)", labeled_est_raw=round(d0, 4),
                     labeled_ci_low=round(dl, 4), labeled_ci_high=round(dh, 4)))

t = pd.DataFrame(rows)
t.to_csv(OUT / "table_8_corrected_ai_share.csv", index=False)
print("\nTable 8 - corrected AI share\n", t.to_string(index=False))

# ---------------- Fig 12 ----------------
SURFACE, INK, INK2, GRID, C1, C2 = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#eb6834"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                     "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "text.color": INK, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": GRID, "axes.axisbelow": True, "font.size": 11, "axes.titlesize": 13,
                     "axes.titleweight": "bold", "axes.titlelocation": "left"})
fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
for ax, (src, colr, ttl) in zip(axes, [("translated", C2, "Translated (Bengali/Banglish)"),
                                       ("original_english", C1, "Original English (few pairs: indicative)")]):
    pts = [x for x in plot if x[0] == src]
    xs = np.arange(len(pts))
    ax.bar(xs, [p[2] * 100 for p in pts], color=colr, width=0.55,
           yerr=[[(p[2] - p[3]) * 100 for p in pts], [(p[4] - p[2]) * 100 for p in pts]],
           capsize=6, error_kw=dict(ecolor=INK, lw=1.4))
    for x, p in zip(xs, pts):
        ax.text(x, p[4] * 100 + 2, f"{p[2]*100:.1f}%  (n={p[5]})", ha="center", fontsize=9, color=INK2)
    ax.set_xticks(xs)
    ax.set_xticklabels([LABEL[p[1]] for p in pts])
    ax.set_title(ttl, fontsize=11)
axes[0].set_ylabel("Estimated true AI share (%)")
axes[0].set_ylim(0, 115)
fig.suptitle("Estimated share of AI reviews after correcting for detector errors", x=0.07, ha="left", fontsize=13, fontweight="bold")
fig.text(0.07, 0.915, "Baseline = before-2022 flag rate (all human) = 0 by definition. Whiskers: 95% bootstrap range. Values below 0 shown as 0, above 100 as 100.",
         fontsize=9, color=INK2)
fig.tight_layout(rect=(0, 0, 1, 0.9))
fig.savefig(OUT / "fig_12_corrected_ai_share.png", dpi=160, bbox_inches="tight")
print("\nSaved analysis/table_8_corrected_ai_share.csv and analysis/fig_12_corrected_ai_share.png")

"""
STEP 1 - Baseline analysis of your existing RoBERTa results.  (No API key, no model download.)

Reads  : combined_reviews_detected.csv   (must be in the SAME folder as this script)
Writes : analysis/ folder next to this script, containing
           table_1_flag_rate_by_period_and_source.csv
           table_2_false_positive_by_length.csv
           table_3_pre_vs_post_tests.csv
           table_4_flag_rate_by_threshold.csv
           fig_1_flag_rate_by_period_and_source.png
           fig_2_false_positive_by_length.png
           fig_3_probability_distribution.png
           fig_4_flag_rate_by_threshold.png

Run:   python 01_baseline_analysis.py
       python 01_baseline_analysis.py --input combined_reviews_detected_clean.csv --out analysis_clean   (after step 0)

Key idea: reviews from before 2022 cannot be ChatGPT-written, so every pre-2022 review the
detector flags is a FALSE POSITIVE. That rate is the detector's noise floor.
"""
import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--input", default="combined_reviews_detected.csv", help="CSV to analyse")
ap.add_argument("--out", default="analysis", help="output folder name (created next to this script)")
args = ap.parse_args()

BASE = Path(__file__).resolve().parent
IN_FILE = BASE / args.input
OUT = BASE / args.out
OUT.mkdir(exist_ok=True)

# ---- chart style (reference palette: blue, orange, aqua) ----
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
})

PERIODS = ["pre_2022", "2022", "post_2022"]
SOURCES = ["original_english", "translated"]
SRC_LABEL = {"original_english": "Original English", "translated": "Translated (Bengali/Banglish)"}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def two_prop_z(k1, n1, k2, n2):
    """Two-sided z-test for difference in proportions (group 2 minus group 1)."""
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan")
    p1, p2, p = k1 / n1, k2 / n2, (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return p2 - p1, float("nan")
    z = (p2 - p1) / se
    pval = math.erfc(abs(z) / math.sqrt(2))
    return p2 - p1, pval


def rate_row(sub, **keys):
    n = len(sub)
    k = int(sub["flag"].sum())
    lo, hi = wilson(k, n)
    return {**keys, "reviews": n, "flagged": k,
            "flag_rate_pct": round(100 * k / n, 1) if n else np.nan,
            "ci95_low_pct": round(100 * lo, 1), "ci95_high_pct": round(100 * hi, 1)}


df = pd.read_csv(IN_FILE, encoding="utf-8-sig")
df = df[df["Ai_flagged"] != "no_text"].copy()
df["flag"] = (df["Ai_flagged"] == "flagged")
print(f"{len(df)} reviews with text")

# ---------------- Table 1: flag rate by period x source ----------------
rows = []
for per in PERIODS:
    rows.append(rate_row(df[df.period == per], period=per, text_source="ALL"))
    for src in SOURCES:
        rows.append(rate_row(df[(df.period == per) & (df.text_source == src)], period=per, text_source=src))
t1 = pd.DataFrame(rows)
t1.to_csv(OUT / "table_1_flag_rate_by_period_and_source.csv", index=False)
print("\nTable 1 - flag rate by period and text source\n", t1.to_string(index=False))

# ---------------- Table 2: false-positive rate by length (pre-2022 only) ----------------
bins = [(1, 4, "1-4 words"), (5, 9, "5-9 words"), (10, 29, "10-29 words"), (30, 10**6, "30+ words")]
pre = df[df.period == "pre_2022"]
rows = []
for lo_w, hi_w, lab in bins:
    rows.append(rate_row(pre[(pre.word_count >= lo_w) & (pre.word_count <= hi_w)], length=lab, text_source="ALL"))
    for src in SOURCES:
        rows.append(rate_row(pre[(pre.word_count >= lo_w) & (pre.word_count <= hi_w) & (pre.text_source == src)],
                             length=lab, text_source=src))
t2 = pd.DataFrame(rows)
t2.to_csv(OUT / "table_2_false_positive_by_length.csv", index=False)
print("\nTable 2 - false-positive rate by length (pre-2022 only)\n", t2.to_string(index=False))

# ---------------- Table 3: is post-2022 higher than pre-2022? ----------------
rows = []
subsets = {
    "all reviews": df,
    "30+ words": df[df.word_count >= 30],
    "10+ words": df[df.word_count >= 10],
    "translated only": df[df.text_source == "translated"],
    "original English only": df[df.text_source == "original_english"],
    "translated, 10+ words": df[(df.text_source == "translated") & (df.word_count >= 10)],
}
for name, s in subsets.items():
    a, b = s[s.period == "pre_2022"], s[s.period == "post_2022"]
    diff, pval = two_prop_z(int(a.flag.sum()), len(a), int(b.flag.sum()), len(b))
    rows.append({"subset": name, "pre_n": len(a), "pre_flag_pct": round(100 * a.flag.mean(), 1) if len(a) else np.nan,
                 "post_n": len(b), "post_flag_pct": round(100 * b.flag.mean(), 1) if len(b) else np.nan,
                 "diff_post_minus_pre_pts": round(100 * diff, 1), "p_value": round(pval, 3)})
t3 = pd.DataFrame(rows)
t3.to_csv(OUT / "table_3_pre_vs_post_tests.csv", index=False)
print("\nTable 3 - post-2022 vs pre-2022 (two-proportion z-test)\n", t3.to_string(index=False))

# ---------------- Table 3b: platform x period (is the mix of platforms changing?) ----------------
t3b = (df.groupby(["platform", "period"]).flag.agg(reviews="size", flag_rate_pct=lambda x: round(100 * x.mean(), 1))
         .reset_index())
t3b.to_csv(OUT / "table_3b_flag_rate_by_platform_and_period.csv", index=False)
print("\nTable 3b - flag rate by platform and period\n", t3b.to_string(index=False))

# ---------------- Table 4: flag rate as the threshold rises ----------------
THRESH = [0.5, 0.7, 0.9, 0.95, 0.99]
rows = []
for per in PERIODS:
    s = df[df.period == per]
    for t in THRESH:
        k = int((s.roberta_ai_prob >= t).sum())
        rows.append({"period": per, "threshold": t, "reviews": len(s), "flagged": k,
                     "flag_rate_pct": round(100 * k / len(s), 2)})
t4 = pd.DataFrame(rows)
t4.to_csv(OUT / "table_4_flag_rate_by_threshold.csv", index=False)
print("\nTable 4 - flag rate by threshold\n", t4.pivot(index="threshold", columns="period", values="flag_rate_pct").to_string())


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------- Fig 1: flag rate by period and source ----------------
fig, ax = plt.subplots(figsize=(8.5, 4.8))
w = 0.36
for j, (src, col) in enumerate(zip(SOURCES, (C1, C2))):
    sub = t1[t1.text_source == src].set_index("period").loc[PERIODS]
    x = np.arange(len(PERIODS)) + (j - 0.5) * (w + 0.03)
    err = [sub.flag_rate_pct - sub.ci95_low_pct, sub.ci95_high_pct - sub.flag_rate_pct]
    ax.bar(x, sub.flag_rate_pct, w, color=col, label=SRC_LABEL[src], zorder=3)
    ax.errorbar(x, sub.flag_rate_pct, yerr=err, fmt="none", ecolor=INK2, capsize=3, lw=1, zorder=4)
    for xi, r, hi, n in zip(x, sub.flag_rate_pct, sub.ci95_high_pct, sub.reviews):
        ax.text(xi, hi + 0.6, f"{r:.1f}%\n(n={n})", ha="center", va="bottom", fontsize=9, color=INK2)
ax.set_xticks(np.arange(len(PERIODS)))
ax.set_xticklabels(["Before 2022\n(cannot be AI)", "2022", "After 2022"])
ax.set_ylabel("Reviews flagged as AI (%)")
ax.set_ylim(0, t1.ci95_high_pct.max() * 1.5)
ax.set_title("RoBERTa flag rate is the same before and after ChatGPT", pad=26)
ax.text(0, 1.01, "Whiskers: 95% confidence interval. Pre-2022 flags are false positives by construction.",
        transform=ax.transAxes, fontsize=9, color=INK2, va="bottom")
ax.legend(frameon=False, loc="upper center", ncol=2)
save(fig, "fig_1_flag_rate_by_period_and_source.png")

# ---------------- Fig 2: false positives by length ----------------
sub = t2[t2.text_source == "ALL"].set_index("length").loc[[b[2] for b in bins]]
fig, ax = plt.subplots(figsize=(8, 4.5))
x = np.arange(len(sub))
err = [sub.flag_rate_pct - sub.ci95_low_pct, sub.ci95_high_pct - sub.flag_rate_pct]
ax.bar(x, sub.flag_rate_pct, 0.55, color=C1, zorder=3)
ax.errorbar(x, sub.flag_rate_pct, yerr=err, fmt="none", ecolor=INK2, capsize=3, lw=1, zorder=4)
for xi, r, n in zip(x, sub.flag_rate_pct, sub.reviews):
    ax.text(xi, r + 1.2 + 0.0, f"{r:.1f}%\n(n={n})", ha="center", va="bottom", fontsize=9, color=INK2)
ax.set_xticks(x)
ax.set_xticklabels(sub.index)
ax.set_ylabel("False-positive rate (%)")
ax.set_ylim(0, max(sub.ci95_high_pct) * 1.3)
ax.set_title("False positives on pre-2022 (human) reviews, by length")
save(fig, "fig_2_false_positive_by_length.png")

# ---------------- Fig 3: probability distribution ----------------
fig, ax = plt.subplots(figsize=(8.5, 4.5))
edges = np.linspace(0, 1, 21)
for src, col in zip(SOURCES, (C1, C2)):
    s = pre[pre.text_source == src].roberta_ai_prob
    ax.hist(s, bins=edges, weights=np.ones(len(s)) / len(s) * 100, histtype="stepfilled", alpha=0.55,
            color=col, edgecolor=col, linewidth=1.5, label=f"{SRC_LABEL[src]} (n={len(s)})", zorder=3)
ax.set_yscale("log")
ax.axvline(0.5, color=INK2, lw=1, ls="--")
ax.text(0.51, 9, "flag threshold 0.5", color=INK2, fontsize=9)
ax.set_xlabel("RoBERTa AI probability")
ax.set_ylabel("Share of reviews in bin (%, log scale)")
ax.set_title("Pre-2022 (human) reviews: where do the scores land?")
ax.legend(frameon=False, loc="upper right")
save(fig, "fig_3_probability_distribution.png")

# ---------------- Fig 4: flag rate vs threshold ----------------
fig, ax = plt.subplots(figsize=(8, 4.5))
for per, col, lab in zip(PERIODS, (C1, C2, C3), ("Before 2022", "2022", "After 2022")):
    s = t4[t4.period == per]
    ax.plot(s.threshold, s.flag_rate_pct, color=col, lw=2, marker="o", ms=7, mfc=col, mec=SURFACE, mew=2, label=lab)
ax.set_xlabel("Decision threshold on AI probability")
ax.set_ylabel("Reviews flagged (%)")
ax.set_xticks(THRESH)
ax.set_ylim(0, None)
ax.set_title("Raising the threshold does not separate the periods")
ax.legend(frameon=False)
save(fig, "fig_4_flag_rate_by_threshold.png")

print(f"\nDone. Tables and charts are in: {OUT}")

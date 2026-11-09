"""Step 10: does the same review get a different score in another language?

Reads language_bias/results/scores_raw.csv (step 09) and writes:
  language_bias/results/scores_wide.csv         one row per review, one score per language
  language_bias/results/language_bias_summary.txt
  language_bias/results/fig_language_versions.png   every review's three scores, and the means
  language_bias/results/fig_language_differences.png  mean difference between languages

Main measure: for each pair of languages, the mean difference in score between the two
versions of the same review, with a 95% bootstrap interval over reviews, and a Wilcoxon
signed-rank test. A language is treated as biased when the interval excludes 0; the bias
is treated as large enough to matter when the mean difference is 0.5 points or more
(half the run-to-run wobble seen in the main run is about this size).

  python scripts/10_language_bias_summary.py
"""
import argparse, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import ROOT

LANGS = ["bangla", "banglish", "english"]
COLORS = {"bangla": "#1f77b4", "banglish": "#ff7f0e", "english": "#2ca02c"}
PAIRS = [("bangla", "english"), ("banglish", "english"), ("bangla", "banglish")]
BOOT = 5000
MATTERS = 0.5

ap = argparse.ArgumentParser()
ap.add_argument("--version", default=None)
a = ap.parse_args()

res = os.path.join(ROOT, "language_bias", "results")
raw = pd.read_csv(os.path.join(res, "scores_raw.csv"))
version = a.version or raw["prompt_version"].iloc[-1]
raw = raw[raw["prompt_version"] == version]
rng = np.random.default_rng(1)

# one score per review and language = mean of the runs
per = raw.groupby(["item_id", "language"]).agg(score=("overall", "mean"), runs=("overall", "size"),
                                               spread=("overall", lambda s: s.max() - s.min()))
wide = per["score"].unstack("language")
info = raw.drop_duplicates("item_id").set_index("item_id")[["review_id", "source_language"]]
wide = wide.join(info).dropna(subset=LANGS)          # only reviews scored in all three languages
n = len(wide)
if n == 0:
    raise SystemExit("no review has scores in all three languages yet")


def boot_ci(x):
    x = np.asarray(x, float)
    means = x[rng.integers(0, len(x), (BOOT, len(x)))].mean(axis=1)
    return np.percentile(means, [2.5, 97.5])


def wilcoxon_p(x):
    from scipy.stats import wilcoxon
    x = np.asarray(x, float)
    if np.all(x == 0):
        return 1.0
    return float(wilcoxon(x, zero_method="zsplit").pvalue)


lines = [f"prompt version: {version}", f"reviews scored in all three languages: {n}",
         "source language: " + ", ".join(f"{k} {v}" for k, v in wide["source_language"].value_counts().items()),
         f"runs per version: {int(per['runs'].min())}-{int(per['runs'].max())}",
         f"run-to-run spread within a version: same score {np.mean(per['spread'] == 0):.0%}, "
         f"within 1 point {np.mean(per['spread'] <= 1):.0%}", ""]

lines.append("MEAN SCORE PER LANGUAGE VERSION (same reviews)")
for l in LANGS:
    lo, hi = boot_ci(wide[l])
    lines.append(f"  {l:9s} {wide[l].mean():.2f}  (95% CI {lo:.2f}-{hi:.2f})")
lines.append("")

lines.append("DIFFERENCE BETWEEN VERSIONS OF THE SAME REVIEW (first minus second, points)")
pair_rows = []
for x, y in PAIRS:
    d = wide[x] - wide[y]
    lo, hi = boot_ci(d)
    p = wilcoxon_p(d)
    biased = not (lo <= 0 <= hi)
    verdict = ("no clear difference" if not biased else
               "clear difference, " + ("large enough to matter" if abs(d.mean()) >= MATTERS else "but small"))
    pair_rows.append(dict(pair=f"{x} - {y}", mean=d.mean(), lo=lo, hi=hi, p=p,
                          same=np.mean(d.abs() < 0.25), within1=np.mean(d.abs() <= 1), verdict=verdict))
    lines.append(f"  {x} - {y}: mean {d.mean():+.2f} (95% CI {lo:+.2f} to {hi:+.2f}), Wilcoxon p = {p:.2f}; "
                 f"same score {np.mean(d.abs() < 0.25):.0%}, within 1 point {np.mean(d.abs() <= 1):.0%} -> {verdict}")
lines.append("")

# does the original text score differently from its translations?
orig = np.array([wide.loc[i, s] for i, s in zip(wide.index, wide["source_language"])])
trans = np.array([np.mean([wide.loc[i, l] for l in LANGS if l != s]) for i, s in zip(wide.index, wide["source_language"])])
d = orig - trans
lo, hi = boot_ci(d)
lines.append("ORIGINAL AGAINST ITS TRANSLATIONS (original minus mean of the two translations)")
lines.append(f"  mean {d.mean():+.2f} (95% CI {lo:+.2f} to {hi:+.2f}); a value away from 0 means translating "
             f"itself changes the score")
lines.append("")

lines.append("MEAN SCORE BY SOURCE LANGUAGE (rows) AND VERSION (columns)")
tab = wide.groupby("source_language")[LANGS].mean().round(2)
tab.insert(0, "reviews", wide.groupby("source_language").size())
lines += ["  " + l for l in tab.to_string().splitlines()]
lines.append("")

big = wide.assign(range_=wide[LANGS].max(axis=1) - wide[LANGS].min(axis=1)).sort_values("range_", ascending=False)
lines.append("REVIEWS WITH THE LARGEST GAP BETWEEN LANGUAGES (check these by hand)")
for i, r in big.head(5).iterrows():
    lines.append(f"  {i} ({r['source_language']} original): " +
                 ", ".join(f"{l} {r[l]:.1f}" for l in LANGS) + f"  gap {r['range_']:.1f}")

summary = "\n".join(lines)
open(os.path.join(res, "language_bias_summary.txt"), "w", encoding="utf-8").write(summary + "\n")
wide.reset_index().to_csv(os.path.join(res, "scores_wide.csv"), index=False, encoding="utf-8-sig")
print(summary)

# ---- figure 1: every review's three scores, plus the mean with its interval
fig, ax = plt.subplots(figsize=(6.5, 4.5))
x = np.arange(len(LANGS))
for i, r in wide.iterrows():
    ax.plot(x, [r[l] for l in LANGS], color="#999", alpha=0.35, lw=1)
for j, l in enumerate(LANGS):
    lo, hi = boot_ci(wide[l])
    ax.errorbar(j, wide[l].mean(), yerr=[[wide[l].mean() - lo], [hi - wide[l].mean()]], fmt="o",
                color=COLORS[l], ms=9, capsize=5, lw=2, zorder=3)
ax.set_xticks(x, [l.capitalize() for l in LANGS])
ax.set_ylim(0.5, 10.5)
ax.set_ylabel("score (mean of runs)")
ax.set_title(f"Same {n} reviews in three languages\n(grey: one review; dot: mean with 95% CI)", fontsize=10)
fig.tight_layout()
fig.savefig(os.path.join(res, "fig_language_versions.png"), dpi=150)
plt.close(fig)

# ---- figure 2: mean difference per pair of languages
fig, ax = plt.subplots(figsize=(6.5, 3))
pr = pd.DataFrame(pair_rows)
y = np.arange(len(pr))
ax.axvspan(-MATTERS, MATTERS, color="#eee", label=f"within ±{MATTERS} point")
ax.axvline(0, color="#555", lw=1)
ax.errorbar(pr["mean"], y, xerr=[pr["mean"] - pr["lo"], pr["hi"] - pr["mean"]], fmt="o", color="#333", capsize=4)
ax.set_yticks(y, [p.replace(" - ", " minus ").capitalize() for p in pr["pair"]])
ax.invert_yaxis()
ax.set_xlabel("difference in score, same review (points)")
ax.set_title("Score difference between language versions (95% CI)", fontsize=10)
ax.legend(frameon=False, fontsize=8, loc="lower right")
fig.tight_layout()
fig.savefig(os.path.join(res, "fig_language_differences.png"), dpi=150)
plt.close(fig)
print("\nsaved to", res)

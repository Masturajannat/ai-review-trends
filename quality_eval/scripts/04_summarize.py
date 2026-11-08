"""Build the wide table, stability summary and figures from scores_raw.csv."""
import argparse, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import folder

ap = argparse.ArgumentParser()
ap.add_argument("--folder", required=True, choices=["pilot", "main"])
ap.add_argument("--version", default=None)   # default: latest prompt version in the file
a = ap.parse_args()

fdir = folder(a.folder)
res = os.path.join(fdir, "results")
sample = pd.read_csv(os.path.join(fdir, "data", "pilot_sample.csv" if a.folder == "pilot" else "main_sample.csv"))
raw = pd.read_csv(os.path.join(res, "scores_raw.csv"))
version = a.version or raw["prompt_version"].iloc[-1]
raw = raw[raw["prompt_version"] == version]

# wide table: one row per review, one column per run
wide = raw.pivot(index="review_id", columns="run", values="overall")
wide.columns = [f"run{c}" for c in wide.columns]
runs = list(wide.columns)
wide["mean"] = wide[runs].mean(axis=1).round(2)
wide["spread"] = wide[runs].max(axis=1) - wide[runs].min(axis=1)
first = raw[raw["run"] == raw["run"].min()].set_index("review_id")["reason"].rename("reason_run1")
wide = wide.join(first).reset_index().merge(sample, on="review_id", how="left")
wide.to_csv(os.path.join(res, "scores_wide.csv"), index=False, encoding="utf-8-sig")

# only reviews that have every run can be compared
full = wide.dropna(subset=runs)
lines = [f"prompt version: {version}", f"runs: {len(runs)}",
         f"reviews in sample: {len(sample)}, scored in every run: {len(full)}",
         f"missing scores: {len(sample) * len(runs) - len(raw)}", ""]

if len(runs) >= 2:
    sp = full["spread"]
    r1, r2 = full[runs[0]], full[runs[1]]
    rho = r1.rank().corr(r2.rank())
    lines += ["STABILITY",
              f"same score in all runs:        {(sp == 0).mean():.0%}",
              f"within 1 point (spread <= 1):  {(sp <= 1).mean():.0%}",
              f"differ by 2+ points:           {(sp >= 2).mean():.0%}",
              f"rank correlation run1 vs run2: {rho:.2f}", ""]

m = full["mean"]
band = pd.cut(m.round(), [0, 2, 4, 6, 8, 10], labels=["1-2", "3-4", "5-6", "7-8", "9-10"])
lines += ["SCORE SPREAD (mean of runs, rounded)",
          f"distinct scores used: {m.round().nunique()}",
          "share per band: " + ", ".join(f"{k}: {v:.0%}" for k, v in band.value_counts(normalize=True).sort_index().items()),
          "", "MEAN SCORE BY LANGUAGE"]
lines += [f"  {k}: {v:.2f} (n={n})" for (k, v), n in zip(full.groupby("language")["mean"].mean().items(),
                                                        full.groupby("language").size())]
lb = pd.cut(full["n_words"], [5, 9, 19, 49, 10**6], labels=["6-9", "10-19", "20-49", "50+"])
lines += ["", "MEAN SCORE BY LENGTH (words)"]
lines += [f"  {k}: {v:.2f}" for k, v in full.groupby(lb, observed=True)["mean"].mean().items()]
lines += [f"  rank correlation of score with word count: {full['mean'].rank().corr(full['n_words'].rank()):.2f}"]
open(os.path.join(res, "stability_summary.txt"), "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))

# figures
if len(runs) >= 2:
    fig, ax = plt.subplots(figsize=(5, 3.5))
    c = full["spread"].value_counts().sort_index()
    ax.bar(c.index.astype(str), c.values, color="#4c72b0")
    for x, v in zip(range(len(c)), c.values):
        ax.text(x, v, str(v), ha="center", va="bottom")
    ax.set_xlabel("difference between runs (points)"); ax.set_ylabel("reviews")
    ax.set_title("How much do two runs differ?")
    fig.tight_layout(); fig.savefig(os.path.join(res, "fig_differences.png"), dpi=150); plt.close(fig)

    grid = np.zeros((10, 10), dtype=int)
    for x, y in zip(r1.astype(int), r2.astype(int)):
        grid[y - 1, x - 1] += 1
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.imshow(grid, origin="lower", cmap="Blues")
    for i in range(10):
        for j in range(10):
            if grid[i, j]:
                ax.text(j, i, grid[i, j], ha="center", va="center", fontsize=8)
    ax.set_xticks(range(10)); ax.set_xticklabels(range(1, 11))
    ax.set_yticks(range(10)); ax.set_yticklabels(range(1, 11))
    ax.set_xlabel("run 1 score"); ax.set_ylabel("run 2 score")
    ax.set_title("Run 1 vs run 2 (diagonal = same score)")
    fig.tight_layout(); fig.savefig(os.path.join(res, "fig_run1_vs_run2.png"), dpi=150); plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 3.8))
langs = sorted(full["language"].dropna().unique())
w = 0.8 / max(1, len(langs))
for k, lg in enumerate(langs):
    cnt = full[full["language"] == lg]["mean"].round().astype(int).value_counts().reindex(range(1, 11), fill_value=0)
    ax.bar(np.arange(1, 11) + k * w - 0.4 + w / 2, cnt.values, w, label=lg)
ax.set_xticks(range(1, 11)); ax.set_xlabel("score (mean of runs, rounded)"); ax.set_ylabel("reviews")
ax.set_title("Score distribution by language"); ax.legend()
fig.tight_layout(); fig.savefig(os.path.join(res, "fig_score_distribution.png"), dpi=150); plt.close(fig)

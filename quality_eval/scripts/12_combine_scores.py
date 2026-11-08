"""Step 12: one table with a quality score for every scored review.

Combines the pilot (prompt_v2 scores only), main and full sets into
quality_eval/all_scores.csv:
  review_id, platform, language, n_words, product_name, text_original,
  score (mean of the runs), runs, reason (first run), stage

  python scripts/12_combine_scores.py
"""
import os
import pandas as pd
import glob
from common import ROOT, folder, SAMPLE_FILES, read_scores

VERSION = "prompt_v2"
parts = []
for stage, fname in SAMPLE_FILES.items():
    res_dir = os.path.join(folder(stage), "results")
    if not glob.glob(os.path.join(res_dir, "scores_raw*.csv")):
        print(f"{stage}: no scores yet, skipped")
        continue
    raw = read_scores(res_dir).drop_duplicates(["review_id", "run", "prompt_version"])
    raw = raw[raw["prompt_version"] == VERSION]
    sample = pd.read_csv(os.path.join(folder(stage), "data", fname), dtype={"review_id": str})
    g = raw.sort_values("run").groupby("review_id")
    s = pd.DataFrame({"score": g["overall"].mean().round(2), "runs": g["overall"].size(),
                      "reason": g["reason"].first()}).reset_index()
    s = sample.merge(s, on="review_id", how="inner").assign(stage=stage)
    print(f"{stage}: {len(s)} of {len(sample)} reviews scored")
    parts.append(s)

allx = pd.concat(parts, ignore_index=True).drop_duplicates("review_id")
out = os.path.join(ROOT, "all_scores.csv")
allx.to_csv(out, index=False, encoding="utf-8-sig")
print(f"\n{len(allx)} reviews -> {out}")
print(allx.groupby(["platform", "language"])["score"].agg(["size", "mean"]).round(2).to_string())

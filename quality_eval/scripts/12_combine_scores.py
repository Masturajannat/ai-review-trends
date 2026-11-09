"""Step 12: one table with a quality score for every scored review.

Combines the pilot (prompt_v2 scores only), main and full sets into
quality_eval/all_scores.csv and the same table as quality_eval/all_scores.json:
  review_id, platform, language, n_words, product_name, text_original,
  score (mean of the runs), runs, reason (first run), stage,
  level, level_meaning, next_level (what the score level means and what the next level
    asks for, from the SCORING scale of the prompt; no API calls),
  weak_criteria, how_to_improve, feedback_from,
  check_product_detail ... check_on_topic (the ten 0/1 checks, for reviews scored with
    prompt_v2_checks; empty for reviews scored before the checks were added)
Feedback comes from the scoring call itself (prompt_v2_feedback) or, for reviews scored
before feedback was added, from step 14 (feedback_raw*.csv); empty if neither exists yet.

  python scripts/12_combine_scores.py
"""
import os
import pandas as pd
import glob
from common import ROOT, folder, SAMPLE_FILES, read_scores, save_table, CHECKS, LEVELS

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
    ccols = [f"check_{n}" for n in CHECKS]
    if all(c in raw for c in ccols):          # checks from the first run that has them
        ck = raw.dropna(subset=ccols).sort_values("run").drop_duplicates("review_id")
        s = s.merge(ck[["review_id"] + ccols], on="review_id", how="left")
    # feedback: from the scoring call if it had any, else from the backfill (step 14)
    fb = pd.DataFrame(columns=["review_id", "weak_criteria", "how_to_improve", "feedback_from"])
    if "how_to_improve" in raw:
        f1 = raw[raw["how_to_improve"].notna()].sort_values("run").drop_duplicates("review_id")
        fb = pd.concat([fb, f1[["review_id", "weak_criteria", "how_to_improve"]].assign(feedback_from="scoring")])
    for f in glob.glob(os.path.join(res_dir, "feedback_raw*.csv")):
        f2 = pd.read_csv(f, dtype={"review_id": str})
        fb = pd.concat([fb, f2[["review_id", "weak_criteria", "how_to_improve"]].assign(feedback_from="backfill")])
    fb = fb.drop_duplicates("review_id")
    s = s.merge(fb, on="review_id", how="left")
    print(f"{stage}: {len(s)} of {len(sample)} reviews scored, {s['how_to_improve'].notna().sum()} with feedback")
    parts.append(s)

allx = pd.concat(parts, ignore_index=True).drop_duplicates("review_id")
lvl = (allx["score"] + 0.5).apply(int).clip(1, 10)           # mean of runs, 6.5 -> 7
allx.insert(allx.columns.get_loc("stage") + 1, "level", lvl)
allx.insert(allx.columns.get_loc("level") + 1, "level_meaning", lvl.map(LEVELS))
allx.insert(allx.columns.get_loc("level_meaning") + 1, "next_level",
            lvl.map(lambda v: f"{v + 1}: {LEVELS[v + 1]}" if v < 10 else ""))
ccols = [f"check_{n}" for n in CHECKS]
for c in ccols:
    if c not in allx:
        allx[c] = pd.NA
allx[ccols] = allx[ccols].astype("Int64")
allx = allx[[c for c in allx.columns if c not in ccols] + ccols]
out = os.path.join(ROOT, "all_scores.csv")
js = save_table(allx, out)
print(f"\n{len(allx)} reviews -> {out}")
print(f"  and the same table as JSON -> {js}")
print(f"{allx[ccols[0]].notna().sum()} reviews have the ten checks")
print(allx.groupby(["platform", "language"])["score"].agg(["size", "mean"]).round(2).to_string())

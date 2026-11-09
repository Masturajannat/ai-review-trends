"""Step 11: the full set = every cleaned review not already in the pilot or the main sample.

  python scripts/11_make_full_set.py

Writes full/data/full_sample.csv with the same columns as the other samples, so
step 03 can score it:  python scripts/03_score.py --folder full --runs 1
Refuses to overwrite an existing full_sample.csv once scoring has started.
"""
import argparse, os
import pandas as pd
from common import folder, load_source, describe, KEEP_COLS

ap = argparse.ArgumentParser()
ap.add_argument("--source", default=None)   # optional, found automatically if omitted
a = ap.parse_args()

out = os.path.join(folder("full"), "data", "full_sample.csv")
import glob
if glob.glob(os.path.join(folder("full"), "results", "scores_raw*.csv")):
    raise SystemExit("full/results/scores_raw.csv exists: scoring has started, the set must not change.")

pilot_ids = pd.read_csv(os.path.join(folder("pilot"), "data", "pilot_ids.csv"))["review_id"]
main_ids = pd.read_csv(os.path.join(folder("main"), "data", "main_sample.csv"))["review_id"]
d = load_source(a.source)
d = d[~d["review_id"].isin(pilot_ids) & ~d["review_id"].isin(main_ids)]
d = d.sample(frac=1, random_state=11)       # shuffled, so a partial run already covers every group
d[KEEP_COLS].to_csv(out, index=False, encoding="utf-8-sig")
print(f"{len(d)} reviews (pilot {len(pilot_ids)} and main {len(main_ids)} left out) -> {out}")
describe(d[KEEP_COLS])

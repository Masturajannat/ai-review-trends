"""Draw the 400-review main sample, leaving out the pilot reviews.
Run this only after the prompt is frozen."""
import argparse, os
import pandas as pd
from common import folder, load_source, stratified_sample, describe

ap = argparse.ArgumentParser()
ap.add_argument("--source", default=None)   # optional, found automatically if omitted
ap.add_argument("--n", type=int, default=400)
ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()

pilot_ids = pd.read_csv(os.path.join(folder("pilot"), "data", "pilot_ids.csv"))["review_id"]
d = load_source(a.source)
d = d[~d["review_id"].isin(pilot_ids)]          # no overlap with the pilot
s = stratified_sample(d, a.n, a.seed)
s.to_csv(os.path.join(folder("main"), "data", "main_sample.csv"), index=False, encoding="utf-8-sig")
describe(s)

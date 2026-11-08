"""Draw the 100-review pilot sample and save its ids."""
import argparse, os
import pandas as pd
from common import folder, load_source, stratified_sample, describe

ap = argparse.ArgumentParser()
ap.add_argument("--source", default=None)   # optional, found automatically if omitted
ap.add_argument("--n", type=int, default=100)
ap.add_argument("--seed", type=int, default=7)
a = ap.parse_args()

out = os.path.join(folder("pilot"), "data")
s = stratified_sample(load_source(a.source), a.n, a.seed)
s.to_csv(os.path.join(out, "pilot_sample.csv"), index=False, encoding="utf-8-sig")
s[["review_id"]].to_csv(os.path.join(out, "pilot_ids.csv"), index=False)   # excluded from main later
describe(s)

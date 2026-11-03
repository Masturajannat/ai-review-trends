"""Main stage: compare the human judgments with the LLM scores.
Save the raters' filled copies as pairs_filled.csv and single_filled.csv."""
import math, os
import pandas as pd
from common import folder

res = os.path.join(folder("main"), "results")

def wilson(k, n, z=1.96):
    # 95% interval for a proportion
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - w, c + w

# blind pairs: did people pick the review the LLM scored higher?
key = pd.read_csv(os.path.join(res, "pairs_key.csv"))
ans = pd.read_csv(os.path.join(res, "pairs_filled.csv"))
key["pick"] = ans["better_AorB"].astype(str).str.strip().str.upper()
key = key[key["pick"].isin(["A", "B"])].copy()
key["llm_pick"] = (key["_score_a"] > key["_score_b"]).map({True: "A", False: "B"})
key["agree"] = key["pick"] == key["llm_pick"]
n, k = len(key), int(key["agree"].sum())
lo, hi = wilson(k, n)
print(f"pairs: humans agree with LLM in {k}/{n} = {k/n:.0%} (95% CI {lo:.0%}-{hi:.0%})")

# does it still hold when the higher-scored review is the shorter one?
hw = key.apply(lambda r: r["_words_a"] if r["llm_pick"] == "A" else r["_words_b"], axis=1)
lw = key.apply(lambda r: r["_words_b"] if r["llm_pick"] == "A" else r["_words_a"], axis=1)
for name, g in [("higher-scored is longer", key[hw > lw]), ("higher-scored is shorter/equal", key[hw <= lw])]:
    if len(g):
        print(f"  {name}: {int(g['agree'].sum())}/{len(g)} = {g['agree'].mean():.0%}")

# single reviews: rank correlation, human vs LLM
sc = pd.read_csv(os.path.join(res, "scores_raw.csv")).groupby("review_id")["overall"].mean().rename("llm")
one = pd.read_csv(os.path.join(res, "single_filled.csv")).merge(sc, on="review_id").dropna(subset=["my_score"])
print(f"single: Spearman rho = {one['my_score'].rank().corr(one['llm'].rank()):.2f} on {len(one)} reviews")

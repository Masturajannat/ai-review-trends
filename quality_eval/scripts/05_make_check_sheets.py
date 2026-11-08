"""Main stage: blind pairs for the manual check (scores hidden from raters).

Each pair has one review the LLM scored high and one it scored in the middle,
from the same platform and language, in random A/B order.
Writes (in main/results):
  pairs_for_raters.csv  no scores; input for 05b_make_pair_page.py
  pairs_key.csv         with scores and word counts; used by 06, never given to raters

Options:
  --pairs N      number of pairs wanted (default 50; fewer are made if there are
                 not enough high-scored reviews)
  --high-min X   lowest mean score that counts as "high" (default 8)
"""
import argparse, os, random
import pandas as pd
from common import folder

ap = argparse.ArgumentParser()
ap.add_argument("--pairs", type=int, default=50)
ap.add_argument("--high-min", type=float, default=8)
a = ap.parse_args()

random.seed(42)
res = os.path.join(folder("main"), "results")

s = pd.read_csv(os.path.join(folder("main"), "data", "main_sample.csv"))
raw = pd.read_csv(os.path.join(res, "scores_raw.csv"))
raw = raw[raw["prompt_version"] == raw["prompt_version"].iloc[-1]]   # one prompt version only
print("prompt version used:", raw["prompt_version"].iloc[-1])
s = s.merge(raw.groupby("review_id")["overall"].mean().rename("llm_score"), on="review_id")

# pairs: one clearly high and one middle (4-6), same platform and language
high = s[s["llm_score"] >= a.high_min]
mid = s[(s["llm_score"] >= 4) & (s["llm_score"] <= 6)]
print(f"{len(high)} high-scored reviews (>= {a.high_min}), {len(mid)} middle-scored (4-6)")
rows, used = [], set()
for _, h in high.sample(frac=1, random_state=1).iterrows():
    pool = mid[(mid["platform"] == h["platform"]) & (mid["language"] == h["language"])
               & ~mid["review_id"].isin(used)]
    if pool.empty:
        continue
    m = pool.sample(1, random_state=len(rows)).iloc[0]
    used.add(m["review_id"])
    x, y = (m, h) if random.random() < 0.5 else (h, m)     # random A/B order
    rows.append(dict(pair_id=len(rows) + 1,
                     product_a=x["product_name"], review_a=x["text_original"],
                     product_b=y["product_name"], review_b=y["text_original"],
                     better_AorB="",
                     _id_a=x["review_id"], _id_b=y["review_id"],
                     _score_a=x["llm_score"], _score_b=y["llm_score"],
                     _words_a=x["n_words"], _words_b=y["n_words"]))
    if len(rows) == a.pairs:
        break
pairs = pd.DataFrame(rows)
pairs.to_csv(os.path.join(res, "pairs_key.csv"), index=False, encoding="utf-8-sig")
pairs[[c for c in pairs.columns if not c.startswith("_")]].to_csv(
    os.path.join(res, "pairs_for_raters.csv"), index=False, encoding="utf-8-sig")
print(len(pairs), "pairs written")
print("next: python scripts\\05b_make_pair_page.py   (never give pairs_key.csv to raters)")

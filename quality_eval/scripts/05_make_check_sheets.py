"""Main stage: blind sheets for the manual check (scores hidden from raters)."""
import os, random
import pandas as pd
from common import folder

random.seed(42)
N_PAIRS, N_SINGLE = 50, 80
res = os.path.join(folder("main"), "results")

s = pd.read_csv(os.path.join(folder("main"), "data", "main_sample.csv"))
raw = pd.read_csv(os.path.join(res, "scores_raw.csv"))
s = s.merge(raw.groupby("review_id")["overall"].mean().rename("llm_score"), on="review_id")

# pairs: one clearly high (8+) and one middle (4-6), same platform and language
high = s[s["llm_score"] >= 8]
mid = s[(s["llm_score"] >= 4) & (s["llm_score"] <= 6)]
rows, used = [], set()
for _, h in high.sample(frac=1, random_state=1).iterrows():
    pool = mid[(mid["platform"] == h["platform"]) & (mid["language"] == h["language"])
               & ~mid["review_id"].isin(used)]
    if pool.empty:
        continue
    m = pool.sample(1, random_state=len(rows)).iloc[0]
    used.add(m["review_id"])
    a, b = (m, h) if random.random() < 0.5 else (h, m)     # random A/B order
    rows.append(dict(pair_id=len(rows) + 1,
                     product_a=a["product_name"], review_a=a["text_original"],
                     product_b=b["product_name"], review_b=b["text_original"],
                     better_AorB="",
                     _score_a=a["llm_score"], _score_b=b["llm_score"],
                     _words_a=a["n_words"], _words_b=b["n_words"]))
    if len(rows) == N_PAIRS:
        break
pairs = pd.DataFrame(rows)
pairs.to_csv(os.path.join(res, "pairs_key.csv"), index=False, encoding="utf-8-sig")
pairs[[c for c in pairs.columns if not c.startswith("_")]].to_csv(
    os.path.join(res, "pairs_for_raters.csv"), index=False, encoding="utf-8-sig")

# single reviews for a manual 1-10 score
single = s.sample(min(N_SINGLE, len(s)), random_state=7)
single[["review_id", "product_name", "text_original"]].assign(my_score="").to_csv(
    os.path.join(res, "single_for_raters.csv"), index=False, encoding="utf-8-sig")
print(len(pairs), "pairs,", len(single), "single reviews")
print("give raters only the *_for_raters.csv files")

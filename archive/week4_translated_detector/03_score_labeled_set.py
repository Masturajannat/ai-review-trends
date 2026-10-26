"""
STEP 3 - Run the SAME RoBERTa detector you already used on the labeled set.

Reads  : analysis/labeled_set.csv            (made by 02_build_labeled_set.py)
         detect_reviews_roberta.py            (your existing script - must be in this same folder;
                                               we reuse its model name, batch size and thread settings)
Writes : analysis/labeled_set_scored.csv      (same rows + roberta_ai_prob)

Run:  python 03_score_labeled_set.py
Time: a few minutes on CPU for ~700 short texts. The model is already downloaded from your first run.
"""
from pathlib import Path

import pandas as pd

import detect_reviews_roberta as det   # your existing script; importing it does NOT run it

BASE = Path(__file__).resolve().parent
IN_FILE = BASE / "analysis" / "labeled_set.csv"
OUT_FILE = BASE / "analysis" / "labeled_set_scored.csv"

df = pd.read_csv(IN_FILE, encoding="utf-8-sig")
texts = df["text_for_detector"].fillna("").astype(str).str.strip().tolist()
print(f"{len(df)} texts to score with {det.MODEL_NAME}")

score = det.load_scorer()
order = sorted(range(len(texts)), key=lambda i: len(texts[i]))   # similar lengths together = faster
probs = [None] * len(texts)
for n, start in enumerate(range(0, len(order), det.BATCH_SIZE), 1):
    ids = order[start:start + det.BATCH_SIZE]
    batch = [texts[i] if texts[i] else "." for i in ids]
    for i, p in zip(ids, score(batch)):
        probs[i] = round(float(p), 4)
    if n % 10 == 0:
        print(f"  scored {min(start + det.BATCH_SIZE, len(order))}/{len(order)}")

df["roberta_ai_prob"] = probs
df.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")
print(f"Saved -> {OUT_FILE}")
print(df.groupby(["path", "label_name"]).roberta_ai_prob.mean().round(3).unstack())

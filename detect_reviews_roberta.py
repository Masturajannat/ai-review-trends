"""
Adds AI-detection columns to your review CSV using a small RoBERTa detector (runs on CPU, no GPU needed).

New columns added:
    word_count          number of words in the English text
    text_source         original_english  = reviewer wrote English themselves
                        translated        = machine-translated from Bengali etc.
    roberta_ai_prob     raw probability (0-1) that the text is AI-written (helper column)
    Ai_flagged          flagged / non flagged  (no_text if the review is empty)
    confidence          high / medium / low  (mostly depends on review length)

How to run (from the folder that holds this file and the CSV):
    python detect_reviews_roberta.py          -> all reviews
    python detect_reviews_roberta.py 50       -> test run on the first 50 reviews only

Safe to stop any time (Ctrl+C). Progress is saved in roberta_progress.json and the next run continues.
"""
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

# ---------------- settings you can change ----------------
BASE = Path(__file__).resolve().parent
IN_FILE = BASE / "combined_reviews_translated_fixed.csv"
OUT_FILE = BASE / "combined_reviews_detected.csv"
PROGRESS_FILE = BASE / "roberta_progress.json"

TEXT_COLUMN = "translated_review_en"
MODEL_NAME = "Hello-SimpleAI/chatgpt-detector-roberta"
THRESHOLD = 0.5      # probability at or above this -> "flagged"
BATCH_SIZE = 16      # lower (e.g. 8) if your laptop feels slow
THREADS = 4          # CPU threads to use; lower (e.g. 2) = gentler on the laptop
MAX_TOKENS = 512
SAVE_EVERY_BATCHES = 10
# ----------------------------------------------------------

BENGALI = re.compile(r"[\u0980-\u09FF]")


def load_scorer():
    """Loads the model once and returns a function: list of texts -> list of AI probabilities."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(THREADS)
    print(f"Loading model {MODEL_NAME} (first run downloads about 500 MB)...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    model.eval()

    ai_index = 1
    for idx, label in model.config.id2label.items():
        if str(label).strip().lower() in ("chatgpt", "ai", "fake", "machine", "generated", "label_1"):
            ai_index = int(idx)
    print(f"Model labels: {model.config.id2label}  -> using index {ai_index} as 'AI'")

    def score(texts):
        with torch.no_grad():
            enc = tokenizer(texts, truncation=True, max_length=MAX_TOKENS,
                            padding=True, return_tensors="pt")
            probs = torch.softmax(model(**enc).logits, dim=-1)[:, ai_index]
        return probs.tolist()

    return score


def get_text_source(row):
    original = (row["review_text"] or "").strip()
    translated = (row[TEXT_COLUMN] or "").strip()
    if original and original == translated and not BENGALI.search(original):
        return "original_english"
    return "translated"


def make_confidence(words, prob):
    """Confidence in the flag. Short reviews can never be 'high'."""
    if prob is None or math.isnan(prob):
        return "low"
    strength = abs(prob - 0.5) * 2          # 0 = coin flip, 1 = very sure
    if words < 10:
        return "low"
    if words < 30:
        return "medium" if strength >= 0.8 else "low"
    if strength >= 0.8:
        return "high"
    if strength >= 0.5:
        return "medium"
    return "low"


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {}


def save_progress(done):
    tmp = PROGRESS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(done), encoding="utf-8")
    tmp.replace(PROGRESS_FILE)


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def summarise(df, title):
    print(f"\n=== {title} ===")
    rows = []
    for period in ("pre_2022", "2022", "post_2022"):
        sub = df[(df["period"] == period) & (df["Ai_flagged"] != "no_text")]
        k = int((sub["Ai_flagged"] == "flagged").sum())
        lo, hi = wilson(k, len(sub))
        rows.append({
            "period": period, "reviews": len(sub), "flagged": k,
            "flag_rate_%": round(100 * k / len(sub), 1) if len(sub) else None,
            "CI95_low_%": round(100 * lo, 1), "CI95_high_%": round(100 * hi, 1),
        })
    print(pd.DataFrame(rows).to_string(index=False))


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    df = pd.read_csv(IN_FILE, dtype=str, encoding="utf-8-sig")
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    if limit:
        df = df.head(limit).copy()
        print(f"TEST MODE: only the first {limit} reviews")

    texts = df[TEXT_COLUMN].fillna("").str.strip().tolist()
    df["word_count"] = [len(t.split()) for t in texts]
    df["text_source"] = df.apply(get_text_source, axis=1)

    done = load_progress()
    todo = [i for i in range(len(df)) if texts[i] and str(i) not in done]
    print(f"{len(df)} reviews | {len(done)} already scored | {len(todo)} to do")

    if todo:
        score = load_scorer()
        todo.sort(key=lambda i: len(texts[i]))      # similar lengths together = faster
        for n, start in enumerate(range(0, len(todo), BATCH_SIZE), 1):
            ids = todo[start:start + BATCH_SIZE]
            probs = score([texts[i] for i in ids])
            for i, p in zip(ids, probs):
                done[str(i)] = round(float(p), 4)
            if n % SAVE_EVERY_BATCHES == 0:
                save_progress(done)
                print(f"  scored {min(start + BATCH_SIZE, len(todo))}/{len(todo)}")
        save_progress(done)

    df["roberta_ai_prob"] = [done.get(str(i)) for i in range(len(df))]

    flags, confs = [], []
    for i in range(len(df)):
        p = df.at[df.index[i], "roberta_ai_prob"]
        if not texts[i] or p is None or pd.isna(p):
            flags.append("no_text")
            confs.append("low")
        else:
            flags.append("flagged" if p >= THRESHOLD else "non flagged")
            confs.append(make_confidence(df["word_count"].iloc[i], float(p)))
    df["Ai_flagged"] = flags
    df["confidence"] = confs

    df.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")
    print(f"\nSaved -> {OUT_FILE}")

    summarise(df, "VIEW 1: all reviews (short ones are noisy)")
    summarise(df[df["word_count"] >= 30], "VIEW 2: reviews with 30+ words (more reliable)")
    print("\nFlag rate by year, 30+ words only:")
    long_df = df[(df["word_count"] >= 30) & (df["Ai_flagged"] != "no_text")]
    print(long_df.groupby("year")["Ai_flagged"]
          .agg(reviews="size", flag_rate_pct=lambda s: round(100 * (s == "flagged").mean(), 1))
          .to_string())
    print("\nConfidence counts:")
    print(df["confidence"].value_counts().to_string())


if __name__ == "__main__":
    main()
"""
STEP 0 - Clean the dataset (remove rows that are not real, independent product reviews).

Reads  : combined_reviews_detected.csv         (same folder as this script)
Writes : combined_reviews_detected_clean.csv    kept rows, same columns as the input
         analysis/excluded_rows.csv             every removed row + the reason (so the cleaning is auditable)

Run:   python 00_clean_dataset.py

Rows are removed in this order (each row gets the FIRST reason that matches):
  1. duplicate_review_id   the scraper collected the same review twice
  2. request_or_question   "please restock", "when will it be available" (<= 15 words): not a review of the product
  3. no_letters            emoji / stars / numbers only (nothing for a text detector to read)
  4. exact_repeat_text     the same original text posted again ("good", "nice product" ...); first copy is kept

You do NOT need to re-run RoBERTa afterwards: removing rows does not change the score of the rows that stay.
(You only re-run the detector if the TEXT changes, e.g. you re-translate.)
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
IN_FILE = BASE / "combined_reviews_detected.csv"
OUT_FILE = BASE / "combined_reviews_detected_clean.csv"
EXC_FILE = BASE / "analysis" / "excluded_rows.csv"
(BASE / "analysis").mkdir(exist_ok=True)

REQUEST = (r"restock|re-stock|out of stock|back in stock|bring back|when will|"
           r"when (?:is|are) .* (?:available|coming)|please (?:add|bring|provide|stock)")

df = pd.read_csv(IN_FILE, encoding="utf-8-sig")
tr = df["translated_review_en"].fillna("").astype(str)
orig = df["review_text"].fillna("").astype(str).str.strip().str.lower()

reason = pd.Series("", index=df.index)
reason[df.review_id.duplicated()] = "duplicate_review_id"
m = (reason == "") & tr.str.lower().str.contains(REQUEST) & (df.word_count <= 15)
reason[m] = "request_or_question"
m = (reason == "") & (tr.str.count(r"[A-Za-z]") == 0)
reason[m] = "no_letters"
m = (reason == "") & orig.duplicated()
reason[m] = "exact_repeat_text"

df["exclude_reason"] = reason
keep = df[df.exclude_reason == ""].drop(columns="exclude_reason")
drop = df[df.exclude_reason != ""]
keep.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")
drop.to_csv(EXC_FILE, index=False, encoding="utf-8-sig")

print(f"Input rows: {len(df)}   kept: {len(keep)}   removed: {len(drop)}")
print(drop.exclude_reason.value_counts().to_string())
print("\nRows per platform and period, BEFORE -> AFTER cleaning")
b = df.groupby(["platform", "period"]).size().unstack()
a = keep.groupby(["platform", "period"]).size().unstack()
print((b.astype(str) + " -> " + a.astype(str)).to_string())
print(f"\nSaved {OUT_FILE.name} and {EXC_FILE}")
print("Next: python 01_baseline_analysis.py --input combined_reviews_detected_clean.csv --out analysis_clean")

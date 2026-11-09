"""Step 08: pick reviews for the language-bias check.

The check scores the SAME review written in Bangla, Banglish and English. If the
three versions get different scores, the only thing that changed is the language.

This script picks the reviews and writes a sheet with one row per review:
original_review holds the real review; translated_bangla, translated_banglish and
translated_english hold the three versions. The column of the review's own language
says "original"; the other two are left empty for the translations (by hand, or
step 08b).

  python scripts/08_make_language_set.py            # 30 reviews, 10 per language
  python scripts/08_make_language_set.py --per-language 5

Reviews come from the scored main sample, so each one already has a score from
the main run. Per language they are spread over low (up to 3.5), middle (4-6) and
high (6.5 and above) scores, and over platforms. Only reviews of 10-80 words are
used: shorter ones have too little to translate, longer ones are slow to check.
"""
import argparse, os
import pandas as pd
from common import ROOT

LANGS = ["bangla", "banglish", "english"]

ap = argparse.ArgumentParser()
ap.add_argument("--per-language", type=int, default=10)
ap.add_argument("--min-words", type=int, default=10)
ap.add_argument("--max-words", type=int, default=80)
ap.add_argument("--seed", type=int, default=7)
a = ap.parse_args()

out_dir = os.path.join(ROOT, "language_bias", "data")
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, "language_set.csv")
if os.path.exists(out_file):
    raise SystemExit(f"{out_file} already exists; it may hold translations. Delete it first to redraw.")

w = pd.read_csv(os.path.join(ROOT, "main", "results", "scores_wide.csv"))
w = w[w["n_words"].between(a.min_words, a.max_words) & w["language"].isin(LANGS)].copy()
w["band"] = pd.cut(w["mean"], [0, 3.5, 6, 10], labels=["low", "middle", "high"])

rows = []
for lang in LANGS:
    g = w[w["language"] == lang]
    per_band = {"low": a.per_language // 3, "middle": a.per_language // 3}
    per_band["high"] = a.per_language - per_band["low"] - per_band["middle"]
    for band, k in per_band.items():
        b = g[g["band"] == band]
        # spread over platforms: take one per platform in turn
        b = b.sample(frac=1, random_state=a.seed)
        b = b.assign(_r=b.groupby("platform").cumcount()).sort_values("_r")
        take = b.head(k)
        if len(take) < k:
            print(f"note: only {len(take)} {lang} reviews in the {band} band")
        rows.append(take)

s = pd.concat(rows)
sheet = pd.DataFrame({
    "item_id": [f"L{i + 1:02d}" for i in range(len(s))],
    "review_id": s["review_id"].values,
    "original_language": s["language"].values,
    "platform": s["platform"].values,
    "product_name": s["product_name"].values,
    "n_words": s["n_words"].values,
    "gemini_run1": s["run1"].values,
    "gemini_run2": s["run2"].values,
    "gemini_score": s["mean"].values,
    "gemini_reason": s["reason_run1"].values,
    "original_review": s["text_original"].values,
})
for lang in LANGS:
    sheet[f"translated_{lang}"] = ["original" if l == lang else "" for l in s["language"]]
sheet["translated_by"] = ""   # who wrote the translations (a name, "claude" or "gemini")
sheet["checked"] = ""      # set to "yes" once a team member has checked both translations
sheet["notes"] = ""
sheet.to_csv(out_file, index=False, encoding="utf-8-sig")

print(f"wrote {len(sheet)} reviews -> {out_file}")
print(sheet.groupby(["original_language", pd.cut(sheet["gemini_score"], [0, 3.5, 6, 10],
                    labels=["low", "middle", "high"])], observed=True).size().to_string())
print("\nNext: fill the empty translated_ columns (step 08b, or by hand), check them, and set checked = yes.")

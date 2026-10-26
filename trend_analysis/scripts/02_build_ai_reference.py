"""
Collect the AI-generated reviews in their ORIGINAL language (Bengali script, Banglish or English) as a
reference corpus for the trend analysis. No translation is used.

Sources (kept in archive/ from the earlier, translation-based approach):
  archive/week5_mixture_translated/data/ai_reference.csv, ai_validation.csv
      801 Gemini reviews, one per pre-2022 review (half rewrites, half new reviews from product + rating)
  archive/week4_translated_detector/analysis/labeled_set.csv  (rows with label = ai)
      148 Gemini rewrites of pre-2022 reviews made for the Week 4 detector test

Output: trend_analysis/data/ai_reference_original.csv
  ai_id, source_set, source_review_id, platform, prompt_type, model, language, n_words, keep,
  text_original, text_clean
  The text is cleaned and tagged with exactly the same functions as the real reviews (textutil.py).

Run from the repository root:  python trend_analysis/scripts/02_build_ai_reference.py
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import textutil as tu  # noqa: E402

ROOT = HERE.parents[1]
ARCHIVE = ROOT / "archive"
OUT = ROOT / "trend_analysis" / "data" / "ai_reference_original.csv"
MIN_WORDS = 5


def main():
    parts = []
    for half in ["reference", "validation"]:
        d = pd.read_csv(ARCHIVE / "week5_mixture_translated" / "data" / f"ai_{half}.csv", dtype=str)
        parts.append(pd.DataFrame({
            "source_set": f"week5_gemini_{half}", "source_review_id": d.review_id, "platform": d.platform,
            "prompt_type": d.prompt_type, "model": d.model, "text_original": d.review_text}))
    lab = pd.read_csv(ARCHIVE / "week4_translated_detector" / "analysis" / "labeled_set.csv",
                      dtype=str, encoding="utf-8-sig")
    lab = lab[lab.label_name == "ai"]
    parts.append(pd.DataFrame({
        "source_set": "week4_labeled_set", "source_review_id": lab.source_review_id, "platform": lab.platform,
        "prompt_type": "rewrite", "model": "gemini (week 4, model not recorded)",
        "text_original": lab.text_original}))

    ai = pd.concat(parts, ignore_index=True)
    ai["text_clean"] = ai.text_original.map(tu.clean_text)
    ai["n_words"] = ai.text_clean.map(lambda t: len(tu.words(t)))
    ai["language"] = ai.text_clean.map(tu.language_of)
    ai["keep"] = ai.n_words > MIN_WORDS
    ai.insert(0, "ai_id", [f"ai{i:04d}" for i in range(len(ai))])
    ai = ai[["ai_id", "source_set", "source_review_id", "platform", "prompt_type", "model", "language",
             "n_words", "keep", "text_original", "text_clean"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ai.to_csv(OUT, index=False, encoding="utf-8-sig")

    print(f"AI reviews: {len(ai)}   kept (> {MIN_WORDS} words): {ai.keep.sum()}")
    print(ai[ai.keep].groupby(["platform", "language"]).size().unstack(fill_value=0).to_string())
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()

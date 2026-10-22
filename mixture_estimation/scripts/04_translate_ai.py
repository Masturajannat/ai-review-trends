"""
Translate the Bangla / Banglish AI reviews to English with the SAME translator used for the real
reviews (translate_reviews_to_english.py in the main folder: free Bing/Google translators, then
deep-translator, then MyMemory). Using the same translator on both sides matters: otherwise the
estimator could pick up "translation style" instead of "AI style".

Original-English AI reviews are kept as they are, exactly like the real data.

RUN (from the ai-review-trends folder, no API key needed)
  python mixture_estimation\\scripts\\04_translate_ai.py

Safe to stop and run again: finished translations are cached in data/ai_translation_cache.json,
and the pilot_ai_*.csv files are updated in place (only the translated_review_en column).
"""
import json
import sys
from pathlib import Path

import pandas as pd

MAIN = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent.parent / "data"
CACHE = DATA / "ai_translation_cache.json"
ENGINES = ["bing", "google"]          # same default as translate_reviews_to_english.py

sys.path.insert(0, str(MAIN))
import translate_reviews_to_english as tr   # importing does not run it


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for half in ["reference", "validation"]:
        path = DATA / f"pilot_ai_{half}.csv"
        df = pd.read_csv(path, dtype={"review_id": str, "translated_review_en": str})
        df["translated_review_en"] = df["translated_review_en"].fillna("")
        # English rows: copy as they are (this is what the real data did)
        eng = df.text_source == "original_english"
        df.loc[eng, "translated_review_en"] = df.loc[eng, "review_text"]

        todo = df.index[~eng & (df.translated_review_en.str.strip() == "")]
        print(f"\n{half}: {len(todo)} reviews to translate")
        failed = 0
        for k, i in enumerate(todo, 1):
            text = tr.normalize_spaces(df.at[i, "review_text"])
            key = tr.cache_key(text)
            out = cache.get(key, "")
            if not out:
                try:
                    out = tr.translate_text_to_english(text, ENGINES)
                except Exception as exc:  # noqa: BLE001
                    tr.safe_print(f"  [{k}/{len(todo)}] failed: {str(exc)[:100]}")
                    failed += 1
                    out = ""
                if out:
                    cache[key] = out
            df.at[i, "translated_review_en"] = out
            if k % 10 == 0 or k == len(todo):
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"  {k}/{len(todo)} done")

        try:
            df.to_csv(path, index=False, encoding="utf-8")
        except PermissionError:
            sys.exit(f"{path.name} is open in another program (Excel?). Close it and run again.")
        filled = (df.translated_review_en.str.strip() != "").sum()
        print(f"{half}: {filled}/{len(df)} have English text"
              + (f"  ({failed} failed - just run again)" if failed else ""))
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

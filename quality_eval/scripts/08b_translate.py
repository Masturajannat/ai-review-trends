"""Step 08b (optional): draft the missing translations with Gemini.

Fills only EMPTY translated_ cells of language_bias/data/language_set.csv and sets
translated_by to "gemini" for those rows. Cells already filled (by hand or by an
earlier run) are never changed. The drafts must then be checked by a team member,
who corrects them if needed and sets checked = yes; step 09 scores only checked rows.

  set GEMINI_API_KEY (environment variable, never commit it)
  python scripts/08b_translate.py

A translation must carry exactly the same information as the original: no detail
added, removed or made more precise, and the same tone. Otherwise a score difference
could come from the translation rather than from the language.
"""
import argparse, os, time
import pandas as pd
from common import ROOT

LANGS = ["bangla", "banglish", "english"]
STYLE = {
    "bangla": "Bangla in Bengali script, in the everyday style of an online customer review "
              "(not formal or literary Bangla)",
    "banglish": "Banglish: Bangla written in English letters, the way Bangladeshi customers "
                "type it online (informal spelling such as 'onek valo', 'khub', 'dam', "
                "English words kept as they are)",
    "english": "plain English, in the style of an online customer review",
}
PROMPT = """Translate this customer review into {style}.

Rules:
- Keep exactly the same information: do not add, remove, explain or correct any detail.
- Keep the same tone, level of detail, and roughly the same length.
- Keep product names, numbers, prices and units as they are.
- Do not fix the reviewer's opinions or make the review sound better or worse.
- Reply with the translated review only, no quotes and no comments.

Review:
{text}"""

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="gemini-3.5-flash-lite")
ap.add_argument("--pause", type=float, default=4.5)
a = ap.parse_args()

path = os.path.join(ROOT, "language_bias", "data", "language_set.csv")
d = pd.read_csv(path, dtype=str, keep_default_na=False)


def ask(client, prompt):
    for i in range(5):
        try:
            r = client.models.generate_content(model=a.model, contents=prompt,
                                               config={"temperature": 0})
            text = (r.text or "").strip().strip('"').strip()
            if text:
                return text
        except Exception as e:
            print("  retry", i + 1, "-", str(e)[:100])
        time.sleep(10 * (i + 1))
    return None


def main():
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    for i, row in d.iterrows():
        for lang in LANGS:
            if row[f"translated_{lang}"].strip():          # "original" or already translated
                continue
            text = ask(client, PROMPT.format(style=STYLE[lang], text=row["original_review"]))
            if text is None:
                print(f"{row['item_id']} {lang}: failed, run again later")
                continue
            d.at[i, f"translated_{lang}"] = text
            d.at[i, "translated_by"] = (row["translated_by"] + ", gemini").strip(", ") \
                if "gemini" not in row["translated_by"] else row["translated_by"]
            d.to_csv(path, index=False, encoding="utf-8-sig")      # save after every translation
            print(f"{row['item_id']} {row['original_language']} -> {lang}: done")
            time.sleep(a.pause)
    print("\nNow check every translation in", path, "and set checked = yes for each row.")


if __name__ == "__main__":
    main()

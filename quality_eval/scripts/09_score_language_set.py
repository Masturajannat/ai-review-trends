"""Step 09: score every language version of every checked review.

Uses the same prompt, model and settings as the main run (step 03), so the scores
are comparable. Each call is separate and contains only the prompt, the product name
and ONE language version of the review: Gemini never sees the original review, the
other versions, the earlier scores or which version is the original. Each version is scored --runs times. Only ever appends to
language_bias/results/scores_raw.csv; rerunning skips scores that already exist.

  set GEMINI_API_KEY (environment variable, never commit it)
  python scripts/09_score_language_set.py --runs 2
  python scripts/09_score_language_set.py --runs 2 --language bangla    # one language at a time
  python scripts/09_score_language_set.py --show-prompts 3              # see what Gemini receives

Reads language_bias/data/language_set.xlsx (or language_set.csv if there is no .xlsx;
reading .xlsx needs: pip install openpyxl).

30 reviews x 3 languages x 2 runs = 180 calls, about 15-20 minutes on the free tier.
"""
import argparse, json, os, time
import pandas as pd
from common import ROOT

LANGS = ["bangla", "banglish", "english"]

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=2)
ap.add_argument("--prompt", default="prompt_v2.txt")
ap.add_argument("--model", default="gemini-3.5-flash-lite")
ap.add_argument("--pause", type=float, default=4.5)
ap.add_argument("--language", choices=LANGS, default=None,
                help="score only this language version (e.g. all Bangla versions first)")
ap.add_argument("--show-prompts", type=int, default=0,
                help="print the first N prompts exactly as Gemini would receive them, then stop (no API call)")
ap.add_argument("--allow-unchecked", action="store_true",
                help="also score rows not marked checked = yes (for a trial run only)")
a = ap.parse_args()

base = os.path.join(ROOT, "language_bias")
# the Excel sheet (language_set.xlsx) is used if present, otherwise the csv
sheet_xlsx = os.path.join(base, "data", "language_set.xlsx")
sheet_csv = os.path.join(base, "data", "language_set.csv")
out_file = os.path.join(base, "results", "scores_raw.csv")
os.makedirs(os.path.dirname(out_file), exist_ok=True)
template = open(os.path.join(ROOT, "prompts", a.prompt), encoding="utf-8").read()
version = os.path.splitext(a.prompt)[0]


def build(product, text):
    return template.replace("{product_name}", str(product)).replace("{review_text}", str(text))


def parse(text):
    j = json.loads(text)
    overall = int(j["overall"])
    if not 1 <= overall <= 10:
        raise ValueError("overall out of range")
    return overall, str(j.get("reason", ""))


def ask(client, prompt):
    for i in range(5):
        try:
            r = client.models.generate_content(
                model=a.model, contents=prompt,
                config={"temperature": 0, "response_mime_type": "application/json"})
            return parse(r.text)
        except Exception as e:
            print("  retry", i + 1, "-", str(e)[:100])
            time.sleep(10 * (i + 1))
    return None


def main():
    if os.path.exists(sheet_xlsx):
        # row 1 holds readable labels, row 2 the column names used here
        d = pd.read_excel(sheet_xlsx, sheet_name="Reviews", header=1, dtype=str).fillna("")
        print("reading", sheet_xlsx)
    else:
        d = pd.read_csv(sheet_csv, dtype=str, keep_default_na=False)
        print("reading", sheet_csv)
    d = d[d["item_id"].str.strip() != ""]
    if not a.allow_unchecked:
        d = d[d["checked"].str.strip().str.lower() == "yes"]
    missing = [(r.item_id, l) for r in d.itertuples() for l in LANGS if not getattr(r, f"translated_{l}").strip()]
    if missing:
        raise SystemExit(f"missing translations, fill them first: {missing[:10]}")
    if d.empty:
        raise SystemExit("no rows to score: set checked = yes for the rows whose translations are checked")

    langs = [a.language] if a.language else LANGS

    if a.show_prompts:
        shown = 0
        for r in d.itertuples():
            for lang in langs:
                cell = getattr(r, f"translated_{lang}")
                text = r.original_review if cell.strip().lower() == "original" else cell
                print(f"===== {r.item_id} / {lang} =====\n{build(r.product_name, text)}\n")
                shown += 1
                if shown >= a.show_prompts:
                    return
        return

    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    done, exists = set(), os.path.exists(out_file)
    if exists:
        old = pd.read_csv(out_file, dtype=str)
        done = set(zip(old["item_id"], old["language"], old["run"].astype(int), old["prompt_version"]))

    total = len(d) * len(langs) * a.runs
    k = 0
    for run in range(1, a.runs + 1):
        for r in d.itertuples():
            for lang in langs:
                k += 1
                if (r.item_id, lang, run, version) in done:
                    continue
                cell = getattr(r, f"translated_{lang}")
                is_original = cell.strip().lower() == "original"
                res = ask(client, build(r.product_name, r.original_review if is_original else cell))
                if res is None:
                    continue           # picked up on the next launch
                rec = dict(item_id=r.item_id, review_id=r.review_id, language=lang,
                           source_language=r.original_language,
                           text_source="original" if is_original else (r.translated_by or "hand"),
                           run=run, overall=res[0], reason=res[1], model=a.model,
                           prompt_version=version)
                pd.DataFrame([rec]).to_csv(out_file, mode="a", header=not exists, index=False,
                                           encoding="utf-8-sig")
                exists = True
                print(f"run {run}  {k}/{total}  {r.item_id} {lang:8s} -> {res[0]}")
                time.sleep(a.pause)


if __name__ == "__main__":
    main()

"""
Make one AI review for every human review in the pilot files.

RUN (PowerShell, from the ai-review-trends folder)
  Gemini (free tier, the default):
    $env:GEMINI_API_KEY="your-key"
    python mixture_estimation\\scripts\\03_generate_ai.py --provider gemini --limit 4   # quick test
    python mixture_estimation\\scripts\\03_generate_ai.py --provider gemini             # full pilot
  OpenAI (needs credits):
    $env:OPENAI_API_KEY="your-key"
    python mixture_estimation\\scripts\\03_generate_ai.py --provider openai

Safe to stop (Ctrl+C) and run again: every finished review is saved at once, and a new run
only does the reviews that are still missing. Failed requests are never saved as blank rows.
If the API runs out of quota the script stops and tells you; run it again later.
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
DEFAULT_MODEL = {"openai": "gpt-4o-mini", "gemini": "gemini-3.5-flash-lite"}
PAUSE = {"openai": 1.0, "gemini": 4.5}     # seconds between calls (Gemini free tier is rate limited)

# prompt A: rewrite the human review
PROMPT_REWRITE = (
    "Rewrite this customer review of a product bought online in Bangladesh. "
    "Keep the same meaning. {lang_rule} "
    "Write it the way ChatGPT would. About {n} words. Output only the review.\n\n"
    "Review: {text}"
)

# prompt B: write a new review from the product details only
# (the rating line is left out when the review has no rating, e.g. most Rokomari reviews)
PROMPT_NEW = (
    "Write a new customer review for this product bought online in Bangladesh.\n"
    "Product: {product}\n{rating_line}"
    "{lang_rule} Do not copy the sample below. "
    "About {n} words. Output only the review.\n\n"
    "Sample: {text}"
)


BENGALI = re.compile(r"[\u0980-\u09FF]")
LATIN = re.compile(r"[A-Za-z]")
LANG_RULE = {
    "bangla": "Write it in Bangla using Bengali script (not English letters).",
    "banglish": "Write it in Banglish: Bengali language written in English letters "
                "(like 'product ta khub valo'). Do not write it in English and do not use Bengali script.",
    "english": "Write it in English only. Do not use Bengali script or Banglish.",
}


def language_of(review):
    """Language of the human review: bangla (Bengali script), banglish, or english."""
    t = str(review.review_text)
    if len(BENGALI.findall(t)) > len(LATIN.findall(t)):
        return "bangla"
    return "english" if review.text_source == "original_english" else "banglish"


def script_ok(text, lang):
    """Rough check that the AI text is in the right script (Banglish vs English can't be told apart)."""
    b, l = len(BENGALI.findall(text)), len(LATIN.findall(text))
    return b > l if lang == "bangla" else l > b


class OutOfQuota(Exception):
    pass


def call_openai(prompt, model):
    key = os.getenv("OPENAI_API_KEY")
    r = requests.post("https://api.openai.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key}"}, timeout=60,
                      json={"model": model, "messages": [{"role": "user", "content": prompt}]})
    if r.status_code == 429 and "insufficient_quota" in r.text:
        raise OutOfQuota("OpenAI account has no credits left")
    if r.status_code in (401, 403):
        raise OutOfQuota("OpenAI rejected the key (wrong, revoked or no access). Check OPENAI_API_KEY")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def call_gemini(prompt, model):
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(url, headers={"x-goog-api-key": key}, timeout=60,
                      json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]})
    if r.status_code in (400, 401, 403) and "API_KEY" in r.text.upper():
        raise OutOfQuota("Gemini rejected the key. Check GEMINI_API_KEY")
    if r.status_code == 404:
        sys.exit(f"Gemini model '{model}' not found. Try --model gemini-3.8-flash")
    r.raise_for_status()
    cands = r.json().get("candidates") or []
    parts = (cands[0].get("content", {}).get("parts") or []) if cands else []
    return "".join(p.get("text", "") for p in parts).strip()


def ask(call, prompt, model, tries=5):
    """Try a few times (waiting longer each time). Returns "" if every try failed."""
    for attempt in range(tries):
        try:
            text = call(prompt, model)
            if text:
                return text
            print("  empty answer, retrying")
        except OutOfQuota:
            raise
        except Exception as e:  # busy, rate limited, network ...
            print(f"  retry {attempt + 1}/{tries}: {str(e)[:150]}")
        time.sleep(10 * (attempt + 1))
    return ""


def make_prompt(i, r):
    # alternate the two prompts so half the AI reviews come from each
    kind = "rewrite" if i % 2 == 0 else "new"
    n = max(int(r.word_count), 3) if pd.notna(r.word_count) else 20
    rule = LANG_RULE[language_of(r)]
    if kind == "rewrite":
        return kind, PROMPT_REWRITE.format(n=n, text=r.review_text, lang_rule=rule)
    rating_line = f"Rating: {r.rating:g} out of 5\n" if pd.notna(r.rating) else ""
    return kind, PROMPT_NEW.format(product=r.product_name, rating_line=rating_line, n=n,
                                   text=r.review_text, lang_rule=rule)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["openai", "gemini"], default="gemini")
    ap.add_argument("--model", default=None, help="default: gpt-4o-mini / gemini-3.5-flash-lite")
    ap.add_argument("--limit", type=int, default=None, help="test mode: only this many reviews per half")
    args = ap.parse_args()

    key_name = "OPENAI_API_KEY" if args.provider == "openai" else "GEMINI_API_KEY"
    if not (os.getenv(key_name) or (args.provider == "gemini" and os.getenv("GOOGLE_API_KEY"))):
        sys.exit(f'{key_name} is not set. In PowerShell first run:  $env:{key_name}="your-key"')
    call = call_openai if args.provider == "openai" else call_gemini
    model = args.model or DEFAULT_MODEL[args.provider]
    print(f"Provider: {args.provider}   model: {model}")

    for half in ["reference", "validation"]:
        human = pd.read_csv(DATA / f"pilot_human_{half}.csv", dtype={"review_id": str})
        out_file = DATA / f"pilot_ai_{half}.csv"
        done = pd.read_csv(out_file, dtype={"review_id": str}) if out_file.exists() else pd.DataFrame()
        done_ids = set(done.review_id) if len(done) else set()
        todo = [(i, r) for i, r in enumerate(human.itertuples()) if r.review_id not in done_ids]
        if args.limit:
            todo = todo[:args.limit]
        print(f"\n{half}: {len(done_ids)} already done, {len(todo)} to make")

        for k, (i, r) in enumerate(todo, 1):
            kind, prompt = make_prompt(i, r)
            lang = language_of(r)
            text = ""
            try:
                for _ in range(3):                     # ask again if it answers in the wrong language
                    text = ask(call, prompt, model)
                    if not text or script_ok(text, lang):
                        break
                    print(f"  wrong language (wanted {lang}), asking again")
                    text = ""
            except OutOfQuota as e:
                sys.exit(f"\nSTOPPED: {e}. Everything finished so far is saved in {out_file.name}.")
            if not text:
                print(f"  [{k}/{len(todo)}] {r.review_id}: failed, skipped (run again later to retry)")
                continue
            row = pd.DataFrame([{
                "review_id": r.review_id,          # id of the human review it was made from
                "platform": r.platform,
                "text_source": r.text_source,
                "prompt_type": kind,
                "language": lang,
                "provider": args.provider,
                "model": model,
                "review_text": text,
                # English reviews need no translation, Bangla ones are filled in later
                "translated_review_en": text if r.text_source == "original_english" else "",
            }])
            # append this one row right away, so nothing is lost if the run stops
            row.to_csv(out_file, mode="a", header=not out_file.exists(), index=False, encoding="utf-8")
            print(f"  [{k}/{len(todo)}] {r.review_id} ({kind}) ok")
            time.sleep(PAUSE[args.provider])

        total = len(pd.read_csv(out_file)) if out_file.exists() else 0
        print(f"{half} done: {total}/{len(human)} AI reviews in {out_file.name}")


if __name__ == "__main__":
    main()

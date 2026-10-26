"""
Make one AI review for every human review.

  default : the 100 + 100 pilot reviews  (pilot_human_*.csv -> pilot_ai_*.csv)
  --full  : ALL pre-2022 reviews          (human_*.csv -> ai_*.csv, about 800)
            The 200 pilot AI reviews are copied in first, so they are not made again.

RUN (PowerShell, from the ai-review-trends folder)
  Gemini (free tier, the default):
    $env:GEMINI_API_KEY="your-key"
    python mixture_estimation\\scripts\\03_generate_ai.py --provider gemini --limit 4   # quick test
    python mixture_estimation\\scripts\\03_generate_ai.py --provider gemini             # full pilot
    python mixture_estimation\\scripts\\03_generate_ai.py --full                        # all ~800 reviews
  OpenAI (needs credits):
    $env:OPENAI_API_KEY="your-key"
    python mixture_estimation\\scripts\\03_generate_ai.py --provider openai

Safe to stop (Ctrl+C) and run again: every finished review is saved at once, and a new run
only does the reviews that are still missing. Failed requests are never saved as blank rows.
If the API runs out of quota (or Gemini's free daily limit is reached) the script stops and tells
you; run the same command again later (Gemini's daily limit resets the next day).
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


class RateLimited(Exception):
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
    if r.status_code == 429:
        raise RateLimited(f"429 Too Many Requests: {r.text[:120]}")
    if r.status_code == 404:
        sys.exit(f"Gemini model '{model}' not found. Try --model gemini-3.8-flash")
    r.raise_for_status()
    cands = r.json().get("candidates") or []
    parts = (cands[0].get("content", {}).get("parts") or []) if cands else []
    return "".join(p.get("text", "") for p in parts).strip()


def ask(call, prompt, model, tries=5):
    """Try a few times (waiting longer each time). Returns "" if every try failed.
    If EVERY try is refused with 429 (too many requests), the free daily limit is probably used up:
    stop instead of skipping review after review."""
    limited = 0
    for attempt in range(tries):
        try:
            text = call(prompt, model)
            if text:
                return text
            print("  empty answer, retrying")
        except OutOfQuota:
            raise
        except RateLimited as e:
            limited += 1
            print(f"  rate limited {attempt + 1}/{tries}, waiting")
        except Exception as e:  # busy, network ...
            print(f"  retry {attempt + 1}/{tries}: {str(e)[:150]}")
        time.sleep(15 * (attempt + 1))
    if limited == tries:
        raise OutOfQuota("the API kept answering 429 (limit reached, probably the free daily limit). "
                         "Run the same command again later or tomorrow")
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
    ap.add_argument("--full", action="store_true",
                    help="all pre-2022 reviews (human_*.csv -> ai_*.csv) instead of the 100+100 pilot")
    args = ap.parse_args()

    key_name = "OPENAI_API_KEY" if args.provider == "openai" else "GEMINI_API_KEY"
    if not (os.getenv(key_name) or (args.provider == "gemini" and os.getenv("GOOGLE_API_KEY"))):
        sys.exit(f'{key_name} is not set. In PowerShell first run:  $env:{key_name}="your-key"')
    call = call_openai if args.provider == "openai" else call_gemini
    model = args.model or DEFAULT_MODEL[args.provider]
    print(f"Provider: {args.provider}   model: {model}")

    for half in ["reference", "validation"]:
        prefix_in, prefix_out = ("human", "ai") if args.full else ("pilot_human", "pilot_ai")
        human = pd.read_csv(DATA / f"{prefix_in}_{half}.csv", dtype={"review_id": str})
        out_file = DATA / f"{prefix_out}_{half}.csv"
        pilot_file = DATA / f"pilot_ai_{half}.csv"
        if args.full and not out_file.exists() and pilot_file.exists():
            # reuse the pilot AI reviews (same human reviews), so they are not generated again
            pilot = pd.read_csv(pilot_file, dtype={"review_id": str})
            pilot = pilot[pilot.review_id.isin(human.review_id)]
            pilot.to_csv(out_file, index=False, encoding="utf-8")
            print(f"Copied {len(pilot)} pilot AI reviews into {out_file.name}")
        done = pd.read_csv(out_file, dtype={"review_id": str}) if out_file.exists() else pd.DataFrame()
        done_ids = set(done.review_id) if len(done) else set()
        todo = [(i, r) for i, r in enumerate(human.itertuples()) if r.review_id not in done_ids]
        if args.limit:
            todo = todo[:args.limit]
        print(f"\n{half}: {len(done_ids)} already done, {len(todo)} to make")

        fails_in_row = 0
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
                fails_in_row += 1
                if fails_in_row >= 5:
                    sys.exit("\nSTOPPED: 5 reviews in a row failed. The API is probably down or limited. "
                             f"Everything finished so far is saved in {out_file.name}; run again later.")
                continue
            fails_in_row = 0
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

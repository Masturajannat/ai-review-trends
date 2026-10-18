"""
STEP 2 - Build a labeled test set (known human vs known AI).

RUN
  python 02_build_labeled_set.py --limit 6     # tiny test first
  python 02_build_labeled_set.py               # full run
  (if you used other numbers the first time, e.g. --n-translated 120, use THE SAME numbers again)

Safe to stop (Ctrl+C) and re-run: finished rows are cached in analysis/labeled_cache.json.
Set the key first in the same terminal:
  PowerShell: $env:GEMINI_API_KEY="your-key"
  cmd:        set GEMINI_API_KEY=your-key
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
OUT = BASE / "analysis"
OUT.mkdir(exist_ok=True)
IN_FILE = BASE / "combined_reviews_detected_clean.csv"   # made by 00_clean_dataset.py
CACHE_FILE = OUT / "labeled_cache.json"
OUT_FILE = OUT / "labeled_set.csv"

BENGALI = re.compile(r"[ঀ-৿]")
BANGLISH = re.compile(r"(?i)\b(valo|bhalo|khub|onek|onk|kore|korar|moto|darun|lagse|lagche|jinish|ekta|ei|eta|"
                      r"amar|amr|jonno|kintu|ektu|thakle|hoyeche|hoise|chilo|silo|nai|theke|diye|dise|"
                      r"pelam|peyechi|kinlam|dam|dami|sundor|shundor)\b")
API_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = (
    "You write product reviews the way an AI chatbot such as ChatGPT would write them for a fake-review "
    "campaign. You are given one real customer review. Write ONE new review with the same meaning, "
    "sentiment and details, in the SAME language and script as the original (Bengali stays Bengali script, "
    "Banglish stays Banglish, English stays English), and about the same length. Do not add a title, "
    "quotes, hashtags or explanations. Output only the review text."
)

# Used for reviews that were originally English. Those texts are NOT translated afterwards, so the
# rewrite must itself be English. (Gemini sometimes switched to Bengali/Banglish with the prompt above.)
SYSTEM_PROMPT_EN = (
    "You write product reviews the way an AI chatbot such as ChatGPT would write them for a fake-review "
    "campaign. You are given one real customer review written in English. Write ONE new review with the "
    "same meaning, sentiment and details, about the same length. The new review MUST be written in English "
    "only: never use Bengali script and never write Bengali words in English letters. Do not translate it "
    "into any other language. Do not add a title, quotes, hashtags or explanations. Output only the review text."
)

TRANSLATE_PROMPT = (
    "Translate this product review into English. Keep the meaning, tone, emojis and any mistakes or "
    "roughness. Do not improve, polish, shorten or explain. The text may be Bengali script or Bengali "
    "written in English letters (Banglish). Output only the translation."
)


def looks_bengali(text):
    """True if the text is Bengali script, or Banglish (Bengali written in English letters)."""
    t = str(text)
    return bool(BENGALI.search(t)) or len(BANGLISH.findall(t)) >= 2


def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"ai": {}, "tr": {}}


def save_cache(cache):
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE_FILE)


def call_openai(text, model, api_key, system=SYSTEM_PROMPT, temp=0.8):
    import requests
    body = {"model": model, "temperature": temp,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": text}]}
    for attempt in range(6):
        try:
            r = requests.post(API_URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=60)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001
            if attempt == 5:
                print(f"  OpenAI failed: {exc}")
                return ""
            time.sleep(2 ** attempt)
    return ""


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_PAUSE = 4.5   # seconds between calls, keeps us under the free-tier limit


def call_gemini(text, model, api_key, system=SYSTEM_PROMPT, temp=0.8):
    import requests
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"temperature": temp}}
    out = ""
    for attempt in range(4):
        try:
            r = requests.post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": api_key},
                              json=body, timeout=30)
            if r.status_code == 404:
                print(f"  Gemini model '{model}' not found (404). Try --model gemini-3.8-flash")
                break
            if r.status_code in (429, 500, 503):
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            cands = r.json().get("candidates") or []
            parts = (cands[0].get("content", {}).get("parts") or []) if cands else []
            out = "".join(p.get("text", "") for p in parts).strip()
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                print(f"  Gemini failed: {exc}")
            time.sleep(5)
    time.sleep(GEMINI_PAUSE)
    return out


def translate(llm, text, model, api_key):
    """Bengali/Banglish -> English with the same LLM. Returns "" on failure (blanks are not cached)."""
    out = llm(text, model, api_key, TRANSLATE_PROMPT, 0.2)
    return re.sub(r"\s+", " ", out or "").strip()


def rewrite(llm, text, path, model, api_key):
    """AI-style rewrite. English-path rewrites must stay English: retry, and give up (pair skipped) if not."""
    if path != "english":
        return llm(text, model, api_key)
    for _ in range(3):
        out = llm(text, model, api_key, SYSTEM_PROMPT_EN)
        if out and not looks_bengali(out):
            return out
    return ""


def sample_humans(df, n_translated, n_english, min_words_tr, min_words_en, seed):
    pre = df[(df.period == "pre_2022") & df.review_text.notna()].copy()
    pre["review_text"] = pre.review_text.astype(str).str.strip()
    pre = pre[pre.review_text != ""]
    tr = pre[(pre.text_source == "translated") & (pre.word_count >= min_words_tr)]
    en = pre[(pre.text_source == "original_english") & (pre.word_count >= min_words_en)]
    tr = tr.sample(n=min(n_translated, len(tr)), random_state=seed)
    en = en.sample(n=min(n_english, len(en)), random_state=seed)
    print(f"Eligible pre-2022 reviews: translated={len(tr)} (>= {min_words_tr} words), "
          f"original English={len(en)} (>= {min_words_en} words)")
    tr = tr.assign(path="translated")
    en = en.assign(path="english")
    return pd.concat([tr, en], ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-translated", type=int, default=250, help="human reviews from the Bengali/Banglish path")
    ap.add_argument("--n-english", type=int, default=100, help="human reviews that were originally English")
    ap.add_argument("--min-words-translated", type=int, default=10)
    ap.add_argument("--min-words-english", type=int, default=5)
    ap.add_argument("--provider", choices=["gemini", "openai"], default="gemini")
    ap.add_argument("--model", default=None,
                    help="default: gemini-3.5-flash-lite (gemini) or gpt-4o-mini (openai). "
                         "If Gemini says 404, try gemini-3.8-flash.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=None, help="test mode: only this many pairs")
    args = ap.parse_args()

    if args.provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        model = args.model or "gemini-3.5-flash-lite"
        llm, workers = call_gemini, 1
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        model = args.model or "gpt-4o-mini"
        llm, workers = call_openai, 6
    if not api_key:
        sys.exit("API key is not set (GEMINI_API_KEY, or OPENAI_API_KEY with --provider openai). "
                 "See the instructions at the top of this file.")

    df = pd.read_csv(IN_FILE, encoding="utf-8-sig")
    humans = sample_humans(df, args.n_translated, args.n_english, args.min_words_translated,
                           args.min_words_english, args.seed)
    if args.limit:
        humans = humans.groupby("path", group_keys=False).head(max(1, args.limit // 2)).reset_index(drop=True)
        print(f"TEST MODE: {len(humans)} pairs")

    cache = load_cache()
    humans["pair_id"] = [f"p{i:04d}" for i in range(len(humans))]
    humans["rid"] = humans.review_id.astype(str)

    # ---- 2a: AI rewrites ----
    todo = [(r.pair_id, r.review_text, r.path) for r in humans.itertuples()
            if r.pair_id + "|" + r.rid not in cache["ai"]]
    print(f"AI rewrites to generate: {len(todo)}")

    def job(item):
        pid, text, path = item
        return pid, rewrite(llm, text, path, model, api_key)

    rid_of = dict(zip(humans.pair_id, humans.rid))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for n, (pid, out) in enumerate(ex.map(job, todo), 1):
            if out:
                cache["ai"][pid + "|" + rid_of[pid]] = out
            if n % 5 == 0:
                save_cache(cache)
                print(f"  rewrites {n}/{len(todo)}")
    save_cache(cache)

    # ---- 2b: same translator (the LLM) for human and AI text (Bengali/Banglish path only) ----
    rows = []
    n_tr = 0
    for r in humans.itertuples():
        key = r.pair_id + "|" + r.rid
        ai_orig = cache["ai"].get(key, "")
        if not ai_orig:
            continue
        if r.path == "translated":
            for tag, txt in (("h", r.review_text), ("a", ai_orig)):
                k = key + "|" + tag
                if not cache["tr"].get(k):                 # retry anything blank or missing
                    result = translate(llm, txt, model, api_key)
                    if result:                             # only save real translations
                        cache["tr"][k] = result
                    n_tr += 1
                    if n_tr % 20 == 0:
                        save_cache(cache)
                        print(f"  translated {n_tr}")
            h_det = cache["tr"].get(key + "|h", "")
            a_det = cache["tr"].get(key + "|a", "")
        else:
            h_det, a_det = r.review_text, ai_orig
        if not h_det or not a_det:
            continue

        if h_det.strip().lower() == a_det.strip().lower():   # Gemini copied the text instead of rewriting
            continue
        common = dict(pair_id=r.pair_id, path=r.path, platform=r.platform, rating=r.rating,
                      source_review_id=r.rid)
        rows.append({**common, "label": 0, "label_name": "human", "text_original": r.review_text,
                     "text_for_detector": h_det})
        rows.append({**common, "label": 1, "label_name": "ai", "text_original": ai_orig,
                     "text_for_detector": a_det})
    save_cache(cache)

    out = pd.DataFrame(rows)
    if out.empty:
        sys.exit("No pairs were built (rewrites or translations failed). Wait 30 minutes and run again.")
    out["word_count"] = out.text_for_detector.str.split().str.len()
    out.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")
    print(f"\nSaved {len(out)} rows ({out.pair_id.nunique()} pairs) -> {OUT_FILE}")
    print(out.groupby(["path", "label_name"]).size().unstack())
    print("\nSPOT-CHECK a few pairs by eye before moving on (open the CSV and read text_original):")
    for pid in out.pair_id.drop_duplicates().head(3):
        s = out[out.pair_id == pid]
        print(f"  [{pid}] HUMAN: {s[s.label == 0].text_original.iloc[0][:150]!r}")
        print(f"  [{pid}] AI   : {s[s.label == 1].text_original.iloc[0][:150]!r}")


if __name__ == "__main__":
    main()
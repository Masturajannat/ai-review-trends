import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# `translators` pings httpbin.org at import time and crashes if that fails.
os.environ.setdefault("translators_default_region", "EN")


DEFAULT_INPUT = "combined_reviews.csv"
DEFAULT_OUTPUT = "combined_reviews_translated.csv"
DEFAULT_CACHE = "translation_cache.json"
DEFAULT_BATCH_INPUT = "translation_batch_input.jsonl"
DEFAULT_JOB = "translation_batch_job.json"
TRANSLATED_COLUMN = "translated_review_en"
API_BASE = "https://api.openai.com/v1"
BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
BANGLISH_RE = re.compile(
    r"(?i)\b("
    r"ta|tader|pura|baka|hoye|hoyeche|hoise|hoiche|gace|geche|chilo|silo|"
    r"kore|onek|onk|khub|valo|bhalo|baje|nai|kintu|diye|dise|disilo|"
    r"niben|paren|parben|eita|eta|ota|ami|amar|amr|theke|jonno|shob|sobai|"
    r"packeting|antorik|jhamela|nen|nile|chace|botol|dami"
    r")\b"
)
MAX_CHUNK = 4500


def normalize_spaces(text):
    if pd.isna(text):
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def cache_key(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def resolve_path(base, value):
    path = Path(value)
    return path if path.is_absolute() else base / path


def load_cache(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    # Previous runs cached failed empty strings. Never reuse those.
    return {
        key: value
        for key, value in data.items()
        if isinstance(value, str) and value.strip()
    }


def save_cache(path, cache):
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def chunk_text(text, max_chars=MAX_CHUNK):
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        cut = remaining.rfind(" ", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [chunk for chunk in chunks if chunk]


def looks_translated(source, translated):
    translated = normalize_spaces(translated)
    if not translated:
        return False
    if BENGALI_RE.search(translated):
        return False
    if BANGLISH_RE.search(source) and BANGLISH_RE.search(translated):
        return False
    source_words = len(source.split())
    translated_words = len(translated.split())
    if BENGALI_RE.search(source) and source_words >= 12 and translated_words < max(6, int(source_words * 0.5)):
        return False
    return True



# ---------------------------------------------------------------------------
# Translation backends
# ---------------------------------------------------------------------------
MYMEMORY_MAX = 450          # MyMemory rejects queries over 500 chars
BACKEND_FAIL_LIMIT = 5      # consecutive errors before a backend is switched off
_failures = {}              # backend name -> consecutive error count
_disabled = {}              # backend name -> reason
_translators_fn = None


def safe_print(*parts):
    """print() that never crashes on Windows consoles that can't show Bengali/emoji."""
    try:
        print(*parts)
    except UnicodeEncodeError:
        print(*(str(p).encode("ascii", "replace").decode() for p in parts))


def disable_backend(name, reason):
    if name not in _disabled:
        _disabled[name] = reason
        safe_print(f"[backend off] {name}: {reason}")


def get_translators_fn():
    """Import `translators` lazily. Its import does network calls and can raise."""
    global _translators_fn
    if _translators_fn is None:
        from translators import translate_text  # may raise ImportError or TranslatorError
        _translators_fn = translate_text
    return _translators_fn


def translate_with_translators(text, engine):
    translate_text = get_translators_fn()
    is_bn = BENGALI_RE.search(text) or BANGLISH_RE.search(text)
    last_error = None
    for source_lang in (["bn", "auto"] if is_bn else ["auto"]):
        try:
            result = normalize_spaces(translate_text(
                text, translator=engine, from_language=source_lang, to_language="en",
            ))
        except Exception as exc:
            last_error = exc
            continue
        if looks_translated(text, result):
            return result
    if last_error:
        raise last_error
    return ""


def translate_with_deep_translator(text):
    from deep_translator import GoogleTranslator   # pip install deep-translator
    return normalize_spaces(GoogleTranslator(source="auto", target="en").translate(text))


def translate_with_mymemory(text):
    langpair = "bn|en" if BENGALI_RE.search(text) else "Autodetect|en"
    pieces = []
    for part in chunk_text(text, MYMEMORY_MAX):
        response = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": part, "langpair": langpair},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        out = normalize_spaces((payload.get("responseData") or {}).get("translatedText", ""))
        status = str(payload.get("responseStatus", "200"))
        if status != "200" or re.search(r"MYMEMORY WARNING|QUERY LENGTH LIMIT|INVALID", out, re.I):
            raise RuntimeError(f"MyMemory error {status}: {out[:80]!r}")
        pieces.append(out)
        time.sleep(0.3)
    return normalize_spaces(" ".join(pieces))


def build_backends(engines):
    backends = [(f"translators:{e}", (lambda t, e=e: translate_with_translators(t, e))) for e in engines]
    backends.append(("deep-translator:google", translate_with_deep_translator))
    backends.append(("mymemory", translate_with_mymemory))
    return backends


def translate_chunk(chunk, backends, retries=2):
    """Try every working backend in turn. One backend crashing never blocks the others."""
    for attempt in range(retries):
        any_error = False
        for name, fn in backends:
            if name in _disabled:
                continue
            try:
                result = fn(chunk)
            except ImportError as exc:
                disable_backend(name, f"not installed ({exc})")
                continue
            except Exception as exc:
                any_error = True
                _failures[name] = _failures.get(name, 0) + 1
                if name.startswith("translators:") and "Unable to connect" in str(exc):
                    # import-time region check failed; every translators engine will fail
                    for other, _ in backends:
                        if other.startswith("translators:"):
                            disable_backend(other, "region check failed (set translators_default_region=EN)")
                elif _failures[name] >= BACKEND_FAIL_LIMIT:
                    disable_backend(name, f"{BACKEND_FAIL_LIMIT} errors in a row, last: {str(exc)[:100]}")
                continue
            _failures[name] = 0
            if looks_translated(chunk, result):
                return result
        if not any_error:
            break                       # nothing crashed; retrying will not change the answer
        time.sleep(1.5 * (attempt + 1))
    return ""


def translate_text_to_english(text, engines, retries=2):
    text = normalize_spaces(text)
    if not text:
        return ""
    backends = build_backends(engines)
    pieces = []
    for chunk in chunk_text(text):
        translated = translate_chunk(chunk, backends, retries)
        if not translated:
            raise RuntimeError(f"all backends failed for chunk {ascii(chunk[:60])}")
        pieces.append(translated)
        time.sleep(0.3)
    return normalize_spaces(" ".join(pieces))



def insert_translated_column(df, values):
    if TRANSLATED_COLUMN in df.columns:
        df = df.drop(columns=[TRANSLATED_COLUMN])
    review_text_index = df.columns.get_loc("review_text")
    df.insert(review_text_index + 1, TRANSLATED_COLUMN, values)
    return df


def run(args, base):
    input_path = resolve_path(base, args.input)
    output_path = resolve_path(base, args.output)
    cache_path = resolve_path(base, args.cache)
    engines = [engine.strip() for engine in args.engines.split(",") if engine.strip()]

    df = pd.read_csv(input_path)
    if "review_text" not in df.columns:
        raise SystemExit("Input CSV must contain a 'review_text' column.")

    row_count = len(df) if args.limit is None else min(len(df), args.limit)
    cache = load_cache(cache_path)
    translated_values = [""] * len(df)
    unique_needed = {}
    hits = 0

    for row_index, raw_text in enumerate(df["review_text"].iloc[:row_count]):
        review_text = normalize_spaces(raw_text)
        if not review_text:
            continue
        key = cache_key(review_text)
        cached = cache.get(key, "")
        if cached and looks_translated(review_text, cached):
            hits += 1
        else:
            unique_needed.setdefault(key, review_text)

    print(f"Rows to process: {row_count}")
    print(f"Cache hits: {hits}")
    print(f"Unique texts to translate: {len(unique_needed)}")
    print(f"Backends: {', '.join(engines)}, deep-translator (if installed), MyMemory")

    done = translated_unique = failed_unique = 0
    try:
        for key, review_text in unique_needed.items():
            done += 1
            try:
                translation = translate_text_to_english(review_text, engines)
            except Exception as exc:
                failed_unique += 1
                safe_print(f"WARN could not translate: {ascii(review_text[:70])} ({exc})")
                translation = ""
            if translation:
                cache[key] = translation
                translated_unique += 1
            if done % 10 == 0:
                save_cache(cache_path, cache)
                print(f"Progress {done}/{len(unique_needed)} (ok={translated_unique}, failed={failed_unique})")
            if len(_disabled) >= len(build_backends(engines)):
                print("All backends are switched off - stopping early. Progress is saved.")
                break
    except KeyboardInterrupt:
        print("\nInterrupted - saving progress...")
    finally:
        save_cache(cache_path, cache)

    for row_index, raw_text in enumerate(df["review_text"].iloc[:row_count]):
        review_text = normalize_spaces(raw_text)
        if review_text:
            translated_values[row_index] = cache.get(cache_key(review_text), "")

    df = insert_translated_column(df, translated_values)
    try:
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    except PermissionError:
        output_path = output_path.with_name(output_path.stem + "_new" + output_path.suffix)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print("Output file was open in another program (Excel?), saved under a new name instead.")

    filled = sum(1 for value in translated_values[:row_count] if str(value).strip())
    print(f"Filled translations: {filled}/{row_count}")
    if failed_unique:
        print(f"Failed unique texts: {failed_unique} (just run the script again; the cache keeps finished ones)")
    print(f"Saved translated CSV: {output_path}")
    print(f"Cache: {cache_path}")



def require_api_key():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set.\n"
            "The default command no longer needs OpenAI.\n"
            "Run:\n"
            "  python translate_reviews_to_english.py\n"
            "Or set an API key only if you want the optional Batch API commands."
        )
    return api_key


def headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def raise_for_status_with_body(response):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"HTTP {response.status_code} from {response.url}\n{response.text}"
        ) from exc


def translation_request(row_index, review_text, model):
    return {
        "custom_id": f"row-{row_index}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Translate the e-commerce product review into natural English. "
                        "The review may contain Bangla, English, Banglish, informal spelling, "
                        "slang, abbreviations, and emojis. Preserve meaning, tone, product "
                        "concerns, seller/delivery comments, rating sentiment, and emoji sentiment. "
                        "Do not summarize. Do not add explanations. Return only the English translation."
                    ),
                },
                {
                    "role": "user",
                    "content": review_text,
                },
            ],
        },
    }


def prepare(args, base):
    input_path = resolve_path(base, args.input)
    batch_input_path = resolve_path(base, args.batch_input)
    output_path = resolve_path(base, args.output)
    job_path = resolve_path(base, args.job)

    df = pd.read_csv(input_path)
    if "review_text" not in df.columns:
        raise SystemExit("Input CSV must contain a 'review_text' column.")

    row_count = len(df) if args.limit is None else min(len(df), args.limit)
    written = 0

    with batch_input_path.open("w", encoding="utf-8") as f:
        for row_index, raw_text in enumerate(df["review_text"].iloc[:row_count]):
            review_text = normalize_spaces(raw_text)
            if not review_text:
                continue
            f.write(json.dumps(
                translation_request(row_index, review_text, args.model),
                ensure_ascii=False,
            ))
            f.write("\n")
            written += 1

    metadata = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "batch_input": str(batch_input_path),
        "model": args.model,
        "row_count": row_count,
        "request_count": written,
        "batch_id": None,
        "input_file_id": None,
        "output_file_id": None,
        "error_file_id": None,
    }
    job_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Prepared {written} translation requests.")
    print(f"Batch input JSONL: {batch_input_path}")
    print(f"Job metadata: {job_path}")
    print("Preferred: python translate_reviews_to_english.py")
    print("Optional OpenAI: python translate_reviews_to_english.py submit")


def load_job(job_path):
    if not job_path.exists():
        raise SystemExit(f"Job file not found: {job_path}\nRun prepare first.")
    return json.loads(job_path.read_text(encoding="utf-8"))


def save_job(job_path, job):
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def submit(args, base):
    api_key = require_api_key()
    job_path = resolve_path(base, args.job)
    job = load_job(job_path)
    batch_input_path = Path(job["batch_input"])

    with batch_input_path.open("rb") as f:
        file_response = requests.post(
            f"{API_BASE}/files",
            headers=headers(api_key),
            files={"file": (batch_input_path.name, f, "application/jsonl")},
            data={"purpose": "batch"},
            timeout=120,
        )
    raise_for_status_with_body(file_response)
    input_file_id = file_response.json()["id"]

    batch_response = requests.post(
        f"{API_BASE}/batches",
        headers={**headers(api_key), "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": "/v1/chat/completions",
            "completion_window": "24h",
            "metadata": {
                "description": "Translate e-commerce review dataset to English",
            },
        },
        timeout=120,
    )
    raise_for_status_with_body(batch_response)
    batch = batch_response.json()

    job["input_file_id"] = input_file_id
    job["batch_id"] = batch["id"]
    job["status"] = batch.get("status")
    save_job(job_path, job)

    print(f"Submitted batch: {batch['id']}")
    print(f"Status: {batch.get('status')}")
    print("Next: python translate_reviews_to_english.py status")


def get_batch(api_key, batch_id):
    response = requests.get(f"{API_BASE}/batches/{batch_id}", headers=headers(api_key), timeout=120)
    raise_for_status_with_body(response)
    return response.json()


def status(args, base):
    api_key = require_api_key()
    job_path = resolve_path(base, args.job)
    job = load_job(job_path)
    batch_id = job.get("batch_id")
    if not batch_id:
        raise SystemExit("No batch_id found. Run submit first.")

    batch = get_batch(api_key, batch_id)
    job["status"] = batch.get("status")
    job["output_file_id"] = batch.get("output_file_id")
    job["error_file_id"] = batch.get("error_file_id")
    save_job(job_path, job)

    print(f"Batch: {batch_id}")
    print(f"Status: {batch.get('status')}")
    print(f"Request counts: {batch.get('request_counts')}")
    print(f"Output file: {batch.get('output_file_id')}")
    print(f"Error file: {batch.get('error_file_id')}")
    if batch.get("status") == "completed":
        print("Next: python translate_reviews_to_english.py collect")


def download_file_content(api_key, file_id):
    response = requests.get(f"{API_BASE}/files/{file_id}/content", headers=headers(api_key), timeout=120)
    raise_for_status_with_body(response)
    return response.text


def parse_translation_from_result(line):
    item = json.loads(line)
    custom_id = item.get("custom_id", "")
    if not custom_id.startswith("row-"):
        return None, ""

    row_index = int(custom_id.replace("row-", "", 1))
    if item.get("error"):
        return row_index, ""

    body = ((item.get("response") or {}).get("body") or {})
    choices = body.get("choices") or []
    if not choices:
        return row_index, ""

    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    try:
        parsed = json.loads(content)
        return row_index, normalize_spaces(parsed.get("translation", ""))
    except json.JSONDecodeError:
        return row_index, normalize_spaces(content)


def collect(args, base):
    api_key = require_api_key()
    job_path = resolve_path(base, args.job)
    job = load_job(job_path)
    batch_id = job.get("batch_id")
    if not batch_id:
        raise SystemExit("No batch_id found. Run submit first.")

    batch = get_batch(api_key, batch_id)
    if batch.get("status") != "completed":
        print(f"Batch is not completed yet. Current status: {batch.get('status')}")
        print("Run this later: python translate_reviews_to_english.py status")
        return

    output_file_id = batch.get("output_file_id")
    if not output_file_id:
        raise SystemExit("Batch completed but no output_file_id was returned.")

    output_text = download_file_content(api_key, output_file_id)
    translations = {}
    for line in output_text.splitlines():
        if not line.strip():
            continue
        row_index, translation = parse_translation_from_result(line)
        if row_index is not None:
            translations[row_index] = translation

    input_path = Path(job["input_csv"])
    output_path = Path(job["output_csv"])
    df = pd.read_csv(input_path)

    translated_values = [""] * len(df)
    for row_index, translation in translations.items():
        if 0 <= row_index < len(translated_values):
            translated_values[row_index] = translation

    df = insert_translated_column(df, translated_values)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    job["status"] = batch.get("status")
    job["output_file_id"] = output_file_id
    job["error_file_id"] = batch.get("error_file_id")
    save_job(job_path, job)

    filled = sum(1 for value in translated_values if str(value).strip())
    print(f"Collected translations: {filled}/{len(df)}")
    print(f"Saved translated CSV: {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Translate Bangla/Banglish/English e-commerce reviews into English."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "prepare", "submit", "status", "collect"],
        help="Default is run, which translates immediately without OpenAI.",
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--batch-input", default=DEFAULT_BATCH_INPUT)
    parser.add_argument("--job", default=DEFAULT_JOB)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--engines",
        default="bing,google",
        help="Comma-separated translators package engines, tried in order.",
    )
    return parser.parse_args()


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args()
    base = Path(__file__).parent

    if args.command == "run":
        run(args, base)
    elif args.command == "prepare":
        prepare(args, base)
    elif args.command == "submit":
        submit(args, base)
    elif args.command == "status":
        status(args, base)
    elif args.command == "collect":
        collect(args, base)


if __name__ == "__main__":
    main()

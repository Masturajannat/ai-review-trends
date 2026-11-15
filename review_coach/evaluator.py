"""Review Coach: score one review, and on request suggest how to make it more useful.

    from evaluator import evaluate, suggest
    r = evaluate("Foaming Facial Cleanser", "Product ta valo, delivery fast chilo.", judge="gemini")
    r["score"], r["level_meaning"], r["reason"]
    s = suggest("Foaming Facial Cleanser", "Product ta valo, delivery fast chilo.", judge="gemini")
    s["summary"], s["suggestions"]          # [{"quote", "suggestion", "example"}, ...]

The app only calls these two functions, and each always returns the same keys, so what is
behind them can be swapped.

evaluate(): the score
  "gemini"  the scoring prompt of the dataset (prompt_v2) and the same model; needs GEMINI_API_KEY
  "mock"    simple rules, no API calls; for building and testing the page only
  Later, our own model trained on the dataset is added here as a third judge.

suggest(): the suggestions, only when the user asks for them
  A separate prompt (prompts/suggest_v1.txt) that reads this one review and returns at most
  three suggestions, each tied to a phrase the reviewer wrote. It has nothing to do with the
  scoring, shows no checklist, and never invents facts for the reviewer.
"""
import json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
QE = os.path.join(os.path.dirname(HERE), "quality_eval")
sys.path.insert(0, os.path.join(QE, "scripts"))
from common import LEVELS, LLM  # noqa: E402

SCORE_PROMPT = os.path.join(QE, "prompts", "prompt_v2.txt")
SCORE_VERSION = "prompt_v2"
SUGGEST_PROMPT = os.path.join(HERE, "prompts", "suggest_v1.txt")
SUGGEST_VERSION = "suggest_v1"
GEMINI_MODEL = "gemini-3.5-flash-lite"
JUDGES = ["gemini", "mock"]
MAX_SUGGESTIONS = 3

_templates, _llm = {}, {}


def _fill(path, product, review):
    if path not in _templates:
        _templates[path] = open(path, encoding="utf-8").read()
    return _templates[path].replace("{product_name}", product or "(not given)").replace("{review_text}", review)


def _ask_gemini(prompt, parse, retries=3):
    """Send the prompt, parse the JSON answer; ask again on a busy server or a broken answer."""
    if GEMINI_MODEL not in _llm:
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is not set. Set it in the terminal before starting the app, "
                               "or choose the mock judge.")
        _llm[GEMINI_MODEL] = LLM(GEMINI_MODEL)
    last = None
    for i in range(retries):
        try:
            return parse(json.loads(_llm[GEMINI_MODEL](prompt)))
        except Exception as e:
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Gemini did not give a usable answer: {str(last)[:200]}")


def detect_language(text):
    """bangla (Bangla script), banglish (Bangla words in Latin letters) or english."""
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        return "unknown"
    bangla = sum("ঀ" <= ch <= "৿" for ch in letters)
    if bangla / len(letters) > 0.3:
        return "bangla"
    words = re.findall(r"[a-z]+", text.lower())
    banglish = {"ami", "amar", "valo", "bhalo", "khub", "onek", "kintu", "tobe", "ar", "ta", "ti", "hoy",
                "hoyeche", "chilo", "pelam", "paisi", "korlam", "kore", "use", "kaj", "dam", "na", "nai",
                "ache", "theke", "jonno", "eta", "ota", "pore", "dilam", "laglo", "lagche", "boi", "khubi",
                "vai", "bhai", "apu", "sob", "shob", "mone", "hocche", "hobe", "korsi", "kortesi", "krtesi"}
    hits = sum(w in banglish for w in words)
    return "banglish" if words and hits / len(words) >= 0.15 else "english"


def explain_level(score):
    """(level, what the level means) from the scoring scale of the prompt."""
    if score is None:
        return None, ""
    lvl = int(min(10, max(1, score)) + 0.5)
    return lvl, LEVELS[lvl]


def count_words(text):
    return len(re.findall(r"\w+", text))


# ---------------------------------------------------------------- score
def _score_result(score, reason, judge, model, version, t0):
    lvl, meaning = explain_level(score)
    return {"score": score, "level": lvl, "level_meaning": meaning, "reason": reason,
            "judge": judge, "model": model, "prompt_version": version,
            "latency_ms": int((time.time() - t0) * 1000)}


def _parse_score(j):
    score = int(j["overall"])
    if not 1 <= score <= 10:
        raise ValueError("score out of range")
    return score, str(j.get("reason", ""))


_NUM = re.compile(r"\d|[০-৯]")
_SIGNS = [re.compile(p) for p in [
    r"\b(day|days|week|weeks|month|months|year|din|mash|mas|shoptah|saptaho)\b|দিন|সপ্তাহ|মাস|বছর",
    r"\b(but|however|though|tobe|kintu)\b|তবে|কিন্তু",
    r"\b(because|since|karon|tai|jonno)\b|কারণ|তাই|জন্য",
    r"\b(deliver\w*|packag\w*|packing|seller|box|original|sealed|courier)\b|ডেলিভারি|প্যাকেজিং|প্যাকিং",
    r"\b(use[ds]?|using|tried|read|porlam|porechi|wear|wore)\b|ব্যবহার|পড়ে|পড়লাম",
    r"\b(than|compared|better|worse|suits?)\b|চেয়ে",
    r"\b(after|became|now|result|felt|works?|worked|broke|stopped)\b|পরে|এখন|ফলাফল"]]
_QUESTION = re.compile(r"\?\s*$|\b(price koto|available)\b")


def _mock_score(review):
    """Rough score from surface signs (length, numbers, time words, 'but', ...). Not a real judgement."""
    t, words = review.lower(), count_words(review)
    if _QUESTION.search(t):
        return 1
    signs = sum(bool(p.search(t)) for p in _SIGNS) + bool(_NUM.search(t))
    return max(2, min(9, 2 + signs + (words >= 12) + (words >= 25) + (words >= 45) - (words < 6)))


def evaluate(product, review, judge="gemini"):
    """Score a review 1-10 for how useful it is to a buyer."""
    product, review = (product or "").strip(), (review or "").strip()
    if not review:
        raise ValueError("Write a review first.")
    t0 = time.time()
    if judge == "gemini":
        score, reason = _ask_gemini(_fill(SCORE_PROMPT, product, review), _parse_score)
        r = _score_result(score, reason, "gemini", GEMINI_MODEL, SCORE_VERSION, t0)
    else:
        r = _score_result(_mock_score(review), "Mock judge: rough rules for testing the app, not a real score.",
                          "mock", "rules", "mock", t0)
    r["language"] = detect_language(review)
    r["word_count"] = count_words(review)
    return r


# ---------------------------------------------------------------- suggestions
def clean_suggestions(j, review):
    """Keep at most MAX_SUGGESTIONS well-formed suggestions; a quote must really be in the review."""
    out = []
    for s in (j.get("suggestions") or []):
        if not isinstance(s, dict) or not str(s.get("suggestion", "")).strip():
            continue
        quote = str(s.get("quote") or "").strip()
        if quote and quote not in review:
            # the model sometimes changes case or spacing: look for the phrase loosely, else drop the quote
            m = re.search(r"\s+".join(map(re.escape, quote.split())), review, flags=re.IGNORECASE)
            quote = m.group(0) if m else ""
        out.append({"quote": quote, "suggestion": str(s["suggestion"]).strip(),
                    "example": str(s.get("example") or "").strip()})
    return str(j.get("summary") or "").strip(), out[:MAX_SUGGESTIONS]


def _mock_suggest(review):
    lang = detect_language(review)
    first = re.split(r"(?<=[.!?।])\s+|\n", review.strip())[0][:60]
    text = {
        "bangla": ("(পরীক্ষার জন্য নকল পরামর্শ)", "এখানে আরেকটু খুলে বলুন, কী ভালো বা খারাপ লেগেছে?", "আমি ___ ধরে ব্যবহার করছি"),
        "banglish": ("(Test er jonno mock suggestion)", "Ekhane aro ektu khule bolun, ki valo ba kharap legeche?",
                     "Ami ___ dhore use korchi"),
    }.get(lang, ("(Mock suggestion, for testing only)", "Say a little more here: what exactly was good or bad?",
                 "I have used it for ___"))
    return text[0], [{"quote": first, "suggestion": text[1], "example": text[2]}]


def suggest(product, review, judge="gemini"):
    """At most three suggestions for this review, each tied to a phrase the reviewer wrote."""
    product, review = (product or "").strip(), (review or "").strip()
    if not review:
        raise ValueError("Write a review first.")
    t0 = time.time()
    if judge == "gemini":
        summary, items = _ask_gemini(_fill(SUGGEST_PROMPT, product, review),
                                     lambda j: clean_suggestions(j, review))
        model = GEMINI_MODEL
    else:
        summary, items = _mock_suggest(review)
        model = "rules"
    return {"summary": summary, "suggestions": items, "judge": judge, "model": model,
            "prompt_version": SUGGEST_VERSION if judge == "gemini" else "mock",
            "latency_ms": int((time.time() - t0) * 1000)}

"""Review Coach: judge one review and say how to make it more useful to a buyer.

    from evaluator import evaluate
    r = evaluate("Foaming Facial Cleanser", "Product ta valo, delivery fast chilo.", judge="gemini")
    r["score"], r["checks"], r["how_to_improve"]

The app only talks to evaluate(), whose result always has the same keys, so the judge
behind it can be swapped:
  "gemini"  the same prompt (prompt_v2_checks) and model as the scored dataset; needs GEMINI_API_KEY
  "mock"    simple rules, no API calls; for building and testing the interface only
Later an "own_model" judge (the model trained on the dataset) can be added here.
"""
import json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
QE = os.path.join(os.path.dirname(HERE), "quality_eval")
sys.path.insert(0, os.path.join(QE, "scripts"))
from common import CHECKS, CHECK_GROUPS, LEVELS, CRITERIA, parse_checks, parse_feedback, LLM  # noqa: E402

PROMPT_FILE = "prompt_v2_checks.txt"
PROMPT_VERSION = "prompt_v2_checks"
GEMINI_MODEL = "gemini-3.5-flash-lite"
JUDGES = ["gemini", "mock"]

# names shown in the app for the ten checks
CHECK_LABELS = {
    "product_detail": "Product detail",
    "service_detail": "Delivery / service detail",
    "depth": "Explains a point",
    "own_use": "Used it yourself",
    "usage_context": "How long / how often",
    "outcome": "What happened",
    "gives_reason": "Gives a reason",
    "balance": "Good and bad points",
    "comparison_or_audience": "Comparison / who it suits",
    "on_topic": "About this product",
}

_template = None
_llm = {}


def _prompt(product, review):
    global _template
    if _template is None:
        _template = open(os.path.join(QE, "prompts", PROMPT_FILE), encoding="utf-8").read()
    return _template.replace("{product_name}", product).replace("{review_text}", review)


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
    lvl = int(min(10, max(1, score)) + 0.5) if score is not None else None
    if lvl is None:
        return None, "", ""
    nxt = f"{lvl + 1}: {LEVELS[lvl + 1]}" if lvl < 10 else ""
    return lvl, LEVELS[lvl], nxt


def _result(score, reason, checks, weak, tips, judge, model, t0):
    lvl, meaning, nxt = explain_level(score)
    groups = {c: {k: checks[k] for k in CHECK_GROUPS[c]} for c in CRITERIA}
    return {
        "score": score, "level": lvl, "level_meaning": meaning, "next_level": nxt,
        "reason": reason, "checks": checks, "check_groups": groups,
        "checks_met": sum(checks.values()),
        "weak_criteria": weak, "how_to_improve": tips,
        "judge": judge, "model": model, "prompt_version": PROMPT_VERSION,
        "latency_ms": int((time.time() - t0) * 1000),
    }


def _gemini(product, review, t0, retries=3):
    if GEMINI_MODEL not in _llm:
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is not set. Set it in the terminal before starting the app, "
                               "or choose the mock judge.")
        _llm[GEMINI_MODEL] = LLM(GEMINI_MODEL)
    last = None
    for i in range(retries):
        try:
            j = json.loads(_llm[GEMINI_MODEL](_prompt(product, review)))
            score = int(j["overall"])
            if not 1 <= score <= 10:
                raise ValueError("score out of range")
            checks = {k[6:]: v for k, v in parse_checks(j).items()}
            weak, tips = parse_feedback(j)
            return _result(score, str(j.get("reason", "")), checks, [w for w in weak.split("|") if w],
                           json.loads(tips), "gemini", GEMINI_MODEL, t0)
        except Exception as e:          # busy server, broken JSON, missing check: ask again
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Gemini did not give a usable answer: {str(last)[:200]}")


# ---------------------------------------------------------------- mock judge (no API)
_NUM = re.compile(r"\d|[০-৯]")
_TIME = re.compile(r"\b(day|days|week|weeks|month|months|year|din|mash|mas|shoptah|saptaho)\b|দিন|সপ্তাহ|মাস|বছর")
_BUT = re.compile(r"\b(but|however|though|tobe|kintu|but)\b|তবে|কিন্তু")
_WHY = re.compile(r"\b(because|since|so|karon|tai|jonno)\b|কারণ|তাই|জন্য")
_DELIV = re.compile(r"\b(deliver\w*|packag\w*|packing|seller|box|original|sealed|courier)\b|ডেলিভারি|প্যাকেজিং|প্যাকিং")
_USE = re.compile(r"\b(use[ds]?|using|used|tried|read|porlam|porechi|use kor\w*|wear|wore)\b|ব্যবহার|পড়ে|পড়লাম")
_CMP = re.compile(r"\b(than|compared|better|worse|suits?|for people|recommend\w* for)\b|চেয়ে|থেকে ভালো")
_RESULT = re.compile(r"\b(after|became|now|result|felt|works?|worked|broke|stopped)\b|পরে|এখন|ফলাফল")
_QUESTION = re.compile(r"\?\s*$|\b(price koto|ache\?|available)\b")
_TIP = {
    "specific": "Name a concrete detail: a feature, how well it works, or the condition it arrived in.",
    "personal": "Say how long you have used it and in what situation, and what happened.",
    "reasoned": "Give a reason for your opinion: a good and a bad point, or a comparison.",
    "relevant": "Write about your own experience with the product instead of a question to the seller.",
}


def _mock(product, review, t0):
    t = review.lower()
    words = len(re.findall(r"\w+", review))
    c = {k: 0 for k in CHECKS}
    c["on_topic"] = int(not _QUESTION.search(t))
    c["service_detail"] = int(bool(_DELIV.search(t)) and bool(_NUM.search(t)))
    c["product_detail"] = int(words >= 12)
    c["depth"] = int(words >= 20)
    c["own_use"] = int(bool(_USE.search(t)))
    c["usage_context"] = int(bool(_TIME.search(t)) and bool(_NUM.search(t)))
    c["outcome"] = int(bool(_RESULT.search(t)))
    c["gives_reason"] = int(bool(_WHY.search(t)))
    c["balance"] = int(bool(_BUT.search(t)))
    c["comparison_or_audience"] = int(bool(_CMP.search(t)))
    score = 1 if not c["on_topic"] else max(2, min(9, 2 + sum(c.values()) - c["on_topic"] + (words >= 40)))
    weak = [g for g in CRITERIA if score < 9 and not all(c[k] for k in CHECK_GROUPS[g])
            and (g != "specific" or not (c["product_detail"] and c["depth"]))]
    return _result(score, "Mock judge: rough rules for testing the app, not a real score.", c, weak,
                   {g: _TIP[g] for g in weak}, "mock", "rules", t0)


def evaluate(product, review, judge="gemini"):
    product, review = (product or "").strip(), (review or "").strip()
    if not review:
        raise ValueError("Write a review first.")
    t0 = time.time()
    r = _gemini(product or "(not given)", review, t0) if judge == "gemini" else _mock(product, review, t0)
    r["language"] = detect_language(review)
    r["word_count"] = len(re.findall(r"\w+", review))
    return r

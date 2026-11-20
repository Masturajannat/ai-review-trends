"""Review Coach: score one review, and on request suggest how to make it more useful.

    from evaluator import evaluate, suggest
    r = evaluate("Foaming Facial Cleanser", "Product ta valo, delivery fast chilo.", judge="gemini")
    r["score"], r["level_meaning"], r["explanation"]
    s = suggest("Foaming Facial Cleanser", "Product ta valo, delivery fast chilo.", judge="gemini")
    s["summary"], s["suggestions"]          # [{"quote", "suggestion", "example"}, ...]

The app only calls these two functions, and each always returns the same keys, so what is
behind them can be swapped.

evaluate(): the score
  "model"   our own model: XLM-RoBERTa large fine-tuned on the 7,322 reviews Gemini scored
            (quality_model/). Runs on this computer, no API, no internet. The score is given in
            half points, like the training labels, with what its level means.
  "gemini"  the scoring instructions of the dataset (prompt_v2) and the same Gemini model; after
            the score it also explains it in a short paragraph; needs GEMINI_API_KEY
  "mock"    simple rules, no API calls; for building and testing the page only

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
SUGGEST_PROMPT = os.path.join(HERE, "prompts", "suggest_v2.txt")
SUGGEST_VERSION = "suggest_v2"
# the review's language is detected here and named in the prompt, and the answer is checked:
# Gemini does not reliably pick the right language by itself
LANGUAGE_RULE = {
    "english": "The review is written in English. Write in English only. Do not use any Bangla or Banglish words.",
    "bangla": "The review is written in Bangla. Write in Bangla, in Bangla script only (not in English letters).",
    "banglish": "The review is written in Banglish (Bangla written in English letters). Write in Banglish only: "
                "Bangla words in English letters, as the reviewer does. Do not use Bangla script.",
    "unknown": "Write in the same language and script as the review.",
}
GEMINI_MODEL = "gemini-3.5-flash-lite"
# the trained model: a folder made by quality_model/scripts/03_train_transformer.py
MODEL_DIR = os.environ.get("REVIEW_COACH_MODEL", os.path.join(
    os.path.dirname(HERE), "quality_model", "models_noreadmore", "xlm-roberta-large"))
JUDGES = ["model", "gemini", "mock"]
MAX_SUGGESTIONS = 3

_templates, _llm = {}, {}


# What the app asks for after the score. The scoring instructions above it are prompt_v2 word for
# word, and "reason" and "overall" come first as in the dataset, so the score is made the same way.
SCORE_OUTPUT = """OUTPUT
Reply with JSON only, with these keys in this order:
1. "reason": one short sentence in English explaining the score.
2. "overall": the score, an integer from 1 to 10.
3. "explanation": a short paragraph of 2 or 3 sentences for the reviewer, explaining the score in plain words: first what THIS review tells a buyer, then what keeps the score from being higher. Refer to what the review actually says or leaves out. For a score of 9 or 10, say only what makes it useful. Write it in the same language and script as the review (Bangla script for a Bangla review, Banglish for a Banglish review, English for an English review). Do not use bullet points, and do not invent facts about the product.
"""


def _fill(path, product, review):
    if path not in _templates:
        t = open(path, encoding="utf-8").read()
        if path == SCORE_PROMPT:
            t = t[:t.index("\nOUTPUT\n") + 1] + SCORE_OUTPUT
        _templates[path] = t
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


_BANGLISH = {
    # pronouns, verbs and little words that are common in Banglish and rare in English
    "ami", "amar", "amake", "amra", "apni", "apnar", "apnake", "tumi", "tomar", "se", "tar", "ora",
    "valo", "bhalo", "kharap", "khub", "khubi", "onek", "aro", "aroktu", "beshi", "kom", "shundor", "sundor",
    "kintu", "tobe", "ar", "jodi", "tahole", "karon", "tai", "jonno", "theke", "sathe", "moto", "diye",
    "ta", "ti", "tar", "tir", "er", "ke", "te", "der", "gulo", "na", "nai", "nei", "ni", "o", "r", "je",
    "ki", "kon", "keno", "kemon", "kibhabe", "kivabe", "ekta", "ekti", "duita", "eta", "ota", "seta", "ekhane",
    "hoy", "hoyeche", "hoyse", "holo", "hobe", "chilo", "ache", "achhe", "lage", "laglo", "legeche", "lagche",
    "pelam", "paisi", "peyechi", "dilam", "nilam", "kinlam", "kinechi", "korlam", "korechi", "korchi", "korsi",
    "kortesi", "krtesi", "kore", "korle", "kora", "dile", "niye", "geche", "pore", "porlam", "porechi",
    "mone", "hocche", "jacche", "bujha", "bujhlen", "bujhi", "thik", "dam", "taka", "kaj", "vai", "bhai",
    "apu", "sob", "shob", "vabe", "bhabe", "emon"}
BANGLISH_SHARE = 0.12          # share of such words from which a Latin-letter text counts as Banglish


def detect_language(text):
    """bangla (Bangla script), banglish (Bangla words in Latin letters) or english."""
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        return "unknown"
    bangla = sum("ঀ" <= ch <= "৿" for ch in letters)
    if bangla / len(letters) > 0.3:
        return "bangla"
    words = re.findall(r"[a-z]+", text.lower())
    hits = sum(w in _BANGLISH for w in words)
    return "banglish" if words and hits / len(words) >= BANGLISH_SHARE else "english"


def explain_level(score):
    """(level, what the level means) from the scoring scale of the prompt."""
    if score is None:
        return None, ""
    lvl = int(min(10, max(1, score)) + 0.5)
    return lvl, LEVELS[lvl]


def count_words(text):
    return len(re.findall(r"\w+", text))


# ---------------------------------------------------------------- our own model
_own = {}


def model_available(path=None):
    path = path or MODEL_DIR
    return all(os.path.exists(os.path.join(path, f)) for f in ("config.json", "score_scale.json"))


def load_model(path=None):
    """Load the trained model once (a large model takes 10 to 30 seconds the first time)."""
    path = path or MODEL_DIR
    if path not in _own:
        if not model_available(path):
            raise RuntimeError(f"The trained model was not found in {path}. Download it from Google Drive "
                               "(review_quality_model/xlm-roberta-large) into that folder, or choose another judge.")
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSequenceClassification.from_pretrained(path).eval()
        for p in model.parameters():          # scoring only: no training, so no gradients for the weights
            p.requires_grad_(False)
        scale = json.load(open(os.path.join(path, "score_scale.json"), encoding="utf-8"))
        _own[path] = (tok, model, scale, torch)
    return _own[path]


def strip_read_more(review):
    return re.sub(r"(?i)\s*read more\s*$", "", review)          # as in training ("Read More" stripped)


def model_score(review, path=None):
    """The trained model's score, 1 to 10 (not rounded)."""
    tok, model, scale, torch = load_model(path)
    text = strip_read_more(review)
    enc = tok(text, truncation=True, max_length=int(scale.get("max_len", 256)), return_tensors="pt")
    enc.pop("token_type_ids", None)
    with torch.no_grad():
        z = model(**enc).logits.float().squeeze().item()
    return float(min(10, max(1, z * scale["std"] + scale["mean"])))


def word_importance(review, path=None, steps=8, chunk=2):
    """Which words pushed the trained model's score up or down (integrated gradients).

    The review's tokens are faded in from a neutral input (padding) to the real text in `steps`
    steps; the gradient of the score along the way, times the change, gives each token's share of
    the score. Token shares are added up per word and given in score points (positive: raised the
    score). They add up, roughly, to the difference between this review's score and the score of
    an empty review. Words after the model's token limit are not read; they are marked `read: False`.
    Runs on the CPU in a few seconds for a short review, longer for a long one."""
    tok, model, scale, torch = load_model(path)
    text = strip_read_more(review)
    enc = tok(text, truncation=True, max_length=int(scale.get("max_len", 256)), return_tensors="pt",
              return_offsets_mapping=True)
    offsets = enc.pop("offset_mapping")[0].tolist()
    enc.pop("token_type_ids", None)
    ids, mask = enc["input_ids"], enc["attention_mask"]
    emb = model.get_input_embeddings()
    special = torch.tensor(tok.get_special_tokens_mask(ids[0].tolist(), already_has_special_tokens=True)).bool()
    with torch.no_grad():
        x = emb(ids)
        base = torch.where(special[None, :, None], x, emb(torch.full_like(ids, tok.pad_token_id)))
    if ids.shape[1] > 128 and steps > 4:          # long review: fewer steps keep it to a few seconds on a CPU
        steps = 4
    grads = torch.zeros_like(x)
    for alphas in ((torch.arange(steps, dtype=x.dtype) + 0.5) / steps).split(chunk):
        inp = (base + alphas[:, None, None] * (x - base)).requires_grad_(True)
        out = model(inputs_embeds=inp, attention_mask=mask.expand(len(alphas), -1)).logits.float().squeeze(-1)
        grads += torch.autograd.grad(out.sum(), inp)[0].sum(0, keepdim=True)
    token_values = ((x - base) * grads / steps).sum(-1)[0] * float(scale["std"])

    spans = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    values, read_until, w = [0.0] * len(spans), 0, 0
    for (a, b), v, sp in zip(offsets, token_values.tolist(), special.tolist()):
        if sp or b <= a:
            continue
        read_until = max(read_until, b)
        while w < len(spans) and spans[w][1] <= a:
            w += 1
        if w < len(spans):
            values[w] += v
    return {"text": text, "words": [{"start": a, "end": b, "value": round(v, 4), "read": a < read_until}
                                    for (a, b), v in zip(spans, values)]}


_SENT_END = re.compile(r"[.!?\u0964]+|\n+")                                  # . ! ? and the Bangla danda
_CLAUSE = re.compile(r"[,;:]\s+|\s+(?=(?:but|however|though|although|kintu|tobe|karon|because)\b)|"
                     r"\s+(?=(?:\u09a4\u09ac\u09c7|\u0995\u09bf\u09a8\u09cd\u09a4\u09c1|\u0995\u09be\u09b0\u09a3)\s)",
                     re.IGNORECASE)                                                 # , ; : and "but", "kintu", তবে, কিন্তু, কারণ


def split_parts(text, long_part=14, min_words=3):
    """Cut a review into parts a reader would recognise: sentences, and long sentences into
    clauses at commas and words like "but" / "kintu" / "তবে". Parts of fewer than `min_words`
    words are joined to their neighbour. Returns (start, end) character spans covering the words."""
    def spans(a, b, pattern):
        out, pos = [], a
        for m in pattern.finditer(text, a, b):
            out.append((pos, m.end())); pos = m.end()
        out.append((pos, b))
        return [(x, y) for x, y in out if text[x:y].strip()]

    nwords = lambda sp: len(text[sp[0]:sp[1]].split())
    parts = []
    for sp in spans(0, len(text), _SENT_END):
        parts += spans(*sp, _CLAUSE) if nwords(sp) > long_part else [sp]
    merged = []
    for sp in parts:
        if merged and (nwords(sp) < min_words or nwords(merged[-1]) < min_words):
            merged[-1] = (merged[-1][0], sp[1])
        else:
            merged.append(sp)
    # trim surrounding spaces so the highlight covers only the words
    out = []
    for a, b in merged:
        seg = text[a:b]
        out.append((a + len(seg) - len(seg.lstrip()), b - (len(seg) - len(seg.rstrip()))))
    return out


def part_importance(review, path=None):
    """How much each part of the review moves the trained model's score.

    Each part's value is the score of the whole review minus the score of the review with that
    part left out (in score points): positive = that part raised the score. One extra pass of the
    model per part, all in one batch; no API. With a single part there is nothing to compare,
    so values are None."""
    tok, model, scale, torch = load_model(path)
    text = strip_read_more(review)
    spans = split_parts(text)
    max_len = int(scale.get("max_len", 256))
    enc = tok(text, truncation=True, max_length=max_len, return_offsets_mapping=True)
    read_until = max([b for a, b in enc["offset_mapping"] if b > a] or [0])
    parts = [{"start": a, "end": b, "value": None, "read": a < read_until} for a, b in spans]
    if len(spans) < 2:
        return {"text": text, "parts": parts}
    variants = [text] + [" ".join((text[:a] + " " + text[b:]).split()) for a, b in spans]
    enc = tok(variants, truncation=True, max_length=max_len, padding=True, return_tensors="pt")
    enc.pop("token_type_ids", None)
    with torch.no_grad():
        z = model(**enc).logits.float().squeeze(-1)
    scores = (z * float(scale["std"])).tolist()                 # the mean cancels in the differences
    for p, without in zip(parts, scores[1:]):
        p["value"] = round(scores[0] - without, 3) if p["read"] else None
    return {"text": text, "parts": parts}


def model_name(path=None):
    path = path or MODEL_DIR
    try:
        return json.load(open(os.path.join(path, "score_scale.json"), encoding="utf-8")).get("base_model", "own model")
    except OSError:
        return "own model"


# ---------------------------------------------------------------- score
def _score_result(score, reason, explanation, judge, model, version, t0):
    lvl, meaning = explain_level(score)
    return {"score": score, "level": lvl, "level_meaning": meaning, "reason": reason,
            "explanation": explanation,
            "judge": judge, "model": model, "prompt_version": version,
            "latency_ms": int((time.time() - t0) * 1000)}


def _parse_score(j):
    score = int(j["overall"])
    if not 1 <= score <= 10:
        raise ValueError("score out of range")
    return score, str(j.get("reason", "")), " ".join(str(j.get("explanation") or "").split())


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


def evaluate(product, review, judge="gemini", explain=True):
    """Score a review 1-10 for how useful it is to a buyer. With the trained model and explain=True
    the result also has "importance": which parts of the review raised or lowered the score
    (part_importance). word_importance gives the same per word, but single words ("but", "a", a full
    stop) are hard for a reviewer to read, so the app shows parts."""
    product, review = (product or "").strip(), (review or "").strip()
    if not review:
        raise ValueError("Write a review first.")
    t0 = time.time()
    if judge == "model":
        raw = model_score(review)
        r = _score_result(round(raw * 2) / 2, "", "", "model", model_name(), "trained model", t0)
        r["raw_score"] = round(raw, 3)
        if explain:
            r["importance"] = part_importance(review)
            r["latency_ms"] = int((time.time() - t0) * 1000)
    elif judge == "gemini":
        score, reason, why = _ask_gemini(_fill(SCORE_PROMPT, product, review), _parse_score)
        r = _score_result(score, reason, why or reason, "gemini", GEMINI_MODEL, SCORE_VERSION, t0)
    else:
        r = _score_result(_mock_score(review), "Mock judge: rough rules for testing the app, not a real score.",
                          "", "mock", "rules", "mock", t0)
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


def check_language(text, lang):
    """Raise (so Gemini is asked again) when the suggestions are not in the review's language."""
    got = detect_language(text)
    if (lang == "english" and got != "english") or (lang == "bangla" and got != "bangla") \
            or (lang == "banglish" and got == "bangla"):
        raise ValueError(f"suggestions came back in {got}, the review is in {lang}")


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
        lang = detect_language(review)
        prompt = _fill(SUGGEST_PROMPT, product, review).replace("{language_rule}", LANGUAGE_RULE[lang])

        def parse(j):
            summary, items = clean_suggestions(j, review)
            check_language(" ".join([summary] + [i["suggestion"] + " " + i["example"] for i in items]), lang)
            return summary, items
        summary, items = _ask_gemini(prompt, parse)
        model = GEMINI_MODEL
    else:
        summary, items = _mock_suggest(review)
        model = "rules"
    return {"summary": summary, "suggestions": items, "judge": judge, "model": model,
            "prompt_version": SUGGEST_VERSION if judge == "gemini" else "mock",
            "latency_ms": int((time.time() - t0) * 1000)}

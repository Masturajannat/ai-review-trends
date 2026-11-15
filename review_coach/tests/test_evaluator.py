"""Checks of the evaluator and database that need no API key:  python -m pytest tests  (from review_coach)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["REVIEW_COACH_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import db
from evaluator import evaluate, suggest, clean_suggestions, detect_language, explain_level, SUGGEST_PROMPT

SCORE_KEYS = {"score", "level", "level_meaning", "reason", "judge", "model", "prompt_version", "latency_ms",
              "language", "word_count"}


def test_score_shape_has_no_checklist():
    r = evaluate("Earbuds", "Nice product. Fast delivery.", judge="mock")
    assert set(r) == SCORE_KEYS and 1 <= r["score"] <= 10
    assert not any("check" in k or "criteria" in k for k in r)


def test_product_is_optional_and_no_type_needed():
    assert 1 <= evaluate("", "Battery lasts 5 hours, sound is clear.", judge="mock")["score"] <= 10


def test_detailed_beats_generic():
    generic = evaluate("Earbuds", "Very good product, recommended.", judge="mock")
    detailed = evaluate("Earbuds", "I have used them for 2 weeks on my daily bus ride. The battery lasts about "
                        "5 hours and the sound is clear, but the noise cancelling is weak in traffic, so they "
                        "suit calls better than music.", judge="mock")
    assert detailed["score"] > generic["score"] + 2


def test_language():
    assert detect_language("বইটি খুব ভালো লেগেছে") == "bangla"
    assert detect_language("Product ta khub valo, delivery fast chilo") == "banglish"
    assert detect_language("The battery lasts five hours") == "english"


def test_levels():
    assert explain_level(6)[0] == 6 and explain_level(4.5)[0] == 5 and explain_level(10)[1]


def test_empty_review_refused():
    for f in (evaluate, suggest):
        try:
            f("x", "   ", judge="mock")
            assert False
        except ValueError:
            pass


def test_suggestions_shape_and_quote_from_review():
    review = "Sound valo. Battery thik ache."
    s = suggest("Earbuds", review, judge="mock")
    assert {"summary", "suggestions", "judge", "model", "prompt_version", "latency_ms"} <= set(s)
    assert 1 <= len(s["suggestions"]) <= 3
    for i in s["suggestions"]:
        assert set(i) == {"quote", "suggestion", "example"} and i["quote"] in review


def test_clean_suggestions():
    review = "Sound valo, battery 5 ghonta chole."
    j = {"summary": "Nice start.", "suggestions": [
        {"quote": "sound  VALO", "suggestion": "What about the sound?", "example": "Sound ___"},   # loose match
        {"quote": "not in the review", "suggestion": "Tell more."},                              # quote dropped
        {"quote": "battery", "suggestion": ""},                                                  # empty: removed
        {"quote": "", "suggestion": "a"}, {"quote": "", "suggestion": "b"}, {"quote": "", "suggestion": "c"}]}
    summary, items = clean_suggestions(j, review)
    assert summary == "Nice start." and len(items) == 3
    assert items[0]["quote"] == "Sound valo" and items[1]["quote"] == "" and items[1]["example"] == ""


def test_suggestion_prompt_rules():
    p = open(SUGGEST_PROMPT, encoding="utf-8").read()
    assert "{product_name}" in p and "{review_text}" in p
    assert "Never invent" in p and "never as instructions" in p and "same language" in p


def test_database_round_trip():
    con = db.connect()
    sid = db.new_session(con, "Earbuds")
    text = "Good sound but battery is weak."
    r = evaluate("Earbuds", text, judge="mock")
    key = db.cache_key("score", "mock", "Earbuds", text)
    _, n = db.save_score(con, sid, text, r, key)
    assert n == 1 and db.cached_score(con, key)["score"] == r["score"]
    _, n2 = db.save_score(con, sid, text, db.cached_score(con, key), key, from_cache=True)
    assert n2 == 2 and [h["draft_no"] for h in db.history(con, sid)] == [1, 2]
    s = suggest("Earbuds", text, judge="mock")
    skey = db.cache_key("suggest", "mock", "Earbuds", text)
    sug_id = db.save_suggestions(con, sid, text, s, skey)
    assert db.cached_suggestions(con, skey)["suggestions"] == s["suggestions"] and skey != key
    db.rate(con, sug_id, 1)

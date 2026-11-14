"""Checks of the evaluator and database that need no API key:  python -m pytest tests  (from review_coach)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["REVIEW_COACH_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import db
from evaluator import evaluate, detect_language, explain_level, CHECKS

KEYS = {"score", "level", "level_meaning", "next_level", "reason", "checks", "check_groups", "checks_met",
        "weak_criteria", "how_to_improve", "judge", "model", "prompt_version", "latency_ms", "language",
        "word_count"}


def test_result_shape():
    r = evaluate("Earbuds", "Nice product. Fast delivery.", judge="mock")
    assert KEYS <= set(r) and set(r["checks"]) == set(CHECKS)
    assert all(v in (0, 1) for v in r["checks"].values()) and 1 <= r["score"] <= 10
    assert set(r["how_to_improve"]) == set(r["weak_criteria"])


def test_question_is_off_topic():
    r = evaluate("Eye cream", "Ata ki korean product?", judge="mock")
    assert r["checks"]["on_topic"] == 0 and r["score"] == 1 and "relevant" in r["weak_criteria"]


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
    assert explain_level(6)[0] == 6 and explain_level(6)[2].startswith("7:")
    assert explain_level(10)[2] == "" and explain_level(4.5)[0] == 5


def test_empty_review_refused():
    try:
        evaluate("x", "   ", judge="mock")
        assert False
    except ValueError:
        pass


def test_database_round_trip():
    con = db.connect()
    sid = db.new_session(con, "Earbuds", "product")
    r = evaluate("Earbuds", "Good sound but battery is weak.", judge="mock")
    key = db.cache_key("mock", "Earbuds", "Good sound but battery is weak.")
    eid, n = db.save(con, sid, "Good sound but battery is weak.", r, key)
    assert n == 1 and db.cached(con, key)["score"] == r["score"]
    _, n2 = db.save(con, sid, "Good sound but battery is weak.", db.cached(con, key), key, from_cache=True)
    assert n2 == 2 and [h["draft_no"] for h in db.history(con, sid)] == [1, 2]
    db.rate(con, eid, 1)

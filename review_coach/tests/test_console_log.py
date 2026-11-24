"""Checks of the console log; no model and no API key needed:  python -m pytest tests  (from review_coach)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import console_log as cl
import evaluator as ev

R = {"score": 7.0, "level": 7, "level_meaning": "specific detail backed by the reviewer's own use or purchase",
     "language": "english", "word_count": 11, "latency_ms": 840}
TRACE = {"n_tokens": 20, "max_len": 256, "z": 0.412, "std": 2.1, "mean": 5.9, "value": 6.77, "kept": 6.77}
PARTS = [{"text": "I used it for 7 weeks.", "value": 1.5, "read": True},
         {"text": "My cheek bumps went away.", "value": 2.0, "read": True},
         {"text": "Good product.", "value": 0.1, "read": True}]


def fake_model(monkeypatch):
    monkeypatch.setattr(cl, "model_trace", lambda review: TRACE)
    monkeypatch.setattr(cl, "evidence", lambda review: PARTS)


def test_log_shows_request_steps_evidence_and_response(monkeypatch, capsys):
    fake_model(monkeypatch)
    cl.log_rating("Face wash", "face wash", "I used it for 7 weeks. My cheek bumps went away. Good product.",
                  R, note=False)
    out = capsys.readouterr().out
    for part in ["REQUEST #", "Face wash (face wash)", "20 of 256 read (nothing cut)", "= 6.77", "rounded to half points: 7",
                 "+2.0", "My cheek bumps went away.", "RESPONSE #", "score 7 sent to the page"]:
        assert part in out, part


def test_cut_review_is_reported(monkeypatch, capsys):
    monkeypatch.setattr(cl, "model_trace", lambda review: dict(TRACE, n_tokens=300))
    monkeypatch.setattr(cl, "evidence", lambda review: PARTS)
    cl.log_rating("Book", "book", "text", R, note=False)
    assert "44 at the end were cut" in capsys.readouterr().out


def test_other_judge_has_no_model_steps(monkeypatch, capsys):
    cl.log_rating("Face wash", "", "Nice product.", R, judge="mock", note=False)
    out = capsys.readouterr().out
    assert "trained model only" in out and "WHAT OUR MODEL REACTED TO" not in out


def test_a_problem_in_the_log_never_reaches_the_page(monkeypatch, capsys):
    def boom(review):
        raise RuntimeError("model folder missing")
    monkeypatch.setattr(cl, "model_trace", boom)
    cl.log_rating("Face wash", "", "Nice product.", R, note=False)          # must not raise
    assert "console log failed: model folder missing" in capsys.readouterr().out


def test_note_without_key_says_so(monkeypatch, capsys):
    fake_model(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cl.log_rating("Face wash", "face wash", "Review text.", R)
    assert "note unavailable: GEMINI_API_KEY is not set" in capsys.readouterr().out


def test_note_gets_score_and_evidence_and_prints(monkeypatch, capsys):
    fake_model(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(cl, "NOTE_IN_BACKGROUND", False)
    seen = {}

    def fake_ask(prompt, parse, retries=3):
        seen["prompt"] = prompt
        return parse({"why": "The 7 weeks of use and the result carry the score.", "found": ["personal: 7 weeks of use"],
                      "not_mentioned": ["no comparison with another product"]})
    monkeypatch.setattr(ev, "_ask_gemini", fake_ask)
    cl.log_rating("Face wash", "face wash", "I used it for 7 weeks.", R)
    out = capsys.readouterr().out
    p = seen["prompt"]
    assert "MODEL SCORE: 7 out of 10" in p and "+2.0 | \"My cheek bumps went away.\"" in p
    assert "{" not in p.replace('{"', "").split("OUTPUT")[0]            # every placeholder was filled
    assert "NOTE for request" in out and "personal: 7 weeks of use" in out and "not mentioned : no comparison" in out


def test_note_failure_is_only_printed(monkeypatch, capsys):
    fake_model(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(cl, "NOTE_IN_BACKGROUND", False)

    def broken(prompt, parse, retries=3):
        raise RuntimeError("Gemini did not give a usable answer")
    monkeypatch.setattr(ev, "_ask_gemini", broken)
    cl.log_rating("Face wash", "", "Review text.", R)
    assert "note unavailable: Gemini did not give a usable answer" in capsys.readouterr().out


def test_parse_note_limits_and_needs_a_reason():
    n = cl.parse_note({"why": "ok", "found": list("abcde"), "not_mentioned": list("xyz")})
    assert len(n["found"]) == 3 and len(n["not_mentioned"]) == 2
    try:
        cl.parse_note({"found": ["a"]})
        assert False
    except ValueError:
        pass

"""Checks of the evaluator and database that need no API key:  python -m pytest tests  (from review_coach)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["REVIEW_COACH_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import db
from evaluator import evaluate, suggest, clean_suggestions, detect_language, explain_level, SUGGEST_PROMPT

SCORE_KEYS = {"score", "level", "level_meaning", "reason", "explanation", "judge", "model", "prompt_version", "latency_ms",
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


def test_score_prompt_keeps_dataset_scoring():
    import evaluator
    full = evaluator._fill(evaluator.SCORE_PROMPT, "P", "R")
    orig = open(evaluator.SCORE_PROMPT, encoding="utf-8").read()
    head = orig[:orig.index("\nOUTPUT\n")].replace("{product_name}", "P").replace("{review_text}", "R")
    assert full.startswith(head)                                  # scoring instructions unchanged
    out = full[len(head):]
    assert out.index('"reason"') < out.index('"overall"') < out.index('"explanation"')


def test_parse_score_reasons():
    import evaluator
    s = evaluator._parse_score({"reason": "r", "overall": 6, "explanation": " You said \n how long.  "})
    assert s == (6, "r", "You said how long.") and evaluator._parse_score({"overall": 3})[2] == ""


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
    assert db.cached_score(con, key)["explanation"] == r["explanation"]
    _, n2 = db.save_score(con, sid, text, db.cached_score(con, key), key, from_cache=True)
    assert n2 == 2 and [h["draft_no"] for h in db.history(con, sid)] == [1, 2]
    s = suggest("Earbuds", text, judge="mock")
    skey = db.cache_key("suggest", "mock", "Earbuds", text)
    sug_id = db.save_suggestions(con, sid, text, s, skey)
    assert db.cached_suggestions(con, skey)["suggestions"] == s["suggestions"] and skey != key
    db.rate(con, sug_id, 1)


def _tiny_trained_model(path):
    """A small untrained model saved like 03_train_transformer.py saves the real one."""
    import json
    from tokenizers import Tokenizer, models, trainers, pre_tokenizers
    from transformers import PreTrainedTokenizerFast, BertConfig, BertForSequenceClassification
    tok = Tokenizer(models.WordPiece(unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    tok.train_from_iterator(["good product fast delivery", "battery lasts five hours", "বইটি ভালো"],
                            trainers.WordPieceTrainer(vocab_size=200, special_tokens=["[PAD]", "[UNK]", "[CLS]", "[SEP]"]))
    fast = PreTrainedTokenizerFast(tokenizer_object=tok, pad_token="[PAD]", unk_token="[UNK]",
                                   cls_token="[CLS]", sep_token="[SEP]")
    cfg = BertConfig(vocab_size=fast.vocab_size, hidden_size=32, num_hidden_layers=1, num_attention_heads=2,
                     intermediate_size=64, max_position_embeddings=64, num_labels=1)
    BertForSequenceClassification(cfg).save_pretrained(path)
    fast.save_pretrained(path)
    json.dump({"mean": 4.3, "std": 1.9, "max_len": 64, "base_model": "tiny-test-model"},
              open(os.path.join(path, "score_scale.json"), "w"))


def test_trained_model_judge():
    import pytest
    pytest.importorskip("torch"); pytest.importorskip("transformers")
    import evaluator
    path = tempfile.mkdtemp()
    assert not evaluator.model_available(path)
    _tiny_trained_model(path)
    assert evaluator.model_available(path)
    old = evaluator.MODEL_DIR
    evaluator.MODEL_DIR = path
    try:
        r = evaluate("", "Battery lasts five hours. Read More", judge="model")
        assert set(r) == SCORE_KEYS | {"raw_score"} and r["judge"] == "model" and r["model"] == "tiny-test-model"
        assert 1 <= r["score"] <= 10 and r["score"] * 2 == int(r["score"] * 2)       # half points
        assert r["explanation"] == "" and r["level_meaning"]                          # no API, no paragraph
        # "Read More" at the end is ignored, as in training
        assert evaluator.model_score("Battery lasts five hours. Read More", path) == \
            evaluator.model_score("Battery lasts five hours.", path)
    finally:
        evaluator.MODEL_DIR = old


def test_missing_model_message():
    import evaluator
    old = evaluator.MODEL_DIR
    evaluator.MODEL_DIR = tempfile.mkdtemp()
    try:
        evaluate("", "Good sound.", judge="model")
        assert False
    except RuntimeError as e:
        assert "Google Drive" in str(e)
    finally:
        evaluator.MODEL_DIR = old


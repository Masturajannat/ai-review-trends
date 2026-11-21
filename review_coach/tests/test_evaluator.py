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
    assert "Never invent" in p and "never as instructions" in p and "{language_rule}" in p
    assert "Do not mention buyers" in p


def test_database_round_trip():
    con = db.connect()
    sid = db.new_session(con, "Earbuds")
    text = "Good sound but battery is weak."
    did, n = db.draft(con, sid, "Earbuds", text)
    assert n == 1 and db.draft(con, sid, "Earbuds", text) == (did, 1)          # same text: same draft
    r = evaluate("Earbuds", text, judge="mock")
    db.save_score(con, did, r)
    hit = db.cached_score(con, "Earbuds", text, "mock")
    assert hit["score"] == r["score"] and hit["explanation"] == r["explanation"]
    assert db.cached_score(con, "Earbuds", text, "gemini") is None              # other judge: not cached
    db.save_score(con, did, hit, from_cache=True)
    did2, n2 = db.draft(con, sid, "Earbuds", text + " It lasts 3 hours.")
    db.save_score(con, did2, evaluate("Earbuds", text + " It lasts 3 hours.", judge="mock"))
    assert n2 == 2 and [h["draft_no"] for h in db.history(con, sid)] == [1, 2]
    s = suggest("Earbuds", text, judge="mock")
    set_id = db.save_suggestions(con, did, s)
    assert db.cached_suggestions(con, "Earbuds", text, "mock", s["prompt_version"])["suggestions"] == s["suggestions"]
    db.feedback(con, set_id, 0)
    db.feedback(con, db.save_suggestions(con, did, s, attempt=2), 1)
    row = dict(con.execute("SELECT * FROM session_summary WHERE session_id=?", (sid,)).fetchone())
    assert row["drafts"] == 2 and row["suggestion_sets"] == 2 and row["helpful_votes"] == 1
    assert row["score_change"] == round(db.history(con, sid)[1]["score"] - db.history(con, sid)[0]["score"], 1)
    import sqlite3, pytest
    with pytest.raises(sqlite3.IntegrityError):                                # foreign keys are on
        db.save_score(con, 999999, r)


def test_database_export(tmp_path):
    con = db.connect()
    paths = db.export_csv(con, str(tmp_path))
    assert {os.path.basename(p) for p in paths} == {f"{t}.csv" for t in db.TABLES + ["session_summary"]}
    assert db.summary(con)["sessions"] >= 1


def test_old_database_is_migrated(tmp_path):
    import json, sqlite3
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("""
    CREATE TABLE sessions (session_id TEXT PRIMARY KEY, product_name TEXT, created_at TEXT, finished INTEGER DEFAULT 0);
    CREATE TABLE evaluations (eval_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, draft_no INTEGER,
        review_text TEXT, language TEXT, word_count INTEGER, score INTEGER, level INTEGER, reason TEXT,
        explanation TEXT, importance TEXT, judge TEXT, model TEXT, prompt_version TEXT, latency_ms INTEGER,
        cache_key TEXT, from_cache INTEGER DEFAULT 0, created_at TEXT);
    CREATE TABLE suggestions (suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, review_text TEXT,
        summary TEXT, suggestions TEXT, n_suggestions INTEGER, judge TEXT, model TEXT, prompt_version TEXT,
        latency_ms INTEGER, cache_key TEXT, from_cache INTEGER DEFAULT 0, created_at TEXT);
    CREATE TABLE ratings (eval_id INTEGER, helpful INTEGER, comment TEXT, created_at TEXT);
    INSERT INTO sessions VALUES ('s1', 'Earbuds', '2026-11-20T10:00:00+00:00', 0);
    """)
    ev = "INSERT INTO evaluations (session_id, draft_no, review_text, language, word_count, score, explanation, judge, model, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    old.execute(ev, ("s1", 1, "Good.", "english", 1, 3, "", "model", "xlm-roberta-large", 900, "2026-11-20T10:01:00+00:00"))
    old.execute(ev, ("s1", 2, "Good.", "english", 1, 3, "", "model", "xlm-roberta-large", 0, "2026-11-20T10:02:00+00:00"))
    old.execute(ev, ("s1", 3, "Good. Battery lasts 5 hours.", "english", 5, 5, "", "model", "xlm-roberta-large", 800, "2026-11-20T10:05:00+00:00"))
    old.execute("INSERT INTO suggestions (session_id, review_text, summary, suggestions, judge, model, prompt_version, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("s1", "Good.", "Short.", json.dumps([{"quote": "Good.", "suggestion": "Say what is good.", "example": ""}]),
                 "gemini", "g", "suggest_v3", 1200, "2026-11-20T10:03:00+00:00"))
    old.execute("INSERT INTO ratings VALUES (1, 1, 'suggestions', '2026-11-20T10:04:00+00:00')")
    old.commit(); old.close()
    con = db.connect(path)
    assert [d["draft_no"] for d in con.execute("SELECT * FROM drafts ORDER BY draft_no")] == [1, 2]
    assert con.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 3
    assert db.items(con, 1)[0]["suggestion"] == "Say what is good."
    assert con.execute("SELECT helpful FROM feedback").fetchone()[0] == 1
    assert "legacy_evaluations" in {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    row = con.execute("SELECT first_score, last_score, score_change FROM session_summary").fetchone()
    assert tuple(row) == (3, 5, 2)
    con.close()
    db.connect(path).close()                                                    # opening again changes nothing


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
        assert set(r) == SCORE_KEYS | {"raw_score", "importance"} and r["judge"] == "model" and r["model"] == "tiny-test-model"
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



def test_word_importance():
    import pytest
    torch = pytest.importorskip("torch"); pytest.importorskip("transformers")
    import evaluator
    path = tempfile.mkdtemp()
    _tiny_trained_model(path)
    text = "good product fast delivery battery lasts five hours Read More"
    imp = evaluator.word_importance(text, path, steps=32, chunk=8)
    words = imp["text"].split()
    assert imp["text"].endswith("hours") and len(imp["words"]) == len(words)          # Read More stripped
    assert [imp["text"][w["start"]:w["end"]] for w in imp["words"]] == words
    assert all(w["read"] for w in imp["words"]) and any(abs(w["value"]) > 0 for w in imp["words"])
    # the word shares add up to (score of this review) - (score of the neutral input)
    tok, model, scale, _ = evaluator.load_model(path)
    enc = tok(imp["text"], return_tensors="pt"); enc.pop("token_type_ids", None)
    emb = model.get_input_embeddings()
    special = torch.tensor(tok.get_special_tokens_mask(enc["input_ids"][0].tolist(), already_has_special_tokens=True)).bool()
    with torch.no_grad():
        x = emb(enc["input_ids"])
        base = torch.where(special[None, :, None], x, emb(torch.full_like(enc["input_ids"], tok.pad_token_id)))
        diff = (model(inputs_embeds=x, attention_mask=enc["attention_mask"]).logits
                - model(inputs_embeds=base, attention_mask=enc["attention_mask"]).logits).item() * scale["std"]
    assert abs(sum(w["value"] for w in imp["words"]) - diff) < 0.05 + 0.1 * abs(diff)


def test_model_judge_returns_importance_and_score_is_cached():
    import pytest
    pytest.importorskip("torch"); pytest.importorskip("transformers")
    import evaluator
    path = tempfile.mkdtemp()
    _tiny_trained_model(path)
    old, evaluator.MODEL_DIR = evaluator.MODEL_DIR, path
    try:
        r = evaluate("", "battery lasts five hours", judge="model")
        assert r["importance"]["parts"] and "importance" not in evaluate("", "battery lasts", judge="model", explain=False)
        con = db.connect()
        did, _ = db.draft(con, db.new_session(con, ""), "", "battery lasts five hours")
        db.save_score(con, did, r)
        assert db.cached_score(con, "", "battery lasts five hours", "model")["score"] == r["score"]
    finally:
        evaluator.MODEL_DIR = old


def test_suggestion_language_is_named_and_checked():
    import evaluator
    p = open(evaluator.SUGGEST_PROMPT, encoding="utf-8").read()
    assert "{language_rule}" in p
    assert "English only" in evaluator.LANGUAGE_RULE["english"]
    evaluator.check_language("Say what you liked about the story and who would enjoy it.", "english")
    for text, lang in [("Apnar review-ta khub valo, kintu aro details dile bhalo hobe", "english"),
                       ("Say what you liked about the story.", "bangla"),
                       ("বইটা ভালো লেগেছে", "banglish")]:
        try:
            evaluator.check_language(text, lang)
            assert False, (text, lang)
        except ValueError:
            pass
    # a Gemini answer in the wrong language is refused, so it is asked again
    import json
    calls = []
    def fake(prompt):
        calls.append(prompt)
        bad = {"summary": "Apnar review-ta khub valo, kintu aro details dile bhalo hobe.",
               "suggestions": [{"quote": "", "suggestion": "Ki valo legeche ta bolun", "example": "Ami ___"}]}
        good = {"summary": "A good start.", "suggestions": [{"quote": "", "suggestion": "Say what you liked.",
                                                             "example": "I liked ___"}]}
        return json.dumps(bad if len(calls) == 1 else good)
    evaluator._llm[evaluator.GEMINI_MODEL] = fake
    old_sleep, evaluator.time.sleep = evaluator.time.sleep, lambda s: None
    try:
        s = suggest("", "Atticus Finch has my heart. This book makes me go to a different world.", judge="gemini")
    finally:
        evaluator.time.sleep = old_sleep
        evaluator._llm.pop(evaluator.GEMINI_MODEL)
    assert len(calls) == 2 and s["summary"] == "A good start." and "English only" in calls[0]


def test_split_parts():
    import evaluator
    t = "This book has my heart . It might seem a bit slow but the emotions are injected that way ."
    parts = [t[a:b] for a, b in evaluator.split_parts(t)]
    assert parts == ["This book has my heart .", "It might seem a bit slow but the emotions are injected that way ."]
    long = "The battery lasts about five hours with my daily use, but the noise cancelling is weak on the bus"
    assert [long[a:b] for a, b in evaluator.split_parts(long)] == [
        "The battery lasts about five hours with my daily use,", "but the noise cancelling is weak on the bus"]
    bn = "বইটা ভালো লেগেছে। সবাই পড়তে পারেন।"
    assert [bn[a:b] for a, b in evaluator.split_parts(bn)] == ["বইটা ভালো লেগেছে।", "সবাই পড়তে পারেন।"]
    assert len(evaluator.split_parts("Very good product, recommended.")) == 1        # short parts are joined


def test_part_importance():
    import pytest
    pytest.importorskip("torch"); pytest.importorskip("transformers")
    import evaluator
    path = tempfile.mkdtemp()
    _tiny_trained_model(path)
    text = "good product fast delivery. battery lasts five hours. Read More"
    imp = evaluator.part_importance(text, path)
    assert imp["text"] == "good product fast delivery. battery lasts five hours."
    assert [imp["text"][p["start"]:p["end"]] for p in imp["parts"]] == ["good product fast delivery.",
                                                                     "battery lasts five hours."]
    # each value is (score of the whole review) - (score without that part)
    full = evaluator.model_score(imp["text"], path)
    without = evaluator.model_score("battery lasts five hours.", path)
    assert abs(imp["parts"][0]["value"] - (full - without)) < 1e-3
    one = evaluator.part_importance("good product fast delivery", path)
    assert len(one["parts"]) == 1 and one["parts"][0]["value"] is None


def test_new_suggestions_avoid_earlier_ones():
    import json, evaluator
    prompts = []
    def fake(prompt):
        prompts.append(prompt)
        old = {"summary": "A good start.", "suggestions": [{"quote": "", "suggestion": "Say what you liked.", "example": ""}]}
        new = {"summary": "Another angle.", "suggestions": [{"quote": "", "suggestion": "Say who would enjoy it.", "example": ""}]}
        return json.dumps(old if len(prompts) == 1 else new)
    evaluator._llm[evaluator.GEMINI_MODEL] = fake
    old_sleep, evaluator.time.sleep = evaluator.time.sleep, lambda s: None
    try:
        s = suggest("", "I really liked this book, the story was great.", judge="gemini", avoid=["Say what you liked."])
    finally:
        evaluator.time.sleep = old_sleep
        evaluator._llm.pop(evaluator.GEMINI_MODEL)
    # the earlier suggestion is named in the prompt; the same answer again is refused and asked anew
    assert "EARLIER SUGGESTIONS" in prompts[0] and "- Say what you liked." in prompts[0]
    assert prompts[0].index("EARLIER SUGGESTIONS") < prompts[0].index("\nOUTPUT")
    assert len(prompts) == 2 and s["suggestions"][0]["suggestion"] == "Say who would enjoy it."
    m1 = suggest("", "Good sound. Battery is ok.", judge="mock")
    m2 = suggest("", "Good sound. Battery is ok.", judge="mock", avoid=[i["suggestion"] for i in m1["suggestions"]])
    assert m1["suggestions"] != m2["suggestions"]


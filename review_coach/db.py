"""SQLite database for Review Coach (one file, review_coach.db, made by Python's built-in sqlite3).

Tables (one row per ...)
  sessions          review a person starts: product, when, finished or not
  drafts            version of the review text in a session (the same text is saved once)
  scores            rating of a draft: score shown, exact model output, judge, model, time taken
  suggestion_sets   click on "Suggest improvements" (attempt 1) or "Show different ones" (2, 3, ...)
  suggestion_items  single suggestion in a set: the quoted words, the advice, an example
  feedback          "Suggestions helped" (1) or "Not helpful" (0) for a set

View
  session_summary   per session: drafts, first and last score, change, suggestion sets, helpful votes

Foreign keys are on, so a score cannot point to a draft that does not exist.
No names, emails, IP addresses or API keys are stored, only the review text and the results.

A database made by the earlier version of the app (tables evaluations, suggestions, ratings) is
copied into these tables the first time it is opened; the old tables are kept as legacy_*.

Export everything to CSV for the report:  python export_db.py   (writes db_export/*.csv)
"""
import csv, hashlib, json, os, sqlite3, uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get("REVIEW_COACH_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "review_coach.db"))
VERSION = 2
TABLES = ["sessions", "drafts", "scores", "suggestion_sets", "suggestion_items", "feedback"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    product_name TEXT,
    created_at   TEXT NOT NULL,
    finished     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS drafts (
    draft_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(session_id),
    draft_no     INTEGER NOT NULL,
    product_name TEXT,
    review_text  TEXT NOT NULL,
    text_hash    TEXT NOT NULL,
    word_count   INTEGER,
    language     TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE (session_id, draft_no)
);
CREATE INDEX IF NOT EXISTS idx_drafts_session ON drafts(session_id);
CREATE INDEX IF NOT EXISTS idx_drafts_hash ON drafts(text_hash);
CREATE TABLE IF NOT EXISTS scores (
    score_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id       INTEGER NOT NULL REFERENCES drafts(draft_id),
    score          REAL NOT NULL,
    raw_score      REAL,
    reason         TEXT,
    explanation    TEXT,
    judge          TEXT NOT NULL,
    model          TEXT,
    prompt_version TEXT,
    latency_ms     INTEGER,
    from_cache     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scores_draft ON scores(draft_id);
CREATE TABLE IF NOT EXISTS suggestion_sets (
    set_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id       INTEGER NOT NULL REFERENCES drafts(draft_id),
    attempt        INTEGER NOT NULL DEFAULT 1,
    summary        TEXT,
    judge          TEXT NOT NULL,
    model          TEXT,
    prompt_version TEXT,
    latency_ms     INTEGER,
    from_cache     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sets_draft ON suggestion_sets(draft_id);
CREATE TABLE IF NOT EXISTS suggestion_items (
    item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id     INTEGER NOT NULL REFERENCES suggestion_sets(set_id),
    position   INTEGER NOT NULL,
    quote      TEXT,
    suggestion TEXT NOT NULL,
    example    TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_set ON suggestion_items(set_id);
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id      INTEGER NOT NULL REFERENCES suggestion_sets(set_id),
    helpful     INTEGER NOT NULL CHECK (helpful IN (0, 1)),
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_set ON feedback(set_id);
DROP VIEW IF EXISTS session_summary;
CREATE VIEW session_summary AS
WITH scored AS (
    SELECT d.session_id, d.draft_no, s.score,
           ROW_NUMBER() OVER (PARTITION BY d.draft_id ORDER BY s.score_id DESC) AS latest
    FROM drafts d JOIN scores s ON s.draft_id = d.draft_id),
per_draft AS (SELECT * FROM scored WHERE latest = 1),
ends AS (
    SELECT session_id, COUNT(*) AS scored_drafts,
           (SELECT score FROM per_draft p2 WHERE p2.session_id = p.session_id ORDER BY draft_no LIMIT 1) AS first_score,
           (SELECT score FROM per_draft p2 WHERE p2.session_id = p.session_id ORDER BY draft_no DESC LIMIT 1) AS last_score
    FROM per_draft p GROUP BY session_id)
SELECT se.session_id, se.product_name, se.created_at,
       (SELECT COUNT(*) FROM drafts d WHERE d.session_id = se.session_id) AS drafts,
       COALESCE(e.scored_drafts, 0) AS scored_drafts,
       e.first_score, e.last_score, ROUND(e.last_score - e.first_score, 1) AS score_change,
       (SELECT COUNT(*) FROM suggestion_sets ss JOIN drafts d ON d.draft_id = ss.draft_id
         WHERE d.session_id = se.session_id) AS suggestion_sets,
       (SELECT SUM(f.helpful) FROM feedback f JOIN suggestion_sets ss ON ss.set_id = f.set_id
         JOIN drafts d ON d.draft_id = ss.draft_id WHERE d.session_id = se.session_id) AS helpful_votes,
       (SELECT COUNT(*) FROM feedback f JOIN suggestion_sets ss ON ss.set_id = f.set_id
         JOIN drafts d ON d.draft_id = ss.draft_id WHERE d.session_id = se.session_id) AS feedback_votes
FROM sessions se LEFT JOIN ends e ON e.session_id = se.session_id;
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text_hash(product, review):
    """Same product + same review text = same hash: used to find a draft or an earlier result."""
    return hashlib.sha256(f"{(product or '').strip()}|{review.strip()}".encode("utf-8")).hexdigest()


def _tables(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def connect(path=DB_PATH):
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    old = "evaluations" in _tables(con)
    if old:                                          # earlier app version: keep its tables under new names
        for t in ("evaluations", "suggestions", "ratings"):
            if t in _tables(con):
                con.execute(f"ALTER TABLE {t} RENAME TO legacy_{t}")
    con.executescript(SCHEMA)
    if old:
        _migrate(con)
    con.execute(f"PRAGMA user_version = {VERSION}")
    con.commit()
    return con


def _insert(con, table, vals, commit=True):
    try:
        cur = con.execute(f"INSERT INTO {table} ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})",
                          list(vals.values()))
    except sqlite3.Error:
        con.rollback()                               # don't leave the database locked
        raise
    if commit:
        con.commit()
    return cur.lastrowid


# ---------------------------------------------------------------- sessions and drafts
def new_session(con, product):
    sid = uuid.uuid4().hex
    _insert(con, "sessions", dict(session_id=sid, product_name=product, created_at=now(), finished=0))
    return sid


def update_session(con, sid, product):
    con.execute("UPDATE sessions SET product_name=? WHERE session_id=?", (product, sid))
    con.commit()


def finish(con, sid):
    con.execute("UPDATE sessions SET finished=1 WHERE session_id=?", (sid,))
    con.commit()


def draft(con, sid, product, review, language=None, created_at=None, commit=True):
    """The draft for this text in this session: the existing one if the text was saved before,
    otherwise a new one with the next draft number. Returns (draft_id, draft_no)."""
    h = text_hash(product, review)
    row = con.execute("SELECT draft_id, draft_no FROM drafts WHERE session_id=? AND text_hash=? "
                      "ORDER BY draft_no DESC LIMIT 1", (sid, h)).fetchone()
    if row:
        return row["draft_id"], row["draft_no"]
    if language is None:
        from evaluator import detect_language
        language = detect_language(review)
    n = con.execute("SELECT COALESCE(MAX(draft_no), 0) FROM drafts WHERE session_id=?", (sid,)).fetchone()[0] + 1
    did = _insert(con, "drafts", dict(session_id=sid, draft_no=n, product_name=product, review_text=review,
                                      text_hash=h, word_count=len(review.split()), language=language,
                                      created_at=created_at or now()), commit=commit)
    return did, n


# ---------------------------------------------------------------- scores
def cached_score(con, product, review, judge):
    """An earlier score for exactly this product + review from this judge, as an evaluate() result."""
    row = con.execute("""SELECT s.*, d.language, d.word_count FROM scores s JOIN drafts d ON d.draft_id = s.draft_id
                         WHERE d.text_hash=? AND s.judge=? AND s.from_cache=0 AND s.explanation IS NOT NULL
                         ORDER BY s.score_id DESC LIMIT 1""", (text_hash(product, review), judge)).fetchone()
    if row is None:
        return None
    from evaluator import explain_level
    lvl, meaning = explain_level(row["score"])
    return {"score": row["score"], "level": lvl, "level_meaning": meaning, "reason": row["reason"],
            "explanation": row["explanation"], "judge": row["judge"], "model": row["model"],
            "prompt_version": row["prompt_version"], "latency_ms": 0, "language": row["language"],
            "word_count": row["word_count"]}


def save_score(con, draft_id, r, from_cache=False):
    return _insert(con, "scores", dict(
        draft_id=draft_id, score=r["score"], raw_score=r.get("raw_score", r["score"]), reason=r.get("reason"),
        explanation=r.get("explanation"), judge=r["judge"], model=r.get("model"),
        prompt_version=r.get("prompt_version"), latency_ms=0 if from_cache else r.get("latency_ms"),
        from_cache=int(from_cache), created_at=now()))


def history(con, sid):
    """The latest score of each scored draft in a session, in draft order."""
    return [dict(r) for r in con.execute("""
        SELECT d.draft_id, d.draft_no, d.word_count, d.review_text, s.score, s.created_at
        FROM drafts d JOIN scores s ON s.score_id = (SELECT MAX(score_id) FROM scores WHERE draft_id = d.draft_id)
        WHERE d.session_id=? ORDER BY d.draft_no""", (sid,))]


# ---------------------------------------------------------------- suggestions and feedback
def cached_suggestions(con, product, review, judge, prompt_version):
    """The first set of suggestions given earlier for exactly this text, judge and prompt."""
    row = con.execute("""SELECT ss.* FROM suggestion_sets ss JOIN drafts d ON d.draft_id = ss.draft_id
                         WHERE d.text_hash=? AND ss.judge=? AND ss.prompt_version=? AND ss.attempt=1
                         AND ss.from_cache=0 ORDER BY ss.set_id DESC LIMIT 1""",
                      (text_hash(product, review), judge, prompt_version)).fetchone()
    if row is None:
        return None
    return {"summary": row["summary"], "suggestions": items(con, row["set_id"]), "judge": row["judge"],
            "model": row["model"], "prompt_version": row["prompt_version"], "latency_ms": 0}


def items(con, set_id):
    return [{"quote": r["quote"] or "", "suggestion": r["suggestion"], "example": r["example"] or ""}
            for r in con.execute("SELECT * FROM suggestion_items WHERE set_id=? ORDER BY position", (set_id,))]


def save_suggestions(con, draft_id, s, attempt=1, from_cache=False, created_at=None, commit=True):
    set_id = _insert(con, "suggestion_sets", dict(
        draft_id=draft_id, attempt=attempt, summary=s.get("summary"), judge=s["judge"], model=s.get("model"),
        prompt_version=s.get("prompt_version"), latency_ms=0 if from_cache else s.get("latency_ms"),
        from_cache=int(from_cache), created_at=created_at or now()), commit=False)
    for n, i in enumerate(s["suggestions"], 1):
        _insert(con, "suggestion_items", dict(set_id=set_id, position=n, quote=i.get("quote"),
                                              suggestion=i["suggestion"], example=i.get("example")), commit=False)
    if commit:
        con.commit()
    return set_id


def feedback(con, set_id, helpful):
    return _insert(con, "feedback", dict(set_id=set_id, helpful=int(bool(helpful)), created_at=now()))


# ---------------------------------------------------------------- report
def summary(con):
    """Numbers for the report, over all sessions."""
    q = lambda sql: con.execute(sql).fetchone()[0]
    return {
        "sessions": q("SELECT COUNT(*) FROM sessions"),
        "drafts": q("SELECT COUNT(*) FROM drafts"),
        "scores": q("SELECT COUNT(*) FROM scores"),
        "suggestion_sets": q("SELECT COUNT(*) FROM suggestion_sets"),
        "helpful_share": q("SELECT AVG(helpful) FROM feedback"),
        "mean_change": q("SELECT AVG(score_change) FROM session_summary WHERE scored_drafts > 1"),
        "model_ms": q("SELECT AVG(latency_ms) FROM scores WHERE judge='model' AND from_cache=0"),
        "gemini_ms": q("SELECT AVG(latency_ms) FROM scores WHERE judge='gemini' AND from_cache=0"),
    }


def export_csv(con, folder):
    """Every table and the session_summary view as CSV files (UTF-8, opens in Excel). Returns the paths."""
    os.makedirs(folder, exist_ok=True)
    paths = []
    for name in TABLES + ["session_summary"]:
        cur = con.execute(f"SELECT * FROM {name}")
        p = os.path.join(folder, f"{name}.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([c[0] for c in cur.description])
            w.writerows(cur)
        paths.append(p)
    return paths


# ---------------------------------------------------------------- one-time copy of an old database
def _migrate(con):
    t = _tables(con)
    evals = con.execute("SELECT * FROM legacy_evaluations ORDER BY eval_id").fetchall() if "legacy_evaluations" in t else []
    sugs = con.execute("SELECT * FROM legacy_suggestions ORDER BY suggestion_id").fetchall() if "legacy_suggestions" in t else []
    rates = con.execute("SELECT * FROM legacy_ratings").fetchall() if "legacy_ratings" in t else []
    product = {r["session_id"]: r["product_name"] or "" for r in con.execute("SELECT * FROM sessions")}
    for sid in {r["session_id"] for r in list(evals) + list(sugs)} - set(product):
        con.execute("INSERT INTO sessions (session_id, product_name, created_at) VALUES (?, '', ?)", (sid, now()))
        product[sid] = ""
    # replay in time order so draft numbers follow what the person did
    events = sorted([("e", r["created_at"] or "", r) for r in evals] + [("s", r["created_at"] or "", r) for r in sugs],
                    key=lambda e: e[1])
    set_of = {}
    for kind, when, r in events:
        did, _ = draft(con, r["session_id"], product[r["session_id"]], r["review_text"] or "",
                       language=r["language"] if kind == "e" else None, created_at=when, commit=False)
        if kind == "e":
            _insert(con, "scores", dict(draft_id=did, score=r["score"], raw_score=r["score"], reason=r["reason"],
                                        explanation=r["explanation"], judge=r["judge"], model=r["model"],
                                        prompt_version=r["prompt_version"], latency_ms=r["latency_ms"],
                                        from_cache=r["from_cache"], created_at=when), commit=False)
        else:
            attempt = 1 + con.execute("SELECT COUNT(*) FROM suggestion_sets WHERE draft_id=?", (did,)).fetchone()[0]
            s = {"summary": r["summary"], "suggestions": json.loads(r["suggestions"] or "[]"), "judge": r["judge"],
                 "model": r["model"], "prompt_version": r["prompt_version"], "latency_ms": r["latency_ms"]}
            set_of[r["suggestion_id"]] = save_suggestions(con, did, s, attempt=attempt, from_cache=bool(r["from_cache"]),
                                                          created_at=when, commit=False)
    for r in rates:                                  # the old column eval_id held the suggestion id
        if r["eval_id"] in set_of and r["helpful"] is not None:
            _insert(con, "feedback", dict(set_id=set_of[r["eval_id"]], helpful=int(bool(r["helpful"])),
                                          created_at=r["created_at"] or now()), commit=False)

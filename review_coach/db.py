"""SQLite storage for Review Coach.

Tables
  sessions     one review being written: product, when, finished or not
  evaluations  one row per click on "Rate my review": the draft, its score and reasons,
               which judge gave it, how long it took
  suggestions  one row per click on "Suggest improvements": the draft and the suggestions given
  ratings      whether the user found the suggestions helpful

No names, emails or API keys are stored. A database made by an earlier version of the app
(with a product type and checklist columns) keeps working; the extra columns stay empty.
"""
import hashlib, json, os, sqlite3, uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get("REVIEW_COACH_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "review_coach.db"))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=DB_PATH):
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id   TEXT PRIMARY KEY,
        product_name TEXT,
        created_at   TEXT,
        finished     INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS evaluations (
        eval_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id     TEXT REFERENCES sessions(session_id),
        draft_no       INTEGER,
        review_text    TEXT,
        language       TEXT,
        word_count     INTEGER,
        score          INTEGER,
        level          INTEGER,
        reason         TEXT,
        explanation    TEXT,
        judge          TEXT,
        model          TEXT,
        prompt_version TEXT,
        latency_ms     INTEGER,
        cache_key      TEXT,
        from_cache     INTEGER DEFAULT 0,
        created_at     TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_eval_cache ON evaluations(cache_key);
    CREATE INDEX IF NOT EXISTS idx_eval_session ON evaluations(session_id);
    CREATE TABLE IF NOT EXISTS suggestions (
        suggestion_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id     TEXT REFERENCES sessions(session_id),
        review_text    TEXT,
        summary        TEXT,
        suggestions    TEXT,
        n_suggestions  INTEGER,
        judge          TEXT,
        model          TEXT,
        prompt_version TEXT,
        latency_ms     INTEGER,
        cache_key      TEXT,
        from_cache     INTEGER DEFAULT 0,
        created_at     TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_sug_cache ON suggestions(cache_key);
    CREATE TABLE IF NOT EXISTS ratings (
        eval_id    INTEGER,
        helpful    INTEGER,
        comment    TEXT,
        created_at TEXT
    );
    """)
    have = {r[1] for r in con.execute("PRAGMA table_info(evaluations)")}
    for col in ("explanation",):                        # a database made by an earlier version
        if col not in have:
            con.execute(f"ALTER TABLE evaluations ADD COLUMN {col} TEXT")
    con.commit()
    return con


def _insert(con, table, vals):
    cur = con.execute(f"INSERT INTO {table} ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})",
                      list(vals.values()))
    con.commit()
    return cur.lastrowid


def new_session(con, product):
    sid = uuid.uuid4().hex
    _insert(con, "sessions", dict(session_id=sid, product_name=product, created_at=now(), finished=0))
    return sid


def update_session(con, sid, product):
    con.execute("UPDATE sessions SET product_name=? WHERE session_id=?", (product, sid))
    con.commit()


def cache_key(kind, judge, product, review):
    return hashlib.sha256(f"{kind}|{judge}|{product.strip()}|{review.strip()}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- scores
def cached_score(con, key):
    """An earlier score for exactly this judge + product + review, as an evaluate() result."""
    row = con.execute("SELECT * FROM evaluations WHERE cache_key=? AND from_cache=0 ORDER BY eval_id DESC LIMIT 1",
                      (key,)).fetchone()
    if row is None:
        return None
    from evaluator import explain_level
    lvl, meaning = explain_level(row["score"])
    if row["explanation"] is None:        # scored before the explanation was added: score it again
        return None
    return {"score": row["score"], "level": lvl, "level_meaning": meaning, "reason": row["reason"],
            "explanation": row["explanation"],
            "judge": row["judge"], "model": row["model"], "prompt_version": row["prompt_version"],
            "latency_ms": 0, "language": row["language"], "word_count": row["word_count"]}


def save_score(con, sid, review, r, key, from_cache=False):
    n = con.execute("SELECT COUNT(*) FROM evaluations WHERE session_id=?", (sid,)).fetchone()[0] + 1
    eid = _insert(con, "evaluations", dict(
        session_id=sid, draft_no=n, review_text=review, language=r["language"], word_count=r["word_count"],
        score=r["score"], level=r["level"], reason=r["reason"],
        explanation=r["explanation"], judge=r["judge"], model=r["model"],
        prompt_version=r["prompt_version"], latency_ms=0 if from_cache else r["latency_ms"],
        cache_key=key, from_cache=int(from_cache), created_at=now()))
    return eid, n


def history(con, sid):
    return [dict(r) for r in con.execute(
        "SELECT eval_id, draft_no, score, review_text, created_at FROM evaluations WHERE session_id=? ORDER BY draft_no",
        (sid,))]


# ---------------------------------------------------------------- suggestions
def cached_suggestions(con, key):
    row = con.execute("SELECT * FROM suggestions WHERE cache_key=? AND from_cache=0 "
                      "ORDER BY suggestion_id DESC LIMIT 1", (key,)).fetchone()
    if row is None:
        return None
    return {"summary": row["summary"], "suggestions": json.loads(row["suggestions"] or "[]"),
            "judge": row["judge"], "model": row["model"], "prompt_version": row["prompt_version"],
            "latency_ms": 0}


def save_suggestions(con, sid, review, s, key, from_cache=False):
    return _insert(con, "suggestions", dict(
        session_id=sid, review_text=review, summary=s["summary"],
        suggestions=json.dumps(s["suggestions"], ensure_ascii=False), n_suggestions=len(s["suggestions"]),
        judge=s["judge"], model=s["model"], prompt_version=s["prompt_version"],
        latency_ms=0 if from_cache else s["latency_ms"], cache_key=key, from_cache=int(from_cache),
        created_at=now()))


def rate(con, suggestion_id, helpful, comment="suggestions"):
    _insert(con, "ratings", dict(eval_id=suggestion_id, helpful=int(helpful), comment=comment, created_at=now()))


def finish(con, sid):
    con.execute("UPDATE sessions SET finished=1 WHERE session_id=?", (sid,))
    con.commit()

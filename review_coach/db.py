"""SQLite storage for Review Coach: one row per check of a draft.

Tables
  sessions     one review being written: product, category, when, finished or not
  evaluations  one row per click on "Check my review": the draft, its score, the ten checks,
               the tips, which judge gave them, how long it took
  ratings      whether the user found the tips helpful

The check columns have the same names as in the scored dataset (check_product_detail ...),
so app data and training data can be compared directly. No names, emails or API keys are stored.
"""
import hashlib, json, os, sqlite3, uuid
from datetime import datetime, timezone

from evaluator import CHECKS

DB_PATH = os.environ.get("REVIEW_COACH_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "review_coach.db"))
CHECK_COLS = [f"check_{c}" for c in CHECKS]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=DB_PATH):
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(f"""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id   TEXT PRIMARY KEY,
        product_name TEXT,
        category     TEXT,
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
        {", ".join(c + " INTEGER" for c in CHECK_COLS)},
        weak_criteria  TEXT,
        how_to_improve TEXT,
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
    CREATE TABLE IF NOT EXISTS ratings (
        eval_id    INTEGER REFERENCES evaluations(eval_id),
        helpful    INTEGER,
        comment    TEXT,
        created_at TEXT
    );
    """)
    return con


def new_session(con, product, category):
    sid = uuid.uuid4().hex
    con.execute("INSERT INTO sessions VALUES (?,?,?,?,0)", (sid, product, category, now()))
    con.commit()
    return sid


def update_session(con, sid, product, category):
    con.execute("UPDATE sessions SET product_name=?, category=? WHERE session_id=?", (product, category, sid))
    con.commit()


def cache_key(judge, product, review):
    return hashlib.sha256(f"{judge}|{product.strip()}|{review.strip()}".encode("utf-8")).hexdigest()


def cached(con, key):
    """An earlier result for exactly this judge + product + review, rebuilt as an evaluate() result."""
    row = con.execute("SELECT * FROM evaluations WHERE cache_key=? AND from_cache=0 ORDER BY eval_id DESC LIMIT 1",
                      (key,)).fetchone()
    return None if row is None else row_to_result(row)


def save(con, sid, review, r, key, from_cache=False):
    n = con.execute("SELECT COUNT(*) FROM evaluations WHERE session_id=?", (sid,)).fetchone()[0] + 1
    vals = dict(session_id=sid, draft_no=n, review_text=review, language=r["language"],
                word_count=r["word_count"], score=r["score"], level=r["level"], reason=r["reason"],
                weak_criteria="|".join(r["weak_criteria"]),
                how_to_improve=json.dumps(r["how_to_improve"], ensure_ascii=False),
                judge=r["judge"], model=r["model"], prompt_version=r["prompt_version"],
                latency_ms=0 if from_cache else r["latency_ms"], cache_key=key,
                from_cache=int(from_cache), created_at=now())
    vals.update({f"check_{k}": v for k, v in r["checks"].items()})
    cols = ", ".join(vals)
    cur = con.execute(f"INSERT INTO evaluations ({cols}) VALUES ({', '.join('?' * len(vals))})", list(vals.values()))
    con.commit()
    return cur.lastrowid, n


def row_to_result(row):
    from evaluator import _result, explain_level
    import time
    checks = {c: row[f"check_{c}"] for c in CHECKS}
    r = _result(row["score"], row["reason"], checks, [w for w in (row["weak_criteria"] or "").split("|") if w],
                json.loads(row["how_to_improve"] or "{}"), row["judge"], row["model"], time.time())
    r.update(language=row["language"], word_count=row["word_count"], latency_ms=0)
    return r


def history(con, sid):
    return [dict(r) for r in con.execute(
        "SELECT eval_id, draft_no, score, review_text, created_at FROM evaluations WHERE session_id=? ORDER BY draft_no",
        (sid,))]


def rate(con, eval_id, helpful, comment=""):
    con.execute("INSERT INTO ratings VALUES (?,?,?,?)", (eval_id, int(helpful), comment, now()))
    con.commit()


def finish(con, sid):
    con.execute("UPDATE sessions SET finished=1 WHERE session_id=?", (sid,))
    con.commit()

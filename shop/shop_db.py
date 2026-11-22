"""The dummy shop's database (shop.db): products and their reviews.

Used by the shop (shop_app.py) to show them and by Review Coach to add a new review.
Create it once with:  python build_shop_db.py
"""
import os, sqlite3
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = os.environ.get("SHOP_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "shop.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    platform   TEXT,
    name       TEXT NOT NULL,
    type       TEXT NOT NULL            -- what kind of product it is, e.g. "body wash"
);
CREATE TABLE IF NOT EXISTS reviews (
    review_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  TEXT NOT NULL REFERENCES products(product_id),
    review_text TEXT NOT NULL,
    language    TEXT,                   -- english, bangla, banglish or unknown
    score       REAL,                   -- Review Coach score; empty for the dataset's reviews
    written_at  TEXT,                   -- ISO date; newest first
    source      TEXT NOT NULL           -- "dataset" or "coach"
);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id, written_at);
"""


def connect(path=None):
    path = path or DB_PATH
    if not os.path.exists(path):           # sqlite would quietly make an empty file
        raise FileNotFoundError(f"{path} not found. Run 'python build_shop_db.py' in the shop folder first.")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def products():
    """All products with their number of reviews, most reviewed first."""
    with closing(connect()) as con:
        return con.execute("SELECT p.*, COUNT(r.review_id) AS n FROM products p "
                           "LEFT JOIN reviews r ON r.product_id = p.product_id "
                           "GROUP BY p.product_id ORDER BY n DESC, p.name").fetchall()


def product(product_id):
    """One product (with its review count), or None if there is no such product."""
    with closing(connect()) as con:
        return con.execute("SELECT p.*, COUNT(r.review_id) AS n FROM products p "
                           "LEFT JOIN reviews r ON r.product_id = p.product_id "
                           "WHERE p.product_id = ? GROUP BY p.product_id", (str(product_id),)).fetchone()


def reviews(product_id, language=None, limit=20):
    """(reviews, total): the newest `limit` reviews of the product, optionally of one language."""
    where, args = "product_id = ?", [str(product_id)]
    if language:
        where += " AND language = ?"
        args.append(language)
    with closing(connect()) as con:
        total = con.execute(f"SELECT COUNT(*) FROM reviews WHERE {where}", args).fetchone()[0]
        rows = con.execute(f"SELECT * FROM reviews WHERE {where} "
                           "ORDER BY written_at IS NULL, written_at DESC, review_id DESC LIMIT ?",
                           args + [limit]).fetchall()
    return rows, total


def add_review(product_id, text, score, language):
    """Add a review written in Review Coach; it shows first in the product's list."""
    text = (text or "").strip()
    if not text:
        raise ValueError("The review is empty.")
    with closing(connect()) as con:
        if con.execute("SELECT 1 FROM products WHERE product_id = ?", (str(product_id),)).fetchone() is None:
            raise ValueError(f"No product {product_id}.")
        cur = con.execute("INSERT INTO reviews (product_id, review_text, language, score, written_at, source) "
                          "VALUES (?, ?, ?, ?, ?, 'coach')",
                          (str(product_id), text, language, score, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        con.commit()
        return cur.lastrowid

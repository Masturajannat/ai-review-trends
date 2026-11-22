"""python -m pytest shop/test_shop_db.py  (uses a temporary database)"""
import os, sqlite3, tempfile
import pytest

import shop_db


@pytest.fixture()
def db(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    con = sqlite3.connect(path)
    con.executescript(shop_db.SCHEMA)
    con.execute("INSERT INTO products VALUES ('1', 'Daraz', 'Lux Body Wash', 'body wash')")
    con.execute("INSERT INTO reviews (product_id, review_text, language, written_at, source) "
                "VALUES ('1', 'old one', 'english', '2021-01-01', 'dataset')")
    con.commit(); con.close()
    monkeypatch.setattr(shop_db, "DB_PATH", path)
    return path


def test_new_review_comes_first(db):
    shop_db.add_review("1", "  my new review  ", 7.5, "english")
    rows, total = shop_db.reviews("1")
    assert total == 2 and rows[0]["review_text"] == "my new review" and rows[0]["source"] == "coach"
    assert shop_db.product("1")["n"] == 2
    assert shop_db.reviews("1", "bangla") == ([], 0)


def test_bad_input(db):
    with pytest.raises(ValueError):
        shop_db.add_review("1", "  ", 5, "english")
    with pytest.raises(ValueError):
        shop_db.add_review("99", "text", 5, "english")
    assert shop_db.product("99") is None and shop_db.product("") is None


def test_missing_database(monkeypatch):
    monkeypatch.setattr(shop_db, "DB_PATH", "/nonexistent/x.db")
    with pytest.raises(FileNotFoundError):
        shop_db.product("1")

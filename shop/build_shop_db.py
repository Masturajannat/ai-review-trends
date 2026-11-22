"""Make shop.db: the 20 most reviewed products of the dataset and all their reviews.

    cd shop
    python build_shop_db.py

Running it again starts from scratch, so reviews added through Review Coach are removed.
The name and type of each product are written by hand below: the dataset has only a messy name
(some are web-address slugs), and the type is what lets Review Coach notice a review that is
about a different kind of product.
"""
import os, sqlite3, sys
import pandas as pd

import shop_db

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(os.path.dirname(HERE), "combined_reviews.csv")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "review_coach"))
from evaluator import detect_language  # noqa: E402   (to tell English, Bangla and Banglish apart)

# product_id: (name shown in the shop, what kind of product it is)
PRODUCTS = {
    159660913: ("5 Layer KN95 Protective Face Mask with Nose Clip, White (10 pcs)", "disposable face mask"),
    131896608: ("Sepnil Disinfectant Spray 300 ml", "disinfectant spray"),
    106010859: ("Vim Liquid Dishwash 200 ml", "dishwashing liquid"),
    563240477: ("Hoco EQ34 Plus Rima True Wireless Earbuds (ANC + ENC)", "wireless earbuds"),
    183379291: ("Jeans Prayer Mat (Jaynamaz)", "prayer mat"),
    1914756:   ("Lux Body Wash, Black Orchid Scent with Juniper Oil", "body wash"),
    170978:    ("মা, মা, মা এবং বাবা (পেপারব্যাক)", "book (paperback)"),
    106012818: ("Surf Excel Washing Powder 500 g", "washing powder"),
    816517:    ("Surf Excel Synthetic Laundry Detergent Powder 1 kg", "laundry detergent powder"),
    199137074: ("M19 TWS Bluetooth Earbuds with Digital Display", "wireless earbuds"),
    95331:     ("The Ordinary Niacinamide 10% + Zinc 1%", "face serum"),
    167332307: ("Junerose Jr-I4S In-Ear Earphones", "wired earphones"),
    91654:     ("Simple Kind to Skin Hydrating Light Moisturiser 125 g", "face moisturiser"),
    93281:     ("Vaseline Lip Therapy, Rosy Lips", "lip balm"),
    149930244: ("Germnil Hand Sanitizer 500 ml", "hand sanitizer"),
    816876:    ("Lizol Disinfectant Floor & Surface Cleaner 500 ml, Floral", "floor cleaner"),
    243494:    ("Missha All Around Safe Block Soft Finish Sun Milk SPF50+ PA+++", "sunscreen"),
    101536344: ("Rin Advanced Detergent Powder 500 g", "detergent powder"),
    188894:    ("Skin Cafe 100% Natural Rose Water Face & Body Mist", "face and body mist"),
    6773:      ("যদ্যপি আমার গুরু (হার্ডকভার)", "book (hardcover)"),
}


def main():
    d = pd.read_csv(CSV)
    d = d[d["product_id"].isin(PRODUCTS)].copy()
    d["review_text"] = d["review_text"].fillna("").astype(str).str.replace(r"(?i)\s*read more\s*$", "", regex=True).str.strip()
    d = d[d["review_text"] != ""]
    d["written_at"] = pd.to_datetime(d["review_date"], format="%d %b %Y", errors="coerce").dt.strftime("%Y-%m-%d")
    missing = set(PRODUCTS) - set(d["product_id"])
    if missing:
        raise SystemExit(f"No reviews found for products {sorted(missing)}")

    if os.path.exists(shop_db.DB_PATH):
        os.remove(shop_db.DB_PATH)
    con = sqlite3.connect(shop_db.DB_PATH)
    con.executescript(shop_db.SCHEMA)
    platform = d.groupby("product_id")["platform"].first()
    for pid, (name, kind) in PRODUCTS.items():
        con.execute("INSERT INTO products VALUES (?, ?, ?, ?)", (str(pid), platform[pid], name, kind))
    for r in d.itertuples():
        con.execute("INSERT INTO reviews (product_id, review_text, language, score, written_at, source) "
                    "VALUES (?, ?, ?, NULL, ?, 'dataset')",
                    (str(r.product_id), r.review_text, detect_language(r.review_text),
                     None if pd.isna(r.written_at) else r.written_at))
    con.commit()
    print(f"{shop_db.DB_PATH}: {len(PRODUCTS)} products, {len(d)} reviews")


if __name__ == "__main__":
    main()

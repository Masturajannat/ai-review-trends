"""Daraz review scraper - 14 chosen products.
Resumes if stopped, saves after every product,
skips the star filters when filter 0 already returned everything.
Scrapes ALL reviews of these products (no early stop).
"""
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

PRODUCT_URLS = [
    "https://www.daraz.com.bd/products/sepnil-disinfectant-spray-300ml-i131896608-s1052464687.html",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=159660913&skuId=1659654057",
    "https://www.daraz.com.bd/products/surf-excel-washing-powder-500g-i106012818-s1020970212.html",
    "https://www.daraz.com.bd/products/surf-excel-synthetic-laundry-detergent-powder-1kg-i816517-s3435537.html",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=106010859&skuId=1020960380",
    "https://www.daraz.com.bd/products/germnil-500-ml-i149930244-s1076284881.html",
    "https://www.daraz.com.bd/products/jeans-prayer-mat-jaynamaz-for-muslim-i183379291-s1127632484.html",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=816876&skuId=3436358",
    "https://www.daraz.com.bd/products/savlon-handwash-lavender-herbal-1000ml-50ml-refill-i129756950-s1049554201.html",
    "https://www.daraz.com.bd/products/savlon-handwash-ocean-fresh-liquid-hand-soap-refill-1l-refreshing-fragrance-to-uplift-mood-i131748837-s1052258218.html",
    "https://www.daraz.com.bd/products/lizol-disinfectant-floor-surface-cleaner-5l-citrus-super-saver-pack-kills-999-germs-i136878920-s1059126768.html",
    "https://www.daraz.com.bd/products/rin-advanced-detergent-powder-500g-i101536344-s1015538389.html",
    "https://www.daraz.com.bd/products/chaka-washing-powder-all-in-1-500-gm-i56532-s430966.html",
    "https://www.daraz.com.bd/products/lifebuoy-handwash-soap-lemon-fresh-pump-200ml-i101532348-s1015524353.html",
]

API_URL = "https://my.daraz.com.bd/pdp/review/getReviewList"
PAGE_SIZE = 10
FILTERS = [0, 1, 2, 3, 4, 5]
SORTS = [0]
MAX_PAGES = 600
DELAY = 1.0
YEARS = {"2019", "2020", "2021"}   # only used for the running count

HERE = Path(__file__).parent
OUTPUT_FILE = HERE / "daraz_reviews(2019-2021).csv"
DONE_FILE = HERE / "done_items(2019-2021).txt"
RAW_DIR = HERE / "raw_daraz"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.daraz.com.bd/",
}
COLUMNS = ["review_id", "platform", "product_id", "product_name",
           "review_text", "review_date", "year", "rating"]


def get_item_id(url):
    q = parse_qs(urlparse(url).query).get("itemId")
    if q:
        return q[0]
    m = re.search(r"-i(\d+)(?:-s\d+)?\.html", url)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot find item id in URL: {url}")


def fetch_page(session, item_id, flt, sort, page):
    params = {"itemId": item_id, "pageSize": PAGE_SIZE,
              "filter": flt, "sort": sort, "pageNo": page}
    for attempt in range(3):
        try:
            r = session.get(API_URL, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"    retry {attempt + 1}/3 (page {page}): {e}")
            time.sleep(2 * (attempt + 1))
    return None


def parse_year(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%d %b %Y").year
    except (ValueError, AttributeError):
        return ""


def scrape_product(session, url):
    item_id = get_item_id(url)
    print(f"\n=== item {item_id} ===")
    reviews = {}              # review_id -> record
    raw_seen = no_text = dup = 0
    api_total = rating_count = None

    for flt in FILTERS:
        for sort in SORTS:
            before = len(reviews)
            for page in range(1, MAX_PAGES + 1):
                data = fetch_page(session, item_id, flt, sort, page)
                if not data or not data.get("success"):
                    print(f"  filter={flt} sort={sort} page={page}: no/failed response")
                    break
                model = data.get("model") or {}
                items = model.get("items") or []
                paging = model.get("paging") or {}
                if api_total is None:
                    api_total = paging.get("totalItems")
                    rating_count = (model.get("ratings") or {}).get("reviewCount")

                RAW_DIR.mkdir(exist_ok=True)
                (RAW_DIR / f"{item_id}_f{flt}_s{sort}_p{page}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

                if not items:
                    break
                for it in items:
                    raw_seen += 1
                    rid = it.get("reviewRateId")
                    text = (it.get("reviewContent") or "").strip()
                    if rid is None or not text:
                        no_text += 1
                        continue
                    rid = str(rid)
                    if rid in reviews:
                        dup += 1
                        continue
                    date = it.get("reviewTime") or ""
                    reviews[rid] = {
                        "review_id": rid,
                        "platform": "Daraz",
                        "product_id": str(it.get("itemId") or item_id),
                        "product_name": it.get("itemTitle") or "",
                        "review_text": text,
                        "review_date": date,
                        "year": parse_year(date),
                        "rating": it.get("rating") or "",
                    }
                total_pages = paging.get("totalPages")
                if total_pages and page >= int(total_pages):
                    break
                time.sleep(DELAY)
            print(f"  filter={flt} sort={sort}: +{len(reviews) - before} new")

        # filter 0 already got everything the API reports, star filters add nothing
        if flt == 0 and str(api_total).isdigit() and raw_seen >= int(api_total):
            print("  filter 0 covered all reviews, skipping star filters")
            break

    print(f"  AUDIT item {item_id}: kept={len(reviews)} | raw items seen={raw_seen} "
          f"| no text={no_text} | duplicates={dup}")
    print(f"        API paging.totalItems={api_total} | ratings.reviewCount={rating_count}")
    return list(reviews.values())


def load_progress():
    rows, done = {}, set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, newline="", encoding="utf-8-sig") as f:
            for rec in csv.DictReader(f):
                rows[(rec["product_id"], rec["review_id"])] = rec
    if DONE_FILE.exists():
        done = set(DONE_FILE.read_text().split())
    return rows, done


def save_rows(rows):
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows.values())


def main():
    rows, done = load_progress()
    print(f"Resuming with {len(rows)} saved reviews, {len(done)} items done")

    with requests.Session() as s:
        s.headers.update(HEADERS)
        for url in PRODUCT_URLS:
            try:
                item_id = get_item_id(url)
            except ValueError as e:
                print("SKIP:", e)
                continue
            if item_id in done:
                print(f"skip item {item_id} (already done)")
                continue

            recs = scrape_product(s, url)
            for rec in recs:
                rows[(rec["product_id"], rec["review_id"])] = rec
            save_rows(rows)
            with open(DONE_FILE, "a") as f:
                f.write(item_id + "\n")

            total = sum(str(r["year"]) in YEARS for r in rows.values())
            print(f"  total reviews saved: {len(rows)} | from 2019-2021: {total}")

    print(f"\nSaved {len(rows)} unique reviews -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

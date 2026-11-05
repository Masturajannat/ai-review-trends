"""Daraz review scraper v2.
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
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=1580880978&skuId=12669918048",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=556717015&skuId=2588874171",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=285440412&skuId=1293404632",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=1580709208&skuId=12669688036",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=394125703&skuId=1962290071",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=1587658117&skuId=12694746434",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=1581034348&skuId=12670431575",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=199137074&skuId=1146541571",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=563240477&skuId=2600846263",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=291140755&skuId=2567228510",
    "https://www.daraz.com.bd/products/junerose-jr-i4s-in-ear-earphones-with-box-by-mb-telicom-headphone-i167332307.html",
    "https://www.daraz.com.bd/products/fashion-mini-backpacks-sequin-girls-school-bag-leather-travel-backpacks-sports-daypacks-handbags252811cm-i113146885.html",
    "https://www.daraz.com.bd/products/dc-5v-12v-24v-30v-056-lcd-digital-voltage-meter-voltmeter-battery-capacity-tester-detector-for-electronic-mobile-power-bank-i100713245.html",
    "https://www.daraz.com.bd/products/witzman-travel-backpack-outdoor-hiking-camping-daypack-laptop-weekender-backpack-model-2021-blue-and-brown-i100107784-s1013992712.html",
]

API_URL = "https://my.daraz.com.bd/pdp/review/getReviewList"
PAGE_SIZE = 10
FILTERS = [0, 1, 2, 3, 4, 5]
SORTS = [0]          
MAX_PAGES = 200
DELAY = 1.0

HERE = Path(__file__).parent
OUTPUT_FILE = HERE / "daraz_reviews_v2.csv"
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

    print(f"  AUDIT item {item_id}: kept={len(reviews)} | raw items seen={raw_seen} "
          f"| no text={no_text} | duplicates={dup}")
    print(f"        API paging.totalItems={api_total} | ratings.reviewCount={rating_count}")
    return list(reviews.values())


def main():
    rows = {}
    with requests.Session() as s:
        s.headers.update(HEADERS)
        for url in PRODUCT_URLS:
            try:
                for rec in scrape_product(s, url):
                    rows[(rec["product_id"], rec["review_id"])] = rec
            except ValueError as e:
                print("SKIP:", e)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows.values())
    print(f"\nSaved {len(rows)} unique reviews -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

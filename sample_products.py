"""Samples a few pages of each product and estimates how many reviews
from 2019-2021 are LONG ENOUGH to be useful.

Usage (same folder as your scraper):
    python sample_products.py daraz_scraper_v3.py

Change MIN_WORDS below to your minimum review length.
"""
import csv
import importlib.util
import sys
import time

import requests

MIN_WORDS = 10        # <-- change to the minimum length you would keep
SAMPLE_PAGES = 5      # 5 pages = up to 50 reviews per product
YEARS = {2019, 2020, 2021}


def load_scraper(path):
    spec = importlib.util.spec_from_file_location("scraper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if len(sys.argv) < 2:
        print("Usage: python sample_products.py <your_scraper_file.py>")
        return
    sc = load_scraper(sys.argv[1])

    results = []
    with requests.Session() as s:
        s.headers.update(sc.HEADERS)
        for url in sc.PRODUCT_URLS:
            try:
                item_id = sc.get_item_id(url)
            except ValueError:
                continue

            seen = in_range = good = total = 0
            for page in range(1, SAMPLE_PAGES + 1):
                data = sc.fetch_page(s, item_id, 0, 0, page)
                if not data or not data.get("success"):
                    break
                model = data.get("model") or {}
                paging = model.get("paging") or {}
                total = int(paging.get("totalItems") or total or 0)
                items = model.get("items") or []
                if not items:
                    break
                for it in items:
                    seen += 1
                    text = (it.get("reviewContent") or "").strip()
                    year = sc.parse_year(it.get("reviewTime") or "")
                    if year in YEARS:
                        in_range += 1
                        if len(text.split()) >= MIN_WORDS:
                            good += 1
                if page >= int(paging.get("totalPages") or 1):
                    break
                time.sleep(1.0)

            share_range = in_range / seen if seen else 0
            share_good = good / seen if seen else 0
            est_good = round(total * share_good)
            results.append((item_id, total, seen, share_range, share_good, est_good))
            print(f"item {item_id}: total={total} sampled={seen} "
                  f"2019-21={share_range:.0%} usable={share_good:.0%} "
                  f"-> est. usable reviews ~{est_good}")

    results.sort(key=lambda r: r[5], reverse=True)

    out = sc.HERE / "product_sample_ranking.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "total_reviews", "sampled", "share_2019_2021",
                    "share_usable", "est_usable_reviews"])
        w.writerows(results)

    print("\n" + "=" * 50)
    print(f"MIN_WORDS = {MIN_WORDS}")
    print("Top 15 products by estimated usable 2019-2021 reviews:")
    running = 0
    for item_id, total, seen, sr, sg, est in results[:15]:
        running += est
        print(f"  item {item_id}: ~{est}  (running total ~{running})")
    print(f"\nFull ranking saved to {out}")
    print("=" * 50)


if __name__ == "__main__":
    main()

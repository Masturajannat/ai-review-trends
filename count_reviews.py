"""Counts how many reviews each product has (1 request per product)
and estimates how long the full scrape would take.

Usage: put this file in the same folder as your scraper, then run:
    python count_reviews.py daraz_scraper_v3.py
(replace the name with whatever your scraper file is called)
"""
import importlib.util
import sys
import time

import requests


def load_scraper(path):
    spec = importlib.util.spec_from_file_location("scraper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # safe: main() only runs under __main__
    return mod


def main():
    if len(sys.argv) < 2:
        print("Usage: python count_reviews.py daraz_scraper_v2.py")
        return
    sc = load_scraper(sys.argv[1])

    grand_total = 0
    rows = []
    with requests.Session() as s:
        s.headers.update(sc.HEADERS)
        for url in sc.PRODUCT_URLS:
            try:
                item_id = sc.get_item_id(url)
            except ValueError as e:
                print("SKIP:", e)
                continue

            data = sc.fetch_page(s, item_id, 0, 0, 1)
            total = 0
            if data and data.get("success"):
                paging = (data.get("model") or {}).get("paging") or {}
                total = int(paging.get("totalItems") or 0)
            rows.append((item_id, total))
            grand_total += total
            print(f"item {item_id}: {total} reviews")
            time.sleep(1.0)

    pages = sum((t + sc.PAGE_SIZE - 1) // sc.PAGE_SIZE for _, t in rows)
    secs = pages * 1.5  # ~1s delay + ~0.5s request time
    print("\n" + "=" * 40)
    print(f"Products checked : {len(rows)}")
    print(f"TOTAL REVIEWS    : {grand_total}")
    print(f"Pages to download: {pages}")
    print(f"Estimated time   : about {secs / 60:.0f} minutes ({secs / 3600:.1f} hours)")
    print("=" * 40)

    rows.sort(key=lambda r: r[1], reverse=True)
    print("\nBiggest 10 products:")
    for item_id, t in rows[:10]:
        print(f"  item {item_id}: {t}")


if __name__ == "__main__":
    main()

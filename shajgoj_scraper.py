"""Shajgoj review scraper.
"""
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

PRODUCT_URLS = [
    "https://shop.shajgoj.com/product/ribana-castor-oil-2",
    "https://shop.shajgoj.com/product/the-ordinary-niacinamide-10-zinc1",
    "https://shop.shajgoj.com/product/skin-cafe-jojoba-oil-cold-pressed%3Fsrsltid%3DAfmBOor8y3W_sf64UQms3O4JIro7dWOyMdUuc5IHbZkwiNKS_47JQrvc?",
    "https://shop.shajgoj.com/product/lilac-advanced-brightening-face-wash-dry-and-sensitive-skin?add-to-cart=96785&",
    "https://shop.shajgoj.com/product/clariss-face-wash-milk",
    "https://shop.shajgoj.com/product/jigott-natural-tomato-moisture-soothing-gel",
    "https://shop.shajgoj.com/product/neogen-surmedic-azulene-mild-5-5-uv-protect-sun",
    "https://shop.shajgoj.com/product/maybelline-fit-me-matte-poreless-foundation-natural-beige-220",
    "https://shop.shajgoj.com/product/the-body-shop-black-musk-fragrance-mist",
    "https://shop.shajgoj.com/product/wow-anti-aging-night-cream",
    "https://shop.shajgoj.com/product/meena-herbal-uptan-face-pack",
]
MANUAL_IDS = {
}

API = "https://bk.shajgoj.com/api/get-reviews/{pid}"
DELAY = 0.7
HERE = Path(__file__).parent
ID_CACHE = HERE / "shajgoj_ids.json"
OUTPUT_FILE = HERE / "shajgoj_reviews.csv"
COLUMNS = ["review_id", "platform", "product_id", "product_name",
           "review_text", "review_date", "year", "rating"]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}


def slug_of(url):
    """'.../product/slug%3Fsrsltid%3D...?x=1' -> 'slug'"""
    path = urlparse(url).path
    last = path.rstrip("/").split("/")[-1]
    return re.split(r"%3[fF]|\?", last)[0]


def clean_url(url):
    return f"https://shop.shajgoj.com/product/{slug_of(url)}"


def resolve_ids(urls):
    """slug -> internal id, via the page's own get-reviews request."""
    ids = json.loads(ID_CACHE.read_text()) if ID_CACHE.exists() else {}
    ids.update({k: v for k, v in MANUAL_IDS.items()})
    todo = [u for u in urls if slug_of(u) not in ids]
    if not todo:
        return ids

    from playwright.sync_api import sync_playwright
    pat = re.compile(r"get-reviews/(\d+)")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for url in todo:
            slug, found = slug_of(url), []
            page = browser.new_page()
            page.on("request", lambda r: found.extend(pat.findall(r.url)))
            try:
                page.goto(clean_url(url), wait_until="networkidle", timeout=60000)
                for label in ("Reviews", "Review"):
                    try:
                        page.get_by_text(label, exact=False).first.click(timeout=2500)
                        break
                    except Exception:
                        pass
                for _ in range(5):
                    if found:
                        break
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(1000)
            except Exception as e:
                print(f"  page error for {slug}: {e}")
            page.close()
            if found:
                ids[slug] = int(found[0])
                print(f"  {slug} -> id {ids[slug]}")
            else:
                print(f"  {slug} -> id NOT FOUND (add to MANUAL_IDS if it has reviews)")
        browser.close()
    ID_CACHE.write_text(json.dumps(ids, indent=1))
    return ids


def to_record(item, pid, slug):
    text = " ".join((item.get("message") or "").split())
    if not text:
        return None
    dt = None
    try:
        dt = datetime.strptime((item.get("created_at") or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass
    return {
        "review_id": str(item["id"]),
        "platform": "Shajgoj",
        "product_id": str(pid),
        "product_name": slug,
        "review_text": text,
        "review_date": dt.strftime("%d %b %Y") if dt else "",
        "year": dt.year if dt else "",
        "rating": item.get("rating") or "",
    }


def scrape(session, pid, slug):
    kept, raw, no_text, dup, total = {}, 0, 0, 0, None
    page = 1
    while True:
        try:
            r = session.get(API.format(pid=pid), params={"page": page}, timeout=30)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  page {page} failed: {e}")
            break
        total = data.get("total", total)
        for item in data.get("data") or []:
            raw += 1
            rec = to_record(item, pid, slug)
            if rec is None:
                no_text += 1
            elif rec["review_id"] in kept:
                dup += 1
            else:
                kept[rec["review_id"]] = rec
        if page >= int(data.get("last_page") or 1):
            break
        page += 1
        time.sleep(DELAY)
    print(f"  AUDIT {slug}: kept={len(kept)} | raw={raw} | no text={no_text} "
          f"| dup={dup} | API total={total}")
    return list(kept.values())


def main():
    print("Resolving product ids...")
    ids = resolve_ids(PRODUCT_URLS)
    rows = {}
    with requests.Session() as s:
        s.headers.update(HEADERS)
        for url in PRODUCT_URLS:
            slug = slug_of(url)
            if slug not in ids:
                print(f"\nSKIP {slug}: no id")
                continue
            print(f"\n=== {slug} (id {ids[slug]}) ===")
            for rec in scrape(s, ids[slug], slug):
                rows[(rec["product_id"], rec["review_id"])] = rec
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows.values())
    print(f"\nSaved {len(rows)} reviews -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

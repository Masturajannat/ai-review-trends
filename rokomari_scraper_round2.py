"""Rokomari review scraper, round 2 (new products).

Collects reviews for the books listed in a URL file and writes them to a NEW csv file, so the original
rokomari_reviews.csv is never overwritten. The page-reading code is shared with rokomari_scraper.py,
so columns and review IDs are identical to the first round; a review collected in both rounds has the
same review_id and is removed as a duplicate when the data are combined.

Usage (from the repository root, virtual environment active):
    python rokomari_scraper_round2.py
    python rokomari_scraper_round2.py --urls rokomari_urls_round2.txt --out rokomari_reviews_round2.csv
    python rokomari_scraper_round2.py --headed          # show the browser window (for checking)

Input : a text file with one Rokomari book URL per line (lines starting with # are ignored)
Output: rokomari_reviews_round2.csv with the columns of rokomari_reviews.csv plus scrape_date and batch.
        Reviewer names are not stored.

The output is saved after every book. If the run stops, start it again: books already in the output
file are skipped (use --redo to collect them again).
"""
import argparse
import csv
import sys
import time
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

import rokomari_scraper as base     # shared parsing: same columns and review IDs as round 1

HERE = Path(__file__).parent
CHATGPT_RELEASE = datetime(2022, 11, 30)
COLUMNS = base.COLUMNS + ["scrape_date", "batch"]


def read_urls(path):
    urls = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    # drop repeated links, keep order
    return list(dict.fromkeys(urls))


def load_csv(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_csv(path, rows):
    tmp = Path(path).with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def review_date(rec):
    try:
        return datetime.strptime(rec["review_date"].strip(), "%b %d, %Y")
    except (ValueError, AttributeError, KeyError):
        return None


def describe(records):
    dates = [d for d in (review_date(r) for r in records) if d]
    pre = sum(d < CHATGPT_RELEASE for d in dates)
    span = f"{min(dates):%Y-%m} to {max(dates):%Y-%m}" if dates else "no dates"
    return f"{len(records)} reviews ({pre} before ChatGPT, {len(dates) - pre} after; {span})"


def scrape_product(page, url, max_clicks, delay):
    """Same steps as rokomari_scraper.scrape_product, with a configurable number of 'Show more' clicks."""
    product_id = base.get_product_id(url)
    page.goto(url, wait_until="networkidle", timeout=60000)
    product_name = base.clean_text(page.locator("h1").first.inner_text(timeout=10000))
    for label in ("Reviews and Ratings", "Reviews", "রিভিউ"):
        try:
            page.get_by_text(label, exact=False).first.scroll_into_view_if_needed(timeout=3000)
            break
        except Exception:
            pass
    clicks, before = 0, ""
    for _ in range(max_clicks):
        current = page.inner_text("body")
        if not base.click_show_more(page):
            break
        time.sleep(delay)
        updated = page.inner_text("body")
        if updated in (current, before):
            break
        before = updated
        clicks += 1
    records = base.extract_reviews_from_page(page, product_id, product_name)
    if clicks >= max_clicks:
        print(f"  note: stopped after {max_clicks} 'Show more' clicks; older reviews may be missing "
              f"(raise --max-clicks)")
    return product_name, records


def main():
    ap = argparse.ArgumentParser(description="Scrape Rokomari reviews into a new csv file.")
    ap.add_argument("--urls", default="rokomari_urls_round2.txt", help="text file with one book URL per line")
    ap.add_argument("--out", default="rokomari_reviews_round2.csv", help="output csv (new file)")
    ap.add_argument("--batch", default="2", help="batch label stored in every row")
    ap.add_argument("--max-clicks", type=int, default=300, help="maximum 'Show more reviews' clicks per book")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds to wait after each click and between books")
    ap.add_argument("--redo", action="store_true", help="collect books again even if already in the output")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    args = ap.parse_args()

    out = HERE / args.out
    if out.resolve() == (HERE / "rokomari_reviews.csv").resolve():
        sys.exit("Refusing to overwrite the round-1 file rokomari_reviews.csv; choose another --out name.")
    urls_file = HERE / args.urls
    if not urls_file.exists():
        sys.exit(f"{urls_file.name} not found. Create it with one Rokomari book URL per line.")
    urls = read_urls(urls_file)
    if not urls:
        sys.exit(f"{urls_file.name} contains no URLs.")

    old_ids = {r["review_id"] for r in load_csv(HERE / "rokomari_reviews.csv")}
    rows = {r["review_id"]: r for r in load_csv(out)}
    done_products = {r["product_id"] for r in rows.values()}
    old_products = {r["product_id"] for r in load_csv(HERE / "rokomari_reviews.csv")}
    today = date.today().isoformat()
    print(f"{len(urls)} books in {urls_file.name}; {len(rows)} reviews already in {out.name}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"))
        for i, url in enumerate(urls, 1):
            try:
                pid = base.get_product_id(url)
            except ValueError as e:
                print(f"[{i}/{len(urls)}] SKIP (bad URL): {url} - {e}")
                continue
            if pid in done_products and not args.redo:
                print(f"[{i}/{len(urls)}] {pid}: already collected, skipped")
                continue
            if pid in old_products:
                print(f"[{i}/{len(urls)}] {pid}: note - this book was already scraped in round 1; "
                      f"reviews already there will be dropped")
            try:
                name, records = scrape_product(page, url, args.max_clicks, args.delay)
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(urls)}] {pid}: FAILED ({str(e)[:120]}); run again later to retry")
                continue
            new = [r for r in records if r["review_id"] not in old_ids]
            for r in new:
                rows[r["review_id"]] = {**r, "scrape_date": today, "batch": args.batch}
            print(f"[{i}/{len(urls)}] {pid} {name[:50]}: {describe(new)}"
                  + (f"; {len(records) - len(new)} already in round 1" if len(new) < len(records) else ""))
            save_csv(out, list(rows.values()))       # save after every book
            time.sleep(args.delay)
        browser.close()

    all_rows = list(rows.values())
    save_csv(out, all_rows)
    print(f"\nSaved {len(all_rows)} reviews -> {out.name}")
    print(f"Total: {describe(all_rows)}")


if __name__ == "__main__":
    main()

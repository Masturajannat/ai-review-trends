"""Rokomari review scraper.

Outputs the same columns as daraz_scraper_v2.py and shajgoj_scraper.py:
review_id, platform, product_id, product_name, review_text, review_date, year, rating
"""
import csv
import hashlib
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


PRODUCT_URLS = [
    "https://www.rokomari.com/book/52951/to-kill-a-mocking-bird",
    "https://www.rokomari.com/book/43691/durbin",
    "https://www.rokomari.com/book/56/misir-ali-samagra-1",
    "https://www.rokomari.com/book/7652/borof-gola-nodi",
    "https://www.rokomari.com/book/80412/deshe-bideshe",
    "https://www.rokomari.com/book/185933/pride-and-prejudice",
    "https://www.rokomari.com/book/84516/a-thousand-splendid-suns",
    "https://www.rokomari.com/book/53062/the-kite-runner",
    "https://www.rokomari.com/book/154278/the-alchemist",
    "https://www.rokomari.com/book/52812/the-old-man-and-the-sea-award-winning-authors-books",
    "https://www.rokomari.com/book/220261/ikigai",
]

MAX_SHOW_MORE_CLICKS = 40
DELAY = 1.0

HERE = Path(__file__).parent
OUTPUT_FILE = HERE / "rokomari_reviews.csv"
COLUMNS = ["review_id", "platform", "product_id", "product_name",
           "review_text", "review_date", "year", "rating"]


def clean_text(text):
    return " ".join((text or "").split())


def get_product_id(url):
    match = re.search(r"/(?:book|product)/(\d+)", urlparse(url).path)
    if match:
        return match.group(1)
    raise ValueError(f"Cannot find product id in URL: {url}")


def parse_year(date_str):
    for fmt in ("%b %d, %Y", "%d %b %Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).year
        except (ValueError, AttributeError):
            pass
    match = re.search(r"(20\d{2}|19\d{2})", date_str or "")
    return int(match.group(1)) if match else ""


def stable_review_id(product_id, date, text):
    raw = f"{product_id}|{date}|{text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def clean_review_block(text):
    text = clean_text(text)
    text = re.sub(r"\bDefault\s+Most Popular\s+Newest\s+Oldest\b", " ", text, flags=re.I)
    text = re.sub(r"\bMost Popular\s+Newest\s+Oldest\b", " ", text, flags=re.I)
    text = re.sub(r"\bDefault\s+Newest\s+Oldest\s+Most Popular\s+Verified Purchase\b", " ", text, flags=re.I)
    text = re.sub(r"\bPlease login to write review\s+Login\b", " ", text, flags=re.I)
    text = re.sub(r"\bReviews and Ratings\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d+(?:\.\d+)?\s+\d+\s+Ratings?\s+and\s+\d+\s+Reviews?\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b", "", text)
    text = re.sub(r"^By\s+.*?,\s*(?:Verified Purchase\s*)?", "", text, flags=re.I)
    text = re.sub(r"^.*?\bBy\s+.*?,\s*(?:Verified Purchase\s*)?", "", text, flags=re.I)
    text = re.sub(r"\bVerified Purchase\b", "", text, flags=re.I)
    text = re.sub(r"\d+\s+of\s+\d+\s+people\s+found\s+this\s+review\s+helpful\.?", "", text, flags=re.I)
    text = re.sub(r"Was this review helpful.*$", "", text, flags=re.I | re.S)
    text = re.sub(r"Helpful\s*\(\d+\).*$", "", text, flags=re.I | re.S)
    text = clean_text(text)
    return text


def is_noise_review(text):
    lowered = clean_text(text).lower()
    if not lowered:
        return True
    noise_values = {
        "not",
        "helpful",
        "default most popular newest oldest",
    }
    if lowered in noise_values:
        return True
    if re.fullmatch(r"\d+\s+of\s+\d+\s+people\s+found\s+this\s+review\s+helpful\.?", lowered):
        return True
    return False


def extract_rating(card):
    text = card.inner_text(timeout=3000)
    rating_match = re.search(r"([1-5](?:\.\d+)?)\s*out of\s*5", text, re.I)
    if rating_match:
        return rating_match.group(1)

    filled = 0
    star_alts = card.locator("img").evaluate_all(
        """imgs => imgs.map(img => [
            img.getAttribute('alt') || '',
            img.getAttribute('src') || '',
            img.className || ''
        ].join(' ').toLowerCase())"""
    )
    for alt in star_alts:
        if "full" in alt or "star-fill" in alt or "rating-star-full" in alt:
            filled += 1
    return filled if 1 <= filled <= 5 else ""


def extract_reviews_from_page(page, product_id, product_name):
    section_text = page.evaluate(
        """
        () => {
            const text = document.body.innerText || '';
            const start = text.search(/Reviews and Ratings/i);
            if (start < 0) return '';
            const rest = text.slice(start);
            const end = rest.search(/Product Q\\/A|Customers Also Bought|Related Products|Recently Viewed/i);
            return end >= 0 ? rest.slice(0, end) : rest;
        }
        """
    )

    candidates = []
    for part in re.split(r"(?=\bBy\s+[^,\n]{2,120},)", section_text):
        part = clean_text(part)
        if re.search(r"\bBy\s+[^,]{2,120},", part):
            candidates.append(part)

    reviews = {}
    for text in candidates:
        if not text or "Reviews and Ratings" in text or "Please login" in text:
            text = re.sub(r"^.*?(?=\bBy\s+[^,]{2,120},)", "", text, flags=re.I | re.S)

        date_match = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b", text)
        review_date = date_match.group(0) if date_match else ""

        cleaned = clean_review_block(text)

        if len(cleaned) < 3 or is_noise_review(cleaned):
            continue

        rid = stable_review_id(product_id, review_date, cleaned)
        reviews[rid] = {
            "review_id": rid,
            "platform": "Rokomari",
            "product_id": product_id,
            "product_name": product_name,
            "review_text": cleaned,
            "review_date": review_date,
            "year": parse_year(review_date),
            "rating": "",
        }

    return list(reviews.values())


def click_show_more(page):
    return page.evaluate(
        """
        () => {
            const matches = Array.from(document.querySelectorAll('button, a, span, div'))
                .filter(el => /Show\\s+more\\s+Review\\(s\\)|Show\\s+more\\s+Reviews/i.test(el.innerText || ''))
                .filter(el => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                });
            const el = matches[matches.length - 1];
            if (!el) return false;
            el.scrollIntoView({block: 'center'});
            el.click();
            return true;
        }
        """
    )


def scrape_product(page, url):
    product_id = get_product_id(url)
    print(f"\n=== item {product_id} ===")

    page.goto(url, wait_until="networkidle", timeout=60000)
    product_name = clean_text(page.locator("h1").first.inner_text(timeout=10000))

    for label in ("Reviews and Ratings", "Reviews", "রিভিউ"):
        try:
            page.get_by_text(label, exact=False).first.scroll_into_view_if_needed(timeout=3000)
            break
        except Exception:
            pass

    before = ""
    for _ in range(MAX_SHOW_MORE_CLICKS):
        current_text = page.inner_text("body")
        if not click_show_more(page):
            break
        updated_text = page.inner_text("body")
        if updated_text == current_text or updated_text == before:
            break
        before = updated_text
        time.sleep(DELAY)

    records = extract_reviews_from_page(page, product_id, product_name)
    print(f"  AUDIT item {product_id}: kept={len(records)}")
    return records


def main():
    rows = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )
        )

        for url in PRODUCT_URLS:
            try:
                for rec in scrape_product(page, url):
                    rows[(rec["product_id"], rec["review_id"])] = rec
            except Exception as e:
                print("SKIP:", url, e)

        browser.close()

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows.values())

    print(f"\nSaved {len(rows)} unique reviews -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

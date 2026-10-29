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
    "https://www.daraz.com.bd/products/smartphone-dslr-and-any-device-online-clear-sound-recording-a-pure-boya-m1-professional-and-official-microphone-null-i142714943-s1687179590.html",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=171742277&skuId=1107778826",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=159660913&skuId=1659654057",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=816876&skuId=3436358",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=211060405&skuId=1160935919",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=816882&skuId=3436380",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=69304&skuId=473272",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=26134&skuId=226851",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=106010859&skuId=1020960380",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=101524360&skuId=1015542326",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=169196984&skuId=1120207165",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=164626608&skuId=1097428718",
    "https://www.daraz.com.bd/products/yes-handwash-liquid-sky-blue-45ltr-i298811645-s1328112158.html",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=167812145&skuId=1101652983",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=2385662&skuId=62428262",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=58853&skuId=436890",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=2457322&skuId=86616923",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=2457319&skuId=86616917",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=183856914&skuId=1128438884",
    "https://www.daraz.com.bd/products/parachute-just-for-baby-baby-oil-200ml-i101182193-s1015168216.html",
    "https://www.daraz.com.bd/products/200-ml-i136874623-s1791864948.html",
    "https://www.daraz.com.bd/wow/gcp/bd/review/product-reviews?itemId=2385651&skuId=62428240",
    "https://www.daraz.com.bd/products/sepnil-disinfectant-spray-300ml-i131896608-s1052464687.html",
    "https://www.daraz.com.bd/products/savlon-liquid-antiseptic-disinfectant-5000ml-5l-for-first-aid-wound-care-home-care-laundry-disinfection-and-personal-hygiene-i2457325-s86616927.html",
    "https://www.daraz.com.bd/products/savlon-liquid-antiseptic-disinfectant-112ml-for-first-aid-wound-care-home-care-and-personal-hygiene-i137904227-s1060620715.html",
    "https://www.daraz.com.bd/products/savlon-handwash-ocean-fresh-liquid-hand-soap-refill-pouch-170ml-refreshing-fragrance-to-uplift-mood-i112072210-s1028960197.html",
    "https://www.daraz.com.bd/products/savlon-baby-wipe-for-baby-80-pieces-i2457455-s86617397.html",
    "https://www.daraz.com.bd/products/savlon-handwash-aloe-vera-170ml-refill-pouch-pack-i112064320-s1028954504.html",
    "https://www.daraz.com.bd/products/savlon-handwash-marigold-herbal-500ml-pump-i2457368-s86617002.html",
    "https://www.daraz.com.bd/products/savlon-handwash-lavender-herbal-1000ml-50ml-refill-i129756950-s1049554201.html",
    "https://www.daraz.com.bd/products/savlon-handwash-iris-herbal-1000ml-50ml-extra-refill-i129766211-s1049554172.html",
    "https://www.daraz.com.bd/products/savlon-handwash-ocean-fresh-liquid-hand-soap-refill-1l-refreshing-fragrance-to-uplift-mood-i131748837-s1052258218.html",
    "https://www.daraz.com.bd/products/savlon-handwash-lavender-herbal-500ml-pump-i2457370-s86617004.html",
    "https://www.daraz.com.bd/products/dettol-handwash-aloe-vera-200ml-pump-liquid-soap-with-aloe-vera-extract-i125975542-s1046091284.html",
    "https://www.daraz.com.bd/products/dettol-handwash-skincare-200ml-pump-ph-balanced-liquid-soap-i486779-s1881115.html",
    "https://www.daraz.com.bd/products/dettol-soap-cool-70gm-bathing-bar-soap-with-crispy-menthol-i174274-s986770.html",
    "https://www.daraz.com.bd/products/dettol-antiseptic-disinfectant-liquid-750ml-for-first-aid-medical-personal-hygiene-use-diluted-i486766-s1881064.html",
    "https://www.daraz.com.bd/products/dettol-antiseptic-disinfectant-liquid-500ml-for-first-aid-medical-personal-hygiene-use-diluted-i486791-s1881179.html",
    "https://www.daraz.com.bd/products/lizol-disinfectant-floor-surface-cleaner-5l-floral-super-saver-pack-kills-999-germs-i136888799-s1059124839.html",
    "https://www.daraz.com.bd/products/lizol-disinfectant-floor-surface-cleaner-5l-citrus-super-saver-pack-kills-999-germs-i136878920-s1059126768.html",
    "https://www.daraz.com.bd/products/germnil-hand-sanitizer-50-ml-i150712625-s1077420882.html",
    "https://www.daraz.com.bd/products/germnil-500-ml-i149930244-s1076284881.html",
    "https://www.daraz.com.bd/products/surf-excel-liquid-top-load-1l-i112846558-s1029910661.html",
    "https://www.daraz.com.bd/products/surf-excel-liquid-top-load-500ml-i112838903-s1029924269.html",
    "https://www.daraz.com.bd/products/surf-excel-washing-powder-500g-i106012818-s1020970212.html",
    "https://www.daraz.com.bd/products/surf-excel-synthetic-laundry-detergent-powder-500g-i272399709-s1246215505.html",
    "https://www.daraz.com.bd/products/surf-excel-synthetic-laundry-detergent-powder-1kg-i816517-s3435537.html",
    "https://www.daraz.com.bd/products/rin-liquid-detergent-800ml-i164380694-s1097112849.html",
    "https://www.daraz.com.bd/products/rin-liquid-detergent-400ml-i164384644-s1097110983.html",
    "https://www.daraz.com.bd/products/rin-advanced-detergent-powder-500g-i101536344-s1015538389.html",
    "https://www.daraz.com.bd/products/rin-advanced-synthetic-laundry-detergent-powder-1kg-surf-white-pouch-free-available-i101532360-s1015524377.html",
    "https://www.daraz.com.bd/products/rin-advanced-synthetic-laundry-detergent-powder-2kg-surf-excel-200-gm-free-i272401166-s1246216205.html",
    "https://www.daraz.com.bd/products/dettol-antibacterial-disinfectant-wet-wipes-single-pack-i2389962-s62447350.html",
    "https://www.daraz.com.bd/products/goodknight-liquid-mosquito-repellant-refill-45ml-i161128162-s1093022216.html",
    "https://www.daraz.com.bd/products/xtreme-mosquito-coil-fiber-coil-low-smoke-coil-i182626721-s1126569191.html",
    "https://www.daraz.com.bd/products/hand-towel-tissue-paper-250-pcs-x-1-ply-i25766-s225742.html",
    "https://www.daraz.com.bd/products/fresh-white-paper-napkin-100-pcs-x-2-ply-2-box-combo-i25779-s225894.html",
    "https://www.daraz.com.bd/products/fresh-facial-white-tissue-100-pcs-x-2-ply-i101092150-s1015082146.html",
    "https://www.daraz.com.bd/products/fresh-toilet-tissue-white-4-pcs-family-value-pack-i101208279-s1015192318.html",
    "https://www.daraz.com.bd/products/fresh-facial-tissue-white-60pcs-x-2-ply-i101092180-s1015076201.html",
    "https://www.daraz.com.bd/products/fresh-facial-tissue-perfumed-120-pcs-x-2-ply-i101098223-s1015074276.html",
    "https://www.daraz.com.bd/products/fresh-facial-tissue-perfumed-100-pcs-x-2-ply-i101088196-s1015086140.html",
    "https://www.daraz.com.bd/products/-i167986193-s1101884675.html",
    "https://www.daraz.com.bd/products/jeans-prayer-mat-jaynamaz-for-muslim-i183379291-s1127632484.html",
    "https://www.daraz.com.bd/products/chaka-washing-powder-all-in-1-500-gm-i56532-s430966.html",
    "https://www.daraz.com.bd/products/colgate-active-salt-toothpaste-190-gm-i103670751-s1018350217.html",
    "https://www.daraz.com.bd/products/colgate-maxfresh-red-gel-toothpaste-150-gm-i112940478-s1030022153.html",
    "https://www.daraz.com.bd/products/colgate-herbal-toothpaste-200-gm-i112056815-s1028964050.html",
    "https://www.daraz.com.bd/products/colgate-visible-white-toothpaste-100-gm-i100155265-s1014027274.html",
    "https://www.daraz.com.bd/products/sensodyne-toothpaste-fresh-mint-150g-i128990378-s1048784897.html",
    "https://www.daraz.com.bd/products/lifebuoy-handwash-soap-lemon-fresh-bottle-1l-i149498138-s1075808434.html",
    "https://www.daraz.com.bd/products/lifebuoy-handwash-soap-total-bottle-1l-i119692629-s1039052776.html",
    "https://www.daraz.com.bd/products/lifebuoy-skin-cleansing-soap-bar-care-150g-i2417591-s62540037.html",
    "https://www.daraz.com.bd/products/lifebuoy-handwash-soap-lemon-fresh-pump-200ml-i101532348-s1015524353.html",
    "https://www.daraz.com.bd/products/lifebuoy-handwash-soap-total-5l-i239795192-s1183190157.html",
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
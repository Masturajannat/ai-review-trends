"""Finds where Shajgoj loads its reviews from.

"""
import json
from playwright.sync_api import sync_playwright

URL = "https://shop.shajgoj.com/product/the-ordinary-niacinamide-10-zinc1"
OUT = "shajgoj_network_log.json"

log = []


def on_response(resp):
    url = resp.url
    ctype = resp.headers.get("content-type", "")
    if "json" not in ctype and "review" not in url.lower():
        return
    try:
        body = resp.text()
    except Exception:
        return
    if "review" in url.lower() or "review" in body.lower() or "rating" in body.lower():
        log.append({
            "url": url,
            "method": resp.request.method,
            "status": resp.status,
            "post_data": resp.request.post_data,
            "body_preview": body[:2500],
        })


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)   
    page = browser.new_page()
    page.on("response", on_response)
    page.goto(URL, wait_until="networkidle")
    for label in ("Reviews", "Review", "Ratings"):
        try:
            page.get_by_text(label, exact=False).first.click(timeout=3000)
            break
        except Exception:
            pass
    for _ in range(8):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(1000)
        
    input("Click 'load more'/'next page' for reviews if it exists, then press Enter...")
    browser.close()

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(log, f, ensure_ascii=False, indent=2)
print(f"Logged {len(log)} review-related responses -> {OUT}")
for r in log:
    print(r["status"], r["method"], r["url"][:140])

import requests
import json

url = "https://my.daraz.com.bd/pdp/review/getReviewList"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

for page_number in (4, 5, 6):
    params = {
        "itemId": "100107784",
        "pageSize": 10,
        "filter": 0,
        "sort": 0,
        "pageNo": page_number,
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    model = data.get("model") or {}
    items = model.get("items") or []

    print(f"\n--- PAGE {page_number} ---")
    print("Success:", data.get("success"))
    print("Items returned:", len(items))
    print("Model keys:", list(model.keys()))

    # Print metadata only, excluding the individual reviews.
    metadata = {
        key: value
        for key, value in model.items()
        if key != "items"
    }
    print(json.dumps(metadata, indent=2, ensure_ascii=False))

    if items:
        print("First review ID:", items[0].get("reviewRateId"))
        print("Last review ID:", items[-1].get("reviewRateId"))
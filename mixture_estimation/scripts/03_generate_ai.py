import os
import time
from pathlib import Path
import pandas as pd
from openai import OpenAI

DATA = Path(__file__).resolve().parent.parent / "data"
MODEL = "gpt-4o-mini"               # change to the model you want to use

# the key is read from the computer (OPENAI_API_KEY), never typed into the code
client = OpenAI()

# prompt A: rewrite the human review
PROMPT_REWRITE = (
    "Rewrite this customer review of a product bought online in Bangladesh. "
    "Keep the same meaning, language and script (Bangla, Banglish or English). "
    "Write it the way ChatGPT would. About {n} words. Output only the review.\n\n"
    "Review: {text}"
)

# prompt B: write a new review from the product details only
PROMPT_NEW = (
    "Write a new customer review for this product bought online in Bangladesh.\n"
    "Product: {product}\nRating: {rating} out of 5\n"
    "Use the same language and script as the sample below, but do not copy it. "
    "About {n} words. Output only the review.\n\n"
    "Sample: {text}"
)

def ask(prompt):
    # try a few times in case the API is busy
    for _ in range(3):
        try:
            r = client.chat.completions.create(
                model=MODEL, messages=[{"role": "user", "content": prompt}])
            return r.choices[0].message.content.strip()
        except Exception as e:
            print("retry:", e)
            time.sleep(5)
    return ""

for half in ["reference", "validation"]:
    human = pd.read_csv(DATA / f"pilot_human_{half}.csv", dtype={"review_id": str})
    rows = []
    for i, r in enumerate(human.itertuples()):
        # alternate the two prompts so half the AI reviews come from each
        kind = "rewrite" if i % 2 == 0 else "new"
        n = max(int(r.word_count), 3)
        if kind == "rewrite":
            prompt = PROMPT_REWRITE.format(n=n, text=r.review_text)
        else:
            prompt = PROMPT_NEW.format(product=r.product_name, rating=r.rating, n=n, text=r.review_text)
        text = ask(prompt)
        rows.append({
            "review_id": r.review_id,          # id of the human review it was made from
            "platform": r.platform,
            "text_source": r.text_source,
            "prompt_type": kind,
            "review_text": text,
            # English reviews need no translation, Bangla ones are filled in later
            "translated_review_en": text if r.text_source == "original_english" else "",
        })
        time.sleep(1)                          # small pause to avoid rate limits
    pd.DataFrame(rows).to_csv(DATA / f"pilot_ai_{half}.csv", index=False)
    print(half, "done:", len(rows))
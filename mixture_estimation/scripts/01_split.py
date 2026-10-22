from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

# read the cleaned file, ids as text so they stay intact
df = pd.read_csv(DATA / "source_reviews_clean.csv", dtype={"review_id": str})

# only pre-2022 reviews, these cannot be ChatGPT text
df = df[df["period"] == "pre_2022"].copy()

# drop repeated reviews (same English text ignoring case and spaces)
df["key"] = df["translated_review_en"].str.lower().str.strip()
df = df.drop_duplicates("key").drop(columns="key")

# keep only the columns we need
df = df[["review_id", "platform", "text_source", "product_name", "rating",
         "review_text", "translated_review_en", "word_count"]]

# shuffle, then number the rows inside each platform + text_source group
df = df.sample(frac=1, random_state=42)
df["n"] = df.groupby(["platform", "text_source"]).cumcount()

# even rows go to reference, odd rows to validation, so both halves have the same mix
ref = df[df["n"] % 2 == 0].drop(columns="n")
val = df[df["n"] % 2 == 1].drop(columns="n")

# no review may be in both halves
assert not set(ref.review_id) & set(val.review_id)

ref.to_csv(DATA / "human_reference.csv", index=False)
val.to_csv(DATA / "human_validation.csv", index=False)

print("reference:", len(ref), "validation:", len(val))
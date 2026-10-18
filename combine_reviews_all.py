import pandas as pd
from pathlib import Path

folder = Path(__file__).parent

files = [
    folder / "daraz_reviews_v2.csv",
    folder / "shajgoj_reviews.csv",
    folder / "rokomari_reviews.csv",
]

frames = []
for path in files:
    if path.exists():
        frames.append(pd.read_csv(path))
    else:
        print(f"SKIP missing file: {path.name}")

df = pd.concat(frames, ignore_index=True)

# Recent Daraz reviews have dates like "4 weeks ago", so we are setting their years to 2026.
df.loc[df["review_date"].astype(str).str.contains("ago", na=False), "year"] = 2026


def get_period(year):
    year = int(float(year)) if pd.notna(year) and str(year).strip() else 0
    if year < 2022:
        return "pre_2022"
    if year == 2022:
        return "2022"
    return "post_2022"


df["period"] = df["year"].apply(get_period)

df.to_csv(folder / "combined_reviews.csv", index=False, encoding="utf-8-sig")
print(df.groupby(["platform", "period"]).size())

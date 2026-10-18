import pandas as pd
from pathlib import Path

folder = Path(__file__).parent

# Load and combine
daraz = pd.read_csv(folder / "daraz_reviews_v2.csv")
shajgoj = pd.read_csv(folder / "shajgoj_reviews.csv")
df = pd.concat([daraz, shajgoj], ignore_index=True)

# Recent Daraz reviews have dates like "4 weeks ago", so we are setting their years to 2026
df.loc[df["review_date"].str.contains("ago", na=False), "year"] = 2026

# Pre / 2022 / post column
def get_period(year):
    if year < 2022:
        return "pre_2022"
    if year == 2022:
        return "2022"
    return "post_2022"

df["period"] = df["year"].apply(get_period)

# Save
df.to_csv(folder / "combined_reviews.csv", index=False, encoding="utf-8-sig")
print(df.groupby(["platform", "period"]).size())
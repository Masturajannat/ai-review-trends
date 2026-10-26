from pathlib import Path
import pandas as pd

# main folder is two levels up from this script (scripts -> mixture_estimation -> main)
MAIN = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)

# read the old cleaned file, ids as text so they stay intact
df = pd.read_csv(MAIN / "combined_reviews_detected_clean.csv", dtype={"review_id": str})

# the estimator does not use the detector, so these columns go
df = df.drop(columns=["roberta_ai_prob", "Ai_flagged", "confidence"])

df.to_csv(DATA / "source_reviews_clean.csv", index=False)
print(len(df), "rows saved")
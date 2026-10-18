from pathlib import Path
import shutil
import pandas as pd

BASE = Path(__file__).resolve().parent
DET = BASE / "combined_reviews_detected.csv"
SRC = BASE / "combined_reviews.csv"
BAK = BASE / "combined_reviews_detected_backup.csv"

det = pd.read_csv(DET, dtype=str, encoding="utf-8-sig", keep_default_na=False)
src = pd.read_csv(SRC, dtype=str, encoding="utf-8-sig", keep_default_na=False)

assert len(det) == len(src), "Row counts differ - stop, do not continue."
assert (det.platform == src.platform).all(), "Platform order differs - stop."
assert (det.product_id == src.product_id).all(), "Product order differs - stop."

bad = det.review_id.str.contains("E+", regex=False)

def close(a, b):
    try:
        return abs(float(a) - float(b)) / float(b) < 1e-4
    except ValueError:
        return False

ok = [close(a, b) for a, b in zip(det.review_id[bad], src.review_id[bad])]
assert all(ok), "Some broken IDs do not match the original rows - stop."

if not BAK.exists():
    shutil.copy(DET, BAK)
det.loc[bad, "review_id"] = src.loc[bad, "review_id"]
det.to_csv(DET, index=False, encoding="utf-8-sig")
print("Fixed", int(bad.sum()), "IDs. Unique IDs now:", det.review_id.nunique(), "of", len(det))
print("Backup of the old file:", BAK.name)
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
PER_HALF = 100   # 100 reference + 100 validation = 200 reviews

def take(df, n):
    # same share from every platform + text_source group, so the mix matches the full half
    frac = n / len(df)
    parts = [g.sample(max(1, round(len(g) * frac)), random_state=42)
             for _, g in df.groupby(["platform", "text_source"])]
    out = pd.concat(parts)
    # rounding can leave us a row or two off, trim to exactly n
    return out.sample(n, random_state=42) if len(out) > n else out

for half in ["reference", "validation"]:
    df = pd.read_csv(DATA / f"human_{half}.csv", dtype={"review_id": str})
    pilot = take(df, PER_HALF)
    pilot.to_csv(DATA / f"pilot_human_{half}.csv", index=False)
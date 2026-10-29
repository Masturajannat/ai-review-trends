"""Combine all scraped review files into combined_reviews.csv.

The files to combine are listed in sources.csv, one row per file:
    file, platform, scrape_date, batch, note
To add a new collection round, add a row for the new file (see INSTRUCTIONS.md, section 4).

Every review keeps the scrape_date and batch of its file. scrape_date is needed to convert relative
Daraz dates ("3 weeks ago"); batch records the collection round, so results can be compared with and
without later rounds. A review that appears in more than one file (same review_id) is kept once, from
the earliest batch.

Run from the repository root:  python combine_reviews_all.py
"""
import sys
from pathlib import Path

import pandas as pd

FOLDER = Path(__file__).parent
COLUMNS = ["review_id", "platform", "product_id", "product_name", "review_text", "review_date", "year",
           "rating", "scrape_date", "batch"]


def main():
    sources = pd.read_csv(FOLDER / "sources.csv", dtype=str)
    frames = []
    for s in sources.itertuples():
        path = FOLDER / s.file
        if not path.exists():
            print(f"SKIP missing file: {s.file}")
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        wrong = df.platform != s.platform
        if wrong.any():
            sys.exit(f"{s.file}: {wrong.sum()} rows are not from {s.platform}; check sources.csv")
        # the file's own scrape_date / batch columns (round-2 scrapers write them) take precedence
        for col in ["scrape_date", "batch"]:
            if col not in df.columns:
                df[col] = getattr(s, col)
            df[col] = df[col].replace("", getattr(s, col))
        frames.append(df[COLUMNS])
        print(f"{s.file}: {len(df)} reviews (batch {s.batch}, scraped {s.scrape_date})")

    df = pd.concat(frames, ignore_index=True)
    df["_batch_order"] = pd.to_numeric(df.batch, errors="coerce")
    df = df.sort_values("_batch_order", kind="stable")
    dup = df.duplicated("review_id")
    if dup.any():
        print(f"Removed {dup.sum()} reviews that appear in more than one file (earliest batch kept)")
    df = df[~dup].drop(columns="_batch_order")
    df.to_csv(FOLDER / "combined_reviews.csv", index=False, encoding="utf-8-sig")
    print(f"\nSaved {len(df)} reviews -> combined_reviews.csv")
    print(df.groupby(["platform", "batch"]).size().to_string())


if __name__ == "__main__":
    main()

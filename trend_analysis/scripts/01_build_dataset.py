"""
Build the original-language review dataset (no translation).

Input : combined_reviews.csv (repository root) - all scraped reviews, original text
Output: trend_analysis/data/reviews_all.csv            every review with cleaning columns and exclusion reason
        trend_analysis/data/reviews_<platform>.csv     reviews kept for analysis, one file per platform
        trend_analysis/results/dataset_counts.csv      kept reviews by platform, language and period
        trend_analysis/results/dataset_counts_halfyear.csv
        trend_analysis/results/exclusions.csv          number of reviews removed, by reason

Steps
  1. Clean the original text: remove emojis, emoticons and other symbols (text_clean).
  2. Count words on the cleaned text (n_words): whitespace tokens containing a letter.
  3. Tag the language: bangla (Bengali script), banglish (Bengali in Latin letters), english,
     mixed (both scripts in one review).
  4. Parse the review date. Daraz shows reviews younger than about a month as "x weeks ago"; these are
     converted using the scrape date of the review's file (scrape_date, from sources.csv) and marked
     date_is_approx.
  5. Assign periods relative to ChatGPT's release on 30 Nov 2022: period = pre_chatgpt | post_chatgpt.
     period_detail splits pre_chatgpt further into pre_2022 and jan_nov_2022 (used for a placebo check).
     Calendar half-years in half_year.
  6. Exclude, in this order (first matching reason is recorded):
       duplicate_review_id, no_text, exact_repeat (same cleaned text on the same platform; the earliest
       is kept), stock_request (restock / availability questions of 15 words or fewer),
       too_short (5 words or fewer).
     keep_10 / keep_25 mark reviews that also pass stricter length cut-offs for sensitivity checks.

Run from the repository root:  python trend_analysis/scripts/01_build_dataset.py
"""
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import textutil as tu  # noqa: E402

ROOT = HERE.parents[1]
IN_FILE = ROOT / "combined_reviews.csv"
DATA = ROOT / "trend_analysis" / "data"
RESULTS = ROOT / "trend_analysis" / "results"

# Relative dates ("x weeks ago") are converted from each review's scrape_date (set per file in
# sources.csv). This is only a fallback for rows without one.
DEFAULT_SCRAPE_DATE = pd.Timestamp("2026-10-16")
CHATGPT_RELEASE = pd.Timestamp("2022-11-30")
MIN_WORDS = 5                     # reviews with MIN_WORDS words or fewer are excluded

STOCK_REQUEST = re.compile(
    r"restock|re-stock|out of stock|back in stock|in stock|stock e |stock a |stok|when will .* (?:come|available)"
    r"|kobe (?:asbe|pabo|ashbe|anben)|anben na|asbe na|স্টক|রিস্টক|কবে (?:আসবে|পাবো|আনবেন)|আনবেন না",
    re.I)
DATE_FORMATS = ["%d %b %Y", "%b %d, %Y", "%d-%b-%y", "%d %B %Y"]
RELATIVE = re.compile(r"(\d+)\s+(hour|day|week|month)s?\s+ago", re.I)


def parse_date(raw, scrape_date):
    """(date, is_approximate)"""
    raw = str(raw).strip()
    m = RELATIVE.search(raw)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"hour": pd.Timedelta(hours=n), "day": pd.Timedelta(days=n),
                 "week": pd.Timedelta(weeks=n), "month": pd.Timedelta(days=30 * n)}[unit]
        base = pd.to_datetime(scrape_date, errors="coerce")
        base = DEFAULT_SCRAPE_DATE if pd.isna(base) else base
        return (base - delta).normalize(), True
    for fmt in DATE_FORMATS:
        try:
            return pd.Timestamp(pd.to_datetime(raw, format=fmt)), False
        except (ValueError, TypeError):
            continue
    return pd.NaT, False


def period_detail_of(date):
    if pd.isna(date):
        return "unknown"
    if date < pd.Timestamp("2022-01-01"):
        return "pre_2022"
    if date < CHATGPT_RELEASE:
        return "jan_nov_2022"
    return "post_chatgpt"


def main():
    df = pd.read_csv(IN_FILE, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df = df.drop(columns=[c for c in ["period", "year"] if c in df.columns])
    for col in ["scrape_date", "batch"]:
        if col not in df.columns:
            df[col] = ""
    df = df.rename(columns={"review_text": "text_original", "review_date": "review_date_raw"})
    df["rating"] = pd.to_numeric(df.rating, errors="coerce")

    # 1-3: text
    df["text_clean"] = df.text_original.map(tu.clean_text)
    df["n_words"] = df.text_clean.map(lambda t: len(tu.words(t)))
    df["language"] = df.text_clean.map(tu.language_of)

    # 4-5: dates and periods
    parsed = [parse_date(r, s) for r, s in zip(df.review_date_raw, df.scrape_date)]
    df["date"] = [d for d, _ in parsed]
    df["date_is_approx"] = [a for _, a in parsed]
    df["year"] = df.date.dt.year.astype("Int64")
    df["half_year"] = df.date.dt.year.astype("Int64").astype(str) + "-H" + \
        ((df.date.dt.month > 6).astype(int) + 1).astype(str)
    df["period_detail"] = df.date.map(period_detail_of)
    df["period"] = df.period_detail.replace({"pre_2022": "pre_chatgpt", "jan_nov_2022": "pre_chatgpt"})

    # 6: exclusions (first matching reason wins)
    df = df.sort_values(["platform", "date"], kind="stable").reset_index(drop=True)
    reason = pd.Series("", index=df.index)
    reason[df.review_id.duplicated()] = "duplicate_review_id"
    reason[(reason == "") & (df.n_words == 0)] = "no_text"
    key = df.platform + "|" + df.text_clean.str.lower()
    reason[(reason == "") & key.duplicated()] = "exact_repeat"
    is_request = df.text_clean.str.contains(STOCK_REQUEST) & (df.n_words <= 15)
    reason[(reason == "") & is_request] = "stock_request"
    reason[(reason == "") & (df.n_words <= MIN_WORDS)] = "too_short"
    df["exclude_reason"] = reason
    df["keep"] = reason == ""
    df["keep_10"] = df.keep & (df.n_words > 10)
    df["keep_25"] = df.keep & (df.n_words > 25)

    cols = ["review_id", "platform", "batch", "scrape_date", "product_id", "product_name", "rating",
            "review_date_raw", "date",
            "date_is_approx", "year", "half_year", "period", "period_detail", "language", "n_words", "keep", "keep_10",
            "keep_25", "exclude_reason", "text_original", "text_clean"]
    df = df[cols]
    df["date"] = df.date.dt.strftime("%Y-%m-%d")
    DATA.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA / "reviews_all.csv", index=False, encoding="utf-8-sig")
    kept = df[df.keep]
    for p, g in kept.groupby("platform"):
        g.to_csv(DATA / f"reviews_{p.lower()}.csv", index=False, encoding="utf-8-sig")

    # summaries
    order = ["pre_2022", "jan_nov_2022", "post_chatgpt"]
    counts = (kept.groupby(["platform", "language", "period_detail"]).size().unstack(fill_value=0)
              .reindex(columns=order, fill_value=0))
    counts.insert(2, "pre_chatgpt", counts.pre_2022 + counts.jan_nov_2022)
    counts["total"] = counts.pre_chatgpt + counts.post_chatgpt
    counts.to_csv(RESULTS / "dataset_counts.csv")
    hy = kept.groupby(["platform", "language", "half_year"]).size().unstack(fill_value=0)
    hy.to_csv(RESULTS / "dataset_counts_halfyear.csv")
    exc = df.exclude_reason.replace("", "kept").value_counts().rename_axis("reason").reset_index(name="reviews")
    exc.to_csv(RESULTS / "exclusions.csv", index=False)

    print(f"Reviews read: {len(df)}   kept: {len(kept)}")
    print(exc.to_string(index=False))
    unparsed = df.date.isna().sum()
    if unparsed:
        print(f"WARNING: {unparsed} dates could not be read: {df[df.date.isna()].review_date_raw.unique()[:5]}")
    print(f"Approximate (relative) dates among kept reviews: {kept.date_is_approx.sum()}")
    print("\nKept reviews by platform and collection batch")
    print(kept.groupby(["platform", "batch"]).size().to_string())
    print("\nKept reviews by platform, language and period")
    print(counts.to_string())
    print(f"\nSaved to {DATA} and {RESULTS}")


if __name__ == "__main__":
    main()

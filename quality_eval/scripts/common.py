"""Shared helpers: paths, sampling."""
import glob, os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP_COLS = ["review_id", "platform", "language", "n_words", "product_name", "text_original"]

def folder(name):
    # "pilot" or "main"
    p = os.path.join(ROOT, name)
    if not os.path.isdir(p):
        raise SystemExit("no such folder: " + p)
    return p

def find_source(path=None):
    """Use --source if given, else look for reviews_all.csv near this folder."""
    if path:
        if not os.path.exists(path):
            raise SystemExit("source file not found: " + path)
        return path
    tail = os.path.join("trend_analysis", "data", "reviews_all.csv")
    parent = os.path.dirname(ROOT)
    found = glob.glob(os.path.join(ROOT, "reviews_all.csv"))
    for base in (parent, os.path.dirname(parent)):
        found += glob.glob(os.path.join(base, "ai-review-trends*", tail))
        found += glob.glob(os.path.join(base, tail))
    if not found:
        raise SystemExit("could not find reviews_all.csv near this folder.\n"
                         "Put it in the quality_eval folder, or pass --source <path>")
    print("using source:", found[0])
    return found[0]

def load_source(path=None):
    d = pd.read_csv(find_source(path))
    # keep only reviews the earlier pipeline kept (6+ words, no repeats)
    d = d[d["keep"] == True]
    d = d[d["language"].isin(["english", "bangla", "banglish"])].copy()
    d = d.dropna(subset=["text_original", "product_name"])
    return d

def stratified_sample(d, n, seed):
    """Equal share per length bucket, spread over language and platform."""
    d = d.copy()
    d["_bucket"] = pd.cut(d["n_words"], [5, 9, 19, 49, 10**6],
                          labels=["6-9", "10-19", "20-49", "50+"])
    per_bucket = n // d["_bucket"].nunique()
    parts = []
    for _, g in d.groupby("_bucket", observed=True):
        g = g.assign(_cell=g["language"] + "|" + g["platform"])
        per_cell = max(1, per_bucket // g["_cell"].nunique())
        for _, c in g.groupby("_cell"):
            parts.append(c.sample(min(len(c), per_cell), random_state=seed))
    s = pd.concat(parts)
    # top up (or trim) to exactly n
    if len(s) < n:
        rest = d[~d["review_id"].isin(s["review_id"])]
        s = pd.concat([s, rest.sample(n - len(s), random_state=seed)])
    s = s.sample(n=min(n, len(s)), random_state=seed)
    return s[KEEP_COLS].sample(frac=1, random_state=seed).reset_index(drop=True)

def describe(s):
    print(len(s), "reviews")
    print(s["language"].value_counts().to_string())
    print(s["platform"].value_counts().to_string())
    print(pd.cut(s["n_words"], [5, 9, 19, 49, 10**6],
                 labels=["6-9", "10-19", "20-49", "50+"]).value_counts().sort_index().to_string())

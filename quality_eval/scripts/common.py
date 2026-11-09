"""Shared helpers: paths, sampling."""
import json
import glob, os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP_COLS = ["review_id", "platform", "language", "n_words", "product_name", "text_original"]

# sample file in <folder>/data for each stage
SAMPLE_FILES = {"pilot": "pilot_sample.csv", "main": "main_sample.csv", "full": "full_sample.csv"}
FOLDERS = list(SAMPLE_FILES)

# criteria a review can be told to improve (the four points of A GOOD REVIEW in the prompt)
CRITERIA = ["specific", "personal", "reasoned", "relevant"]
FEEDBACK_COLS = ["weak_criteria", "how_to_improve"]

# yes/no checks asked after the score (prompt_v2_checks), grouped under the four criteria.
# They describe the review; they do not add up to the score.
CHECK_GROUPS = {
    "specific": ["product_detail", "service_detail", "depth"],
    "personal": ["own_use", "usage_context", "outcome"],
    "reasoned": ["gives_reason", "balance", "comparison_or_audience"],
    "relevant": ["on_topic"],
}
CHECKS = [c for g in CHECK_GROUPS.values() for c in g]

# what each score level means (the SCORING scale of the prompt), used to explain a score
LEVELS = {
    1: "empty, meaningless, spam, or off-topic",
    2: "almost nothing a buyer could use",
    3: "generic praise or complaint, no detail",
    4: "a hint of information, but no concrete detail",
    5: "one specific detail, with little explanation",
    6: "specific detail about the product or the buying experience, with limited context",
    7: "specific detail backed by the reviewer's own use or purchase",
    8: "several useful details, or real depth on one point",
    9: "detailed, personal and reasoned, strongly useful to a buyer",
    10: "exceptionally informative, thorough and balanced",
}


class LLM:
    """One model behind one call: Gemini (default) or an OpenAI model such as gpt-6-luna.

    Gemini models use GEMINI_API_KEY, models whose name starts with "gpt-" use OPENAI_API_KEY.
    Both are asked for JSON at temperature 0 (if a model does not accept a temperature, it is
    asked without one)."""

    def __init__(self, model):
        self.model = model
        self.openai = model.startswith("gpt-")
        if self.openai:
            from openai import OpenAI          # pip install openai
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            self.temperature = True
        else:
            from google import genai
            self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def __call__(self, prompt):
        if not self.openai:
            r = self.client.models.generate_content(
                model=self.model, contents=prompt,
                config={"temperature": 0, "response_mime_type": "application/json"})
            return r.text
        kw = dict(model=self.model, messages=[{"role": "user", "content": prompt}],
                  response_format={"type": "json_object"})
        if self.temperature:
            try:
                return self.client.chat.completions.create(temperature=0, **kw).choices[0].message.content
            except Exception as e:
                if "temperature" not in str(e).lower():
                    raise
                self.temperature = False
                print("  (this model does not take a temperature; asking without one)")
        return self.client.chat.completions.create(**kw).choices[0].message.content


def parse_checks(j):
    """The ten 0/1 checks as {"check_<name>": 0 or 1}; raises if any is missing or not 0/1."""
    c = j.get("checks")
    if not isinstance(c, dict):
        raise ValueError("checks missing")
    c = {str(k).strip().lower(): v for k, v in c.items()}
    out = {}
    for name in CHECKS:
        v = c.get(name)
        if isinstance(v, bool):
            v = int(v)
        if str(v).strip() not in ("0", "1"):
            raise ValueError(f"check {name} is not 0 or 1: {v!r}")
        out["check_" + name] = int(str(v).strip())
    return out


def parse_feedback(j):
    """weak_criteria as 'specific|personal', how_to_improve as a JSON object; unknown criteria dropped."""
    weak = [str(c).strip().lower() for c in (j.get("weak_criteria") or [])]
    weak = [c for c in CRITERIA if c in weak]
    tips = j.get("how_to_improve") or {}
    if not isinstance(tips, dict):
        raise ValueError("how_to_improve is not an object")
    tips = {c: str(tips[k]).strip() for k in tips for c in CRITERIA if str(k).strip().lower() == c}
    return "|".join(weak), json.dumps(tips, ensure_ascii=False)


def append_row(path, rec):
    """Append one row; if the file was written before new columns existed, add them first."""
    row = pd.DataFrame([rec])
    if os.path.exists(path):
        old_cols = list(pd.read_csv(path, nrows=0).columns)
        new = [c for c in row.columns if c not in old_cols]
        if new:                                         # widen the existing file once
            old = pd.read_csv(path, dtype=str, keep_default_na=False)
            for c in new:
                old[c] = ""
            old.to_csv(path, index=False, encoding="utf-8-sig")
            old_cols += new
        row = row.reindex(columns=old_cols)
        row.to_csv(path, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        row.to_csv(path, index=False, encoding="utf-8-sig")


def save_table(df, csv_path):
    """Save a results table twice: as CSV and as JSON (same name, .json).

    In the JSON file each review is one object; weak_criteria becomes a list,
    how_to_improve an object, and the check_<name> columns one "checks" object."""
    import json
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    recs = json.loads(df.to_json(orient="records", force_ascii=False))
    for r in recs:
        if "weak_criteria" in r:
            w = r["weak_criteria"]
            r["weak_criteria"] = [c for c in str(w).split("|") if c] if w is not None else None
        cols = [k for k in list(r) if k.startswith("check_")]
        if cols:
            vals = {k[6:]: r.pop(k) for k in cols}
            r["checks"] = None if all(v is None for v in vals.values()) else \
                {k: (int(v) if v is not None else None) for k, v in vals.items()}
        if "how_to_improve" in r and isinstance(r["how_to_improve"], str):
            try:
                r["how_to_improve"] = json.loads(r["how_to_improve"])
            except ValueError:
                pass
    json_path = os.path.splitext(csv_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    return json_path


def read_scores(results_dir):
    """All score files of a stage: scores_raw.csv plus scores_raw_<name>.csv from each teammate."""
    files = sorted(glob.glob(os.path.join(results_dir, "scores_raw*.csv")))
    if not files:
        raise SystemExit("no scores_raw*.csv in " + results_dir)
    return pd.concat([pd.read_csv(f, dtype={"review_id": str}) for f in files], ignore_index=True)

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

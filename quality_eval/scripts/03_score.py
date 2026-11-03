"""Score reviews with Gemini. Only ever appends to scores_raw.csv.

  pip install google-genai pandas
  set GEMINI_API_KEY (environment variable, never commit it)
  python scripts/03_score.py --folder pilot --runs 2

Rerunning does nothing for scores that already exist, so an interrupted
run just carries on. To add a third round, run again with --runs 3.
"""
import argparse, json, os, time
import pandas as pd
from common import ROOT, folder

ap = argparse.ArgumentParser()
ap.add_argument("--folder", required=True, choices=["pilot", "main"])
ap.add_argument("--runs", type=int, default=2)
ap.add_argument("--prompt", default="prompt_v1.txt")
ap.add_argument("--model", default="gemini-3.5-flash-lite")
ap.add_argument("--pause", type=float, default=4.5)   # seconds between calls (free tier)
a = ap.parse_args()

fdir = folder(a.folder)
sample_file = os.path.join(fdir, "data", "pilot_sample.csv" if a.folder == "pilot" else "main_sample.csv")
out_file = os.path.join(fdir, "results", "scores_raw.csv")
template = open(os.path.join(ROOT, "prompts", a.prompt), encoding="utf-8").read()
version = os.path.splitext(a.prompt)[0]

def build(row):
    return (template.replace("{product_name}", str(row["product_name"]))
                    .replace("{review_text}", str(row["text_original"])))

def parse(text):
    j = json.loads(text)
    overall = int(j["overall"])
    if not 1 <= overall <= 10:
        raise ValueError("overall out of range")
    return overall, str(j.get("reason", ""))

def ask(client, prompt):
    # a few retries for rate limits or broken JSON
    for i in range(5):
        try:
            r = client.models.generate_content(
                model=a.model, contents=prompt,
                config={"temperature": 0, "response_mime_type": "application/json"})
            return parse(r.text)
        except Exception as e:
            print("  retry", i + 1, "-", str(e)[:100])
            time.sleep(10 * (i + 1))
    return None

def main():
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    df = pd.read_csv(sample_file)

    done = set()
    exists = os.path.exists(out_file)
    if exists:
        old = pd.read_csv(out_file)
        done = set(zip(old["review_id"], old["run"], old["prompt_version"]))

    for run in range(1, a.runs + 1):
        for i, row in df.iterrows():
            if (row["review_id"], run, version) in done:
                continue
            res = ask(client, build(row))
            if res is None:
                continue          # failed ones get picked up on the next launch
            rec = dict(review_id=row["review_id"], run=run, overall=res[0], reason=res[1],
                       model=a.model, prompt_version=version)
            pd.DataFrame([rec]).to_csv(out_file, mode="a", header=not exists,
                                       index=False, encoding="utf-8-sig")
            exists = True
            print(f"run {run}  {i + 1}/{len(df)}  -> {res[0]}")
            time.sleep(a.pause)

if __name__ == "__main__":
    main()

"""Score reviews with Gemini. Only ever appends to a scores_raw*.csv file.

Teammates can share a large stage: each scores one part with their own key and writes
their own file, so nobody overwrites anyone else's scores:
  python scripts/03_score.py --folder full --runs 1 --prompt prompt_v2.txt --part 2 --of 3 --name Tazrian
Reviews already in ANY scores_raw*.csv of the stage are skipped.

  pip install google-genai pandas
  set GEMINI_API_KEY (environment variable, never commit it)
  python scripts/03_score.py --folder pilot --runs 2

Rerunning does nothing for scores that already exist, so an interrupted
run just carries on. To add a third round, run again with --runs 3.

With --prompt prompt_v2_feedback.txt each answer also says which criteria the review
should improve (weak_criteria) and how (how_to_improve). Its scoring instructions are
word for word those of prompt_v2, so its scores are stored as prompt_v2: reviews already
scored with prompt_v2 are skipped, and old and new scores are summarised together.
"""
import argparse, glob, json, os, time
import pandas as pd
from common import ROOT, folder, FOLDERS, SAMPLE_FILES, parse_feedback, append_row

# prompts whose scoring part is identical to another version: stored under that version
SAME_SCORING = {"prompt_v2_feedback": "prompt_v2"}

ap = argparse.ArgumentParser()
ap.add_argument("--folder", required=True, choices=FOLDERS)
ap.add_argument("--runs", type=int, default=2)
ap.add_argument("--prompt", default="prompt_v2.txt")
ap.add_argument("--model", default="gemini-3.5-flash-lite")
ap.add_argument("--pause", type=float, default=4.5)   # seconds between calls (free tier)
ap.add_argument("--part", type=int, default=1, help="which part of the sample to score (1..--of)")
ap.add_argument("--of", type=int, default=1, help="number of parts the sample is split into")
ap.add_argument("--name", default="", help="your name; scores go to scores_raw_<name>.csv")
ap.add_argument("--limit", type=int, default=0,       # stop after this many new scores (0 = no limit)
                help="score at most this many reviews in this session, e.g. to stay under a daily quota")
ap.add_argument("--stop-after-failures", type=int, default=3,
                help="stop when this many reviews in a row fail (usually the daily quota is used up)")
a = ap.parse_args()

fdir = folder(a.folder)
sample_file = os.path.join(fdir, "data", SAMPLE_FILES[a.folder])
if not 1 <= a.part <= a.of:
    raise SystemExit("--part must be between 1 and --of")
res_dir = os.path.join(fdir, "results")
out_file = os.path.join(res_dir, f"scores_raw_{a.name}.csv" if a.name else "scores_raw.csv")
template = open(os.path.join(ROOT, "prompts", a.prompt), encoding="utf-8").read()
prompt_name = os.path.splitext(a.prompt)[0]
version = SAME_SCORING.get(prompt_name, prompt_name)
with_feedback = '"weak_criteria"' in template

def build(row):
    return (template.replace("{product_name}", str(row["product_name"]))
                    .replace("{review_text}", str(row["text_original"])))

def parse(text):
    j = json.loads(text)
    overall = int(j["overall"])
    if not 1 <= overall <= 10:
        raise ValueError("overall out of range")
    fb = parse_feedback(j) if with_feedback else None
    return overall, str(j.get("reason", "")), fb

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
    df = pd.read_csv(sample_file, dtype={"review_id": str})
    if a.of > 1:
        # part k = every review whose row number is k-1 modulo --of (the sample is shuffled)
        df = df[[i % a.of == a.part - 1 for i in range(len(df))]]
        print(f"part {a.part} of {a.of}: {len(df)} reviews -> {os.path.basename(out_file)}")

    done = set()
    exists = os.path.exists(out_file)
    for f in glob.glob(os.path.join(res_dir, "scores_raw*.csv")):      # everyone's scores
        old = pd.read_csv(f, dtype={"review_id": str})
        done |= set(zip(old["review_id"], old["run"], old["prompt_version"]))

    todo = sum((r, run, version) not in done for run in range(1, a.runs + 1) for r in df["review_id"])
    print(f"{len(df)} reviews x {a.runs} run(s); {todo} scores still to do"
          + (f"; this session stops after {a.limit}" if a.limit else ""))
    new, fails = 0, 0
    for run in range(1, a.runs + 1):
        for i, row in df.iterrows():
            if (row["review_id"], run, version) in done:
                continue
            if a.limit and new >= a.limit:
                print(f"limit of {a.limit} reached; run the same command again to continue")
                return
            res = ask(client, build(row))
            if res is None:
                fails += 1
                if fails >= a.stop_after_failures:
                    print(f"{fails} reviews in a row failed (daily quota used up?). Stopped; "
                          "run the same command again later to continue.")
                    return
                continue          # failed ones get picked up on the next launch
            fails = 0
            new += 1
            rec = dict(review_id=row["review_id"], run=run, overall=res[0], reason=res[1],
                       model=a.model, prompt_version=version)
            if res[2] is not None:
                rec.update(weak_criteria=res[2][0], how_to_improve=res[2][1], prompt_file=a.prompt)
            append_row(out_file, rec)
            fb = f"   improve: {res[2][0] or '-'}" if res[2] is not None else ""
            print(f"run {run}  {i + 1}/{len(df)}  -> {res[0]}{fb}   ({new}/{todo} this session)")
            time.sleep(a.pause)

if __name__ == "__main__":
    main()

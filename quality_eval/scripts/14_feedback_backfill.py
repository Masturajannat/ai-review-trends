"""Step 14 (optional): feedback for reviews scored before feedback was added.

Reviews scored with prompt_v2 (pilot, main and the first part of the full run) have a score
and a reason but no weak_criteria / how_to_improve. This step asks Gemini for the feedback
only: it is shown the review, its existing score and reason, and the same criteria as the
scoring prompt (prompts/feedback_only_v1.txt). Nothing is re-scored.

  set GEMINI_API_KEY (environment variable, never commit it)
  python scripts/14_feedback_backfill.py --name Mastura
  python scripts/14_feedback_backfill.py --stages full --part 2 --of 3 --name Tazrian

Writes <stage>/results/feedback_raw_<name>.csv. Reviews that already have feedback, in any
scores_raw*.csv or feedback_raw*.csv, are skipped, so teammates can share it and an
interrupted run carries on.
"""
import argparse, glob, json, os, time
import pandas as pd
from common import ROOT, folder, SAMPLE_FILES, parse_feedback, append_row

ap = argparse.ArgumentParser()
ap.add_argument("--stages", nargs="+", default=["pilot", "main", "full"], choices=list(SAMPLE_FILES))
ap.add_argument("--name", required=True, help="your name; feedback goes to feedback_raw_<name>.csv")
ap.add_argument("--part", type=int, default=1)
ap.add_argument("--of", type=int, default=1)
ap.add_argument("--model", default="gemini-3.5-flash-lite")
ap.add_argument("--pause", type=float, default=4.5)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--stop-after-failures", type=int, default=3)
a = ap.parse_args()
template = open(os.path.join(ROOT, "prompts", "feedback_only_v1.txt"), encoding="utf-8").read()
ID = {"review_id": str}


def todo_for(stage):
    res = os.path.join(folder(stage), "results")
    files = glob.glob(os.path.join(res, "scores_raw*.csv"))
    if not files:
        return pd.DataFrame(), res
    raw = pd.concat([pd.read_csv(f, dtype=ID) for f in files], ignore_index=True)
    raw = raw[raw["prompt_version"] == "prompt_v2"]
    have = set()
    if "weak_criteria" in raw:
        have |= set(raw.loc[raw["weak_criteria"].notna() | raw["how_to_improve"].notna(), "review_id"])
    for f in glob.glob(os.path.join(res, "feedback_raw*.csv")):
        have |= set(pd.read_csv(f, dtype=ID)["review_id"])
    first = raw.sort_values("run").groupby("review_id").agg(score=("overall", "mean"), reason=("reason", "first"))
    sample = pd.read_csv(os.path.join(folder(stage), "data", SAMPLE_FILES[stage]), dtype=ID)
    t = sample.merge(first.reset_index(), on="review_id")
    t = t[~t["review_id"].isin(have)].sort_values("review_id").reset_index(drop=True)
    if a.of > 1:
        t = t[[i % a.of == a.part - 1 for i in range(len(t))]]
    return t, res


def ask(client, prompt):
    for i in range(5):
        try:
            r = client.models.generate_content(model=a.model, contents=prompt,
                                               config={"temperature": 0, "response_mime_type": "application/json"})
            return parse_feedback(json.loads(r.text))
        except Exception as e:
            print("  retry", i + 1, "-", str(e)[:100])
            time.sleep(10 * (i + 1))
    return None


def main():
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    new = fails = 0
    for stage in a.stages:
        t, res = todo_for(stage)
        print(f"{stage}: {len(t)} reviews need feedback")
        out = os.path.join(res, f"feedback_raw_{a.name}.csv")
        for k, r in enumerate(t.itertuples(), 1):
            if a.limit and new >= a.limit:
                print(f"limit of {a.limit} reached; run the same command again to continue")
                return
            score = f"{r.score:g}"
            prompt = (template.replace("{product_name}", str(r.product_name))
                              .replace("{review_text}", str(r.text_original))
                              .replace("{score}", score).replace("{reason}", str(r.reason)))
            fb = ask(client, prompt)
            if fb is None:
                fails += 1
                if fails >= a.stop_after_failures:
                    print("reviews keep failing (daily quota used up?). Stopped; run again later.")
                    return
                continue
            fails = 0
            new += 1
            append_row(out, dict(review_id=r.review_id, score_used=score, weak_criteria=fb[0],
                                 how_to_improve=fb[1], model=a.model, prompt_file="feedback_only_v1.txt"))
            print(f"{stage} {k}/{len(t)}  score {score}  improve: {fb[0] or '-'}")
            time.sleep(a.pause)


if __name__ == "__main__":
    main()

"""Step 13: check that asking for more output fields does not change the scores.

prompt_v2_checks.txt (and the older prompt_v2_feedback.txt) have the same scoring
instructions as prompt_v2 and only ask for more JSON fields after the score. This step
re-scores 40 main-run reviews once with such a prompt and
compares the new score with the two prompt_v2 scores those reviews already have. If the
scores agree about as well as two prompt_v2 runs agree with each other (within 1 point for
nearly all reviews), the new prompt can score the rest of the data without re-scoring
anything already done.

  set GEMINI_API_KEY (environment variable, never commit it)
  python scripts/13_check_feedback_prompt.py                                   # prompt_v2_checks, 40 calls
  python scripts/13_check_feedback_prompt.py --prompt prompt_v2_feedback.txt   # the older prompt
  python scripts/13_check_feedback_prompt.py --model gemini-3.5-flash          # would another model
                                                    # give the same scores? (own files, _<model>)

Writes main/results/check_<prompt>.csv and check_<prompt>_summary.txt (kept apart from
scores_raw*.csv, so the main-run results do not change); for prompt_v2_feedback the names
are feedback_check.csv and feedback_check_summary.txt, as before.
"""
import argparse, json, os, time
import numpy as np
import pandas as pd
from common import ROOT, folder, parse_feedback, parse_checks, append_row, CHECKS

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=40)
ap.add_argument("--model", default="gemini-3.5-flash-lite")
ap.add_argument("--pause", type=float, default=4.5)
ap.add_argument("--prompt", default="prompt_v2_checks.txt")
a = ap.parse_args()

res = os.path.join(folder("main"), "results")
pname = os.path.splitext(a.prompt)[0]
tag = "feedback_check" if pname == "prompt_v2_feedback" else f"check_{pname}"
DEFAULT_MODEL = "gemini-3.5-flash-lite"      # the model all earlier scores come from
if a.model != DEFAULT_MODEL:                 # checking another model: keep its results apart
    tag += "_" + a.model
out = os.path.join(res, f"{tag}.csv")
summary_file = os.path.join(res, f"{tag}_summary.txt")
template = open(os.path.join(ROOT, "prompts", a.prompt), encoding="utf-8").read()
with_checks = '"checks"' in template
w = pd.read_csv(os.path.join(res, "scores_wide.csv"), dtype={"review_id": str})

# spread over the score range: the same number from each band where possible
w["band"] = pd.cut(w["mean"], [0, 2.5, 4.5, 6.5, 8.5, 10], labels=["1-2", "3-4", "5-6", "7-8", "9-10"])
per = int(np.ceil(a.n / 5))
pick = w.groupby("band", observed=True, group_keys=False).apply(
    lambda g: g.sample(min(len(g), per), random_state=13))
pick = pd.concat([pick, w.drop(pick.index).sample(max(0, a.n - len(pick)), random_state=13)]).head(a.n)


def ask(client, prompt):
    for i in range(5):
        try:
            r = client.models.generate_content(model=a.model, contents=prompt,
                                               config={"temperature": 0, "response_mime_type": "application/json"})
            j = json.loads(r.text)
            overall = int(j["overall"])
            if not 1 <= overall <= 10:
                raise ValueError("overall out of range")
            return overall, str(j.get("reason", "")), parse_feedback(j), (parse_checks(j) if with_checks else {})
        except Exception as e:
            print("  retry", i + 1, "-", str(e)[:100])
            time.sleep(10 * (i + 1))
    return None


def main():
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    done = set(pd.read_csv(out, dtype={"review_id": str})["review_id"]) if os.path.exists(out) else set()
    fails = 0
    for k, r in enumerate(pick.itertuples(), 1):
        if r.review_id in done:
            continue
        prompt = (template.replace("{product_name}", str(r.product_name))
                          .replace("{review_text}", str(r.text_original)))
        res_ = ask(client, prompt)
        if res_ is None:
            fails += 1
            if fails >= 3:
                print("3 reviews in a row failed (quota?). Run again later; done ones are kept.")
                break
            continue
        fails = 0
        append_row(out, dict(review_id=r.review_id, new_score=res_[0], new_reason=res_[1],
                             weak_criteria=res_[2][0], how_to_improve=res_[2][1], model=a.model, **res_[3]))
        ck = f"   checks {sum(res_[3].values())}/10" if res_[3] else ""
        print(f"{k}/{len(pick)}  v2 {r.run1:g}/{r.run2:g}  ->  new {res_[0]}{ck}   improve: {res_[2][0] or '-'}")
        time.sleep(a.pause)
    report()


def report():
    if not os.path.exists(out):
        return
    c = pd.read_csv(out, dtype={"review_id": str}).merge(w, on="review_id")
    d = c["new_score"] - c["mean"]
    same_as_a_run = ((c["new_score"] == c["run1"]) | (c["new_score"] == c["run2"])).mean()
    within1 = (d.abs() <= 1).mean()
    rho = c[["new_score", "mean"]].corr(method="spearman").iloc[0, 1]
    lines = [f"reviews compared: {len(c)}",
             f"new score equals one of the two prompt_v2 scores: {same_as_a_run:.0%}",
             f"within 1 point of the prompt_v2 mean: {within1:.0%}",
             f"mean difference (new minus prompt_v2): {d.mean():+.2f}",
             f"rank correlation: {rho:.2f}",
             "(two prompt_v2 runs: same score 78%, within 1 point 99%, rank correlation 0.96)",
             "",
             f"model: {a.model}" + ("" if a.model == DEFAULT_MODEL else f" (compared with {DEFAULT_MODEL} scores)"),
             "verdict: " + (f"scores unchanged; use {pname} for the remaining reviews"
                            if within1 >= 0.95 and abs(d.mean()) < 0.3 else
                            "scores shifted; check before using the new prompt"),
             ""]
    ccols = [f"check_{n}" for n in CHECKS if f"check_{n}" in c]
    if ccols:
        band = pd.cut(c["new_score"], [0, 4, 6, 8, 10], labels=["1-4", "5-6", "7-8", "9-10"])
        t = c[ccols].groupby(band, observed=True).mean().T
        t.index = [i[6:] for i in t.index]
        lines += ["CHECKS: share of reviews with 1, by new score (should rise with the score)",
                  (t * 100).round().astype(int).astype(str).add("%").to_string(), ""]
    lines += ["EXAMPLES"]
    for r in c.sort_values("mean").iloc[::max(1, len(c) // 6)].itertuples():
        tips = json.loads(r.how_to_improve) if isinstance(r.how_to_improve, str) and r.how_to_improve else {}
        lines.append(f"- score {r.new_score} | {str(r.text_original)[:90]!r}")
        if ccols:
            lines.append("    checks: " + " ".join(f"{n[6:]}={int(getattr(r, n))}" for n in ccols))
        lines += [f"    {k}: {v}" for k, v in tips.items()] or ["    (nothing to improve)"]
    txt = "\n".join(lines)
    open(summary_file, "w", encoding="utf-8").write(txt + "\n")
    print("\n" + txt)


if __name__ == "__main__":
    main()

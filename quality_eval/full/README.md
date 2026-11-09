# Full run: every remaining review

The pilot (100) and main (400) runs tested and validated the evaluator. This stage scores every other
cleaned review (6+ words, no repeats, Bangla / Banglish / English) once, with the frozen `prompt_v2`.

| | Reviews |
|---|---|
| Cleaned reviews in the three languages | 7,322 |
| Already scored in the pilot / main run | 100 / 400 |
| **Full set (this folder)** | **6,822** |

One run per review: the main run showed that two runs agree within 1 point for 99% of reviews, so a
second run adds little. The set is shuffled, so a partly finished run already covers every platform
and language.

## Checks and feedback: why the score, and what to improve

From review 317 on, the run uses `prompt_v2_checks.txt`. Its scoring instructions are word for word
those of `prompt_v2`; only the output has more fields, all written after the score:

```json
{"reason": "...", "overall": 6,
 "checks": {"product_detail": 1, "service_detail": 1, "depth": 1,
            "own_use": 1, "usage_context": 0, "outcome": 0,
            "gives_reason": 0, "balance": 0, "comparison_or_audience": 0,
            "on_topic": 1},
 "weak_criteria": ["personal", "reasoned"],
 "how_to_improve": {"personal": "Mention how long you have used the earbuds and in what situations.",
                    "reasoned": "Say why the sound is good, or compare it with earbuds you used before."}}
```

- `checks`: ten yes/no (1/0) questions about the review, grouped under the four criteria of
  A GOOD REVIEW (specific: product_detail, service_detail, depth; personal: own_use,
  usage_context, outcome; reasoned: gives_reason, balance, comparison_or_audience; relevant:
  on_topic). They describe the review and do not add up to the score. In `scores_raw*.csv`
  they are the columns `check_product_detail` ... `check_on_topic`.
- `weak_criteria` and `how_to_improve`: the criteria to improve and one concrete suggestion each.
- Step 12 also explains each score with the SCORING scale of the prompt, without API calls:
  `level`, `level_meaning` (e.g. "specific detail ... with limited context") and `next_level`
  (what the next score level asks for).

Because the scoring part is unchanged, these scores are stored as `prompt_v2` and summarised
together with the earlier ones; `scripts\13_check_feedback_prompt.py` re-scores 40 main-run
reviews with the new prompt to confirm the scores do not shift. Reviews scored before (pilot,
main, the first 316 here) have no checks; they get rule-based feedback from
`scripts\15_feedback_from_reasons.py`.

## Sharing the run between teammates

Step-by-step instructions for teammates (and their AI assistants): `quality_eval/SCORING_GUIDE.md`.

The free daily quota allows a few hundred reviews per key. To finish faster, each teammate scores one
third with their own key, on their own computer, into their own file:

| Who | Command (from `quality_eval`) | Writes |
|---|---|---|
| Mastura | `python scripts\03_score.py --folder full --runs 1 --prompt prompt_v2_checks.txt --part 1 --of 3 --name Mastura` | `full\results\scores_raw_Mastura.csv` |
| Tazrian | `... --part 2 --of 3 --name Tazrian` | `full\results\scores_raw_Tazrian.csv` |
| Fahima | `... --part 3 --of 3 --name Fahima` | `full\results\scores_raw_Fahima.csv` |

Reviews already in any `scores_raw*.csv` (including the first 316 in `scores_raw.csv`) are skipped.
Commit only your own file; steps 04 and 12 read all the files together.

## How to run (one person)

```powershell
$env:GEMINI_API_KEY = "<key>"                                  # never commit API keys
python scripts\11_make_full_set.py                             # only if full\data\full_sample.csv is missing
python scripts\03_score.py --folder full --runs 1 --prompt prompt_v2_checks.txt
python scripts\04_summarize.py --folder full --version prompt_v2
python scripts\07_make_page.py --folder full                   # optional, large page
python scripts\12_combine_scores.py                            # all_scores.csv + .json: pilot + main + full
```

About 5 seconds per review, so roughly 9-10 hours in total. The free tier's daily quota will usually
stop it earlier: the script stops by itself after 3 reviews in a row fail, and the same command
continues where it stopped (nothing is scored twice). `--limit 1000` scores at most 1,000 reviews in a
session.

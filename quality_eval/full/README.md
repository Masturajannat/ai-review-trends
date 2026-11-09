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

## Feedback: which criteria to improve

From review 317 on, the run uses `prompt_v2_feedback.txt`. Its scoring instructions are word for word
those of `prompt_v2`; only the output has two more fields, written after the score:

```json
{"reason": "...", "overall": 5,
 "weak_criteria": ["specific", "personal"],
 "how_to_improve": {"specific": "Say how many hours the battery lasts with daily use.",
                    "personal": "Mention how long you have used the earbuds and in what situations."}}
```

The criteria are the four points of A GOOD REVIEW in the prompt: specific, personal, reasoned,
relevant. Because the scoring part is unchanged, these scores are stored as `prompt_v2` and
summarised together with the earlier ones; `scripts\13_check_feedback_prompt.py` re-scores 40
main-run reviews with the new prompt to confirm the scores do not shift. Reviews scored before
feedback was added (pilot, main, the first 316 here) get feedback from
`scripts\14_feedback_backfill.py`, which does not re-score them.

## Sharing the run between teammates

Step-by-step instructions for teammates (and their AI assistants): `quality_eval/SCORING_GUIDE.md`.

The free daily quota allows a few hundred reviews per key. To finish faster, each teammate scores one
third with their own key, on their own computer, into their own file:

| Who | Command (from `quality_eval`) | Writes |
|---|---|---|
| Mastura | `python scripts\03_score.py --folder full --runs 1 --prompt prompt_v2_feedback.txt --part 1 --of 3 --name Mastura` | `full\results\scores_raw_Mastura.csv` |
| Tazrian | `... --part 2 --of 3 --name Tazrian` | `full\results\scores_raw_Tazrian.csv` |
| Fahima | `... --part 3 --of 3 --name Fahima` | `full\results\scores_raw_Fahima.csv` |

Reviews already in any `scores_raw*.csv` (including the first 316 in `scores_raw.csv`) are skipped.
Commit only your own file; steps 04 and 12 read all the files together.

## How to run (one person)

```powershell
$env:GEMINI_API_KEY = "<key>"                                  # never commit API keys
python scripts\11_make_full_set.py                             # only if full\data\full_sample.csv is missing
python scripts\03_score.py --folder full --runs 1 --prompt prompt_v2_feedback.txt
python scripts\04_summarize.py --folder full --version prompt_v2
python scripts\07_make_page.py --folder full                   # optional, large page
python scripts\12_combine_scores.py                            # all_scores.csv + .json: pilot + main + full
```

About 5 seconds per review, so roughly 9-10 hours in total. The free tier's daily quota will usually
stop it earlier: the script stops by itself after 3 reviews in a row fail, and the same command
continues where it stopped (nothing is scored twice). `--limit 1000` scores at most 1,000 reviews in a
session.

# Pilot: Gemini review-quality scoring

This folder holds the pilot of the review quality evaluator. The evaluator gives a review a score from
1 to 10 for how useful it would be to a buyer. The first step, set by the course instructor, is to
let an LLM (Gemini) score a sample of reviews and then check whether the reviews it scores higher
(for example 8) are really better than the ones it scores lower (for example 5).

The pilot is a dry run of that step on 100 reviews. It tests whether the prompt works, whether the
scores are stable from one run to the next, and whether the score distribution is sensible, before
the prompt is frozen and used on the 400-review main sample. The pilot reviews are not used in the
main sample or in the final human check, because the prompt may be adjusted after the pilot.

| | Pilot (100 reviews) | Main run (400 reviews) |
|---|---|---|
| Question | Does the prompt work: does it run cleanly, give stable scores and use the scale sensibly? | Does the score reflect quality: is a review scored 8 really better than one scored 5? |
| Checks | Stability between two runs; score distribution; manual read of about 30 scored reviews | Blind human check (pairs and single scores); length and language bias; stability again on a larger sample |
| Prompt | May still change (`prompt_v2.txt`) | Frozen; the final pilot version |
| Folder | `pilot/` | `main/` |
| Scripts | 01, 03, 04 | 02, 03, 04, 05, 06 |
| State | Scored; stability passed; manual read pending | Not started |

The reviews come from `trend_analysis/data/reviews_all.csv` of the `ai-review-trends` project
(Daraz, Rokomari and Shajgoj; Bangla, Banglish and English). Run all commands from the
`quality_eval` folder, one level above this one.

## Design

| Choice | Setting |
|---|---|
| Judge | Gemini `gemini-3.5-flash-lite`, temperature 0, JSON output |
| Input to the judge | Product name and review text only. Star rating, platform, date and language are not sent, so the score reflects the text and not the sentiment |
| Output | `reason` (one sentence), then `overall` (integer 1–10) |
| Prompt | `prompts/prompt_v1.txt`: criteria for good and bad reviews and a 1–10 scale. No worked examples, no list of expected aspects per product type |
| Strictness | Generic praise with no detail should not score above 3 |
| Runs | Two runs of the same prompt on every review, to measure stability |
| Sample | 100 reviews, kept apart from the main sample by saving their IDs |

Decisions made while planning:

- **No examples in the prompt.** Examples can bias a model towards their wording and scores. They
  are added only if the pilot shows a badly used scale.
- **No fixed aspect lists.** The judge works out what matters for the product from its name. A fixed
  list per product type would reward reviews that mention the listed words and would not work on
  other platforms.
- **No sub-scores.** An earlier version also returned specificity, experience, reasoning and
  relevance scores; they were dropped to keep the output simple. The `reason` column is kept for
  diagnosing individual scores.
- **Writer feedback is left for later.** Tips for the review writer are not part of this stage; the
  question here is only whether the score reflects quality.

## The prompt

The judge is told to assess how useful the review would be to a person deciding whether to buy the
product, and not to judge sentiment, spelling, grammar, language or script, or length by itself.

| Good review | Bad review |
|---|---|
| Specific: names concrete parts or features | Only generic adjectives or stock phrases ("nice product", "recommended") |
| Personal: real use, how long, in what situation | Nothing a buyer could check or act on |
| Reasoned: a reason, a pro and a con, or a comparison | Off-topic: question to the seller, delivery-only complaint, spam |
| Relevant: about this product and useful to a buyer | Copied product description or book blurb with no opinion of the reviewer's own |

| Score | Meaning |
|---|---|
| 1–2 | Empty, useless or off-topic |
| 3–4 | Generic praise or complaint, no real detail |
| 5–6 | Some detail or some real use, but thin |
| 7–8 | Clearly specific and personal, useful to a buyer |
| 9–10 | Detailed and balanced, real experience with depth |

## Pilot sample

`data/pilot_sample.csv` has 100 reviews drawn from the reviews the earlier pipeline kept (at least 6
words, no exact repeats), with seed 7. Reviews are spread evenly over four length ranges, and within
each range over language and platform, so that short generic reviews do not dominate.

| Length (words) | Reviews | | Language | Reviews | | Platform | Reviews |
|---|---|---|---|---|---|---|---|
| 6–9 | 24 | | Bangla | 38 | | Daraz | 41 |
| 10–19 | 25 | | English | 35 | | Shajgoj | 33 |
| 20–49 | 25 | | Banglish | 27 | | Rokomari | 26 |
| 50+ | 26 | | | | | | |

Because the sample is balanced by length, long reviews are over-represented compared with the full
dataset (26% here against a much smaller share overall). The score distribution below therefore
describes this sample and not all reviews.

## How to run

```powershell
python -m pip install google-genai pandas matplotlib
$env:GEMINI_API_KEY = "<key>"                          # never commit API keys

python scripts\01_make_pilot_sample.py                  # already done; the sample is in pilot\data
python scripts\03_score.py --folder pilot --runs 2      # about 15 minutes, resumable
python scripts\04_summarize.py --folder pilot           # table, summary and figures
```

Set the key in the same PowerShell window that runs the scoring. `set GEMINI_API_KEY=...` is
Command Prompt syntax and does not work in PowerShell.

Step 01 is only needed to draw the sample again. Running it again overwrites `pilot_sample.csv` and
`pilot_ids.csv`, so do not run it after scoring: the scores in `scores_raw.csv` would no longer
match the sample.

## Scripts

All scripts are in `scripts\` (one level above this folder) and are shared by the pilot and the
main run. They find their own folders, so they can be started from any directory.

| Script | Stage | Purpose |
|---|---|---|
| `common.py` | both | Shared helpers: finds the project folders and `reviews_all.csv`, loads the kept reviews, draws the stratified sample. Not run directly |
| `01_make_pilot_sample.py` | pilot | Draws the 100-review pilot sample and saves its IDs |
| `02_make_main_sample.py` | main | Draws the 400-review main sample without the pilot IDs. Run after the prompt is frozen |
| `03_score.py` | both | Scores every review with Gemini; appends to `scores_raw.csv` |
| `04_summarize.py` | both | Builds the wide table, the stability summary and the figures |
| `05_make_check_sheets.py` | main | Builds the blind sheets for the human check (pairs of high- and middle-scored reviews, and single reviews to score by hand) |
| `06_check_results.py` | main | Compares the human judgments with the Gemini scores |

### `01_make_pilot_sample.py`

```powershell
python scripts\01_make_pilot_sample.py
python scripts\01_make_pilot_sample.py --source "<path>\reviews_all.csv" --n 100 --seed 7
```

Looks for `reviews_all.csv` inside `quality_eval`, then next to it and one level up in an
`ai-review-trends` folder. `--source` overrides this. Writes `pilot\data\pilot_sample.csv` and
`pilot\data\pilot_ids.csv` and prints the counts per length range, language and platform.

### `02_make_main_sample.py`

```powershell
python scripts\02_make_main_sample.py                   # 400 reviews, seed 42
```

Same options as step 01 (`--source`, `--n`, `--seed`). Removes every ID in `pilot\data\pilot_ids.csv`
before sampling, so the main sample and the pilot never overlap. Writes `main\data\main_sample.csv`.

### `03_score.py`

```powershell
python scripts\03_score.py --folder pilot --runs 2
python scripts\03_score.py --folder pilot --runs 3      # adds a third run only
```

| Option | Default | Meaning |
|---|---|---|
| `--folder` | required | `pilot` or `main` |
| `--runs` | 2 | Number of runs wanted. Runs already in the file are skipped |
| `--prompt` | `prompt_v1.txt` | Prompt file in `prompts\`; its name is stored as the prompt version |
| `--model` | `gemini-3.5-flash-lite` | Gemini model name |
| `--pause` | 4.5 | Seconds between calls, to stay under the free-tier rate limit |

Needs the `GEMINI_API_KEY` environment variable. Every score is written as soon as it arrives, so
an interrupted run (Ctrl+C, network failure, daily quota) continues where it stopped when started
again. Failed requests are retried five times and then skipped until the next start. If the prompt
is changed, save it as `prompt_v2.txt` and pass `--prompt prompt_v2.txt`; scores of different
versions are never mixed.

### `04_summarize.py`

```powershell
python scripts\04_summarize.py --folder pilot
python scripts\04_summarize.py --folder pilot --version prompt_v1
```

Reads `scores_raw.csv` and writes the wide table, `stability_summary.txt` and three figures into
`results\`. Without `--version` it uses the latest prompt version in the file.

### `05_make_check_sheets.py` and `06_check_results.py` (main stage)

```powershell
python scripts\05_make_check_sheets.py
python scripts\06_check_results.py
```

Step 05 needs the scored main sample. It writes `pairs_for_raters.csv` and `single_for_raters.csv`
(without scores, for the people doing the check) and `pairs_key.csv` (with scores). Raters fill
`better_AorB` (A or B) in the pairs and `my_score` (1–10) in the single reviews; the filled copies
are saved as `pairs_filled.csv` and `single_filled.csv` in `main\results\`. Step 06 then reports how
often people chose the review that Gemini scored higher (with a 95% interval, also split by whether
the higher-scored review is the longer one) and the rank correlation between the human and Gemini
scores. These two steps are not used for the pilot.

## Files

| Path | Contents |
|---|---|
| `data/pilot_sample.csv` | The 100 pilot reviews: `review_id`, `platform`, `language`, `n_words`, `product_name`, `text_original` |
| `data/pilot_ids.csv` | IDs of the pilot reviews; excluded from the main sample |
| `results/scores_raw.csv` | One row per review and run: `review_id`, `run`, `overall`, `reason`, `model`, `prompt_version`. Only ever appended to |
| `results/scores_wide.csv` | One row per review: `run1`, `run2`, `mean` (the final score), `spread` (largest minus smallest score), `reason_run1`, and the sample columns including the review text. Rebuilt by step 04 |
| `results/stability_summary.txt` | Run counts, stability, score spread, mean score by language and length |
| `results/fig_differences.png` | How many reviews differ by 0, 1, 2 points between the two runs |
| `results/fig_run1_vs_run2.png` | Grid of run 1 against run 2 scores; the diagonal means the same score |
| `results/fig_score_distribution.png` | Number of reviews per score, by language |

## Results

Prompt `prompt_v1`, model `gemini-3.5-flash-lite`, two runs on 100 reviews.

### The run

200 scores were requested and 200 received; no score is missing and no reply failed to parse. Two
requests hit a temporary network error (`getaddrinfo failed`) and succeeded on the first retry.

### Stability

| Measure | Result |
|---|---|
| Same score in both runs | 79% |
| Within 1 point | 99% |
| Differ by 2 or more points | 1% (one review: 6 and 4) |
| Rank correlation, run 1 against run 2 | 0.98 |

The planned target was at least 85–90% of reviews within 1 point. The pilot is well above it. Of the
21 reviews whose scores differed, 20 differ by one point, mostly in the lower and middle part of
the scale (for example 2 and 3, 3 and 4, or 6 and 7).

![Run 1 against run 2](results/fig_run1_vs_run2.png)

![Differences between runs](results/fig_differences.png)

### Score distribution (mean of the two runs, rounded)

| Band | Reviews |
|---|---|
| 1–2 | 30% |
| 3–4 | 35% |
| 5–6 | 16% |
| 7–8 | 17% |
| 9–10 | 2% |

Nine different scores are used and no band holds more than 35% of the reviews, so the scale is not
squeezed into one range. The top of the scale is used rarely: only two reviews reach 10, and none
rounds to 9. There are 13 reviews with a mean of 8 or more and 31 between 4 and 6, which is enough
for the pair test later (Gemini's high-scored against middle-scored reviews).

![Score distribution by language](results/fig_score_distribution.png)

### By language, platform and length

| Language | Reviews | Mean score | | Platform | Reviews | Mean score | | Length (words) | Reviews | Mean score |
|---|---|---|---|---|---|---|---|---|---|---|
| Bangla | 38 | 4.08 | | Daraz | 41 | 4.11 | | 6–9 | 24 | 2.35 |
| Banglish | 27 | 4.24 | | Rokomari | 26 | 3.73 | | 10–19 | 25 | 3.76 |
| English | 35 | 4.30 | | Shajgoj | 33 | 4.68 | | 20–49 | 25 | 3.74 |
| | | | | | | | | 50+ | 26 | 6.77 |

- **Language.** Means differ by 0.2 points between Bangla, Banglish and English. No language
  penalty is visible at this sample size.
- **Length.** Score and word count have a rank correlation of 0.65. Longer reviews have more room
  for detail, so some correlation is expected. Length alone does not decide the score: 4 of the 26
  reviews with 50 or more words scored 4 or below (long thank-you and delivery reviews), while four
  reviews of 22 words or fewer scored 6 or more because they contain concrete detail (for example
  pores getting larger after a month of use, insects found in the product). Whether this holds on
  the main sample is part of the main check.

### What the scores and reasons look like

From reading the scored sheet:

- Questions to the seller, delivery-only reviews and reviews written before the product was used
  are scored 1–2, with reasons that say so ("a question directed to the seller", "talks only about
  delivery").
- Generic praise ("Best product for my skin. It works like magic.") scores 2.
- Long reviews with duration of use, skin type, results and side effects score 8–10.
- The reasons match the criteria in the prompt and name what is missing ("lacks specific details
  about the earbuds' performance").

### Points to check

These are observations from a first read of the sheet, not confirmed problems.

- **Book plot summaries.** Three Rokomari reviews of *The Kite Runner* that mostly retell the plot
  or the history behind it scored 7, 6.5 and 6, although the prompt names copied blurbs as a bad
  review. One of them (161 words) starts
  in the middle of a sentence and may be pasted text; the judge cannot know whether text was copied.
- **Some 7s may be generous.** For example review 14808 (18 words, "Best for dry skin. I like its
  smell…") scored 7 in both runs.
- **Consistent is not correct.** Stable scores show that the prompt gives repeatable answers, not
  that the answers are right. That is tested by the human check on the main sample.

## Limitations

- 100 reviews and two runs give a rough stability estimate (about ±10 points on the percentages).
- Only one model, one prompt and temperature 0 were tested. A re-worded prompt or a second model
  has not been compared.
- The sample is balanced by length, so score shares do not describe the full dataset.
- Gemini's scores have not yet been compared with human judgments. Stability does not show that
  an 8 is better than a 5.
- Only the text and the product name are scored. A review cannot be checked for truth, copied text
  or fake detail.
- The 9–10 band has two reviews, so its behaviour is almost untested.

## Status

| Item | State |
|---|---|
| Pilot scored twice, summary and figures built | Done |
| Stability check | Passed (99% within 1 point) |
| Manual read of about 30 scored reviews (10 lowest, 10 middle, 10 highest) | To do |
| Decision to freeze `prompt_v1` for the main run | Pending the manual read |

## Next steps

1. Read about 30 pilot reviews in `results/scores_wide.csv` and note any score that looks wrong.
   If the scores are acceptable, keep `prompt_v1` unchanged; if a pattern is wrong (for example
   book summaries), write `prompt_v2.txt` and rerun the pilot.
2. Draw the main sample without the pilot reviews: `python scripts\02_make_main_sample.py`.
3. Score the main sample twice: `python scripts\03_score.py --folder main --runs 2` (about one hour
   for 800 calls), then `python scripts\04_summarize.py --folder main`.
4. Build the blind sheets with `python scripts\05_make_check_sheets.py`. At least two people mark the
   better review in each pair and score some single reviews without seeing Gemini's scores.
5. Run `python scripts\06_check_results.py` to test whether higher-scored reviews are better, whether
   the result holds when the higher-scored review is the shorter one, and whether Bangla and
   Banglish reviews are scored fairly.
6. After the evaluator is validated: suggestions to the writer for improving a review, and a check
   that the score rises when a review is improved.

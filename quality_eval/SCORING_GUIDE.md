# Scoring guide for teammates (full run)

This guide is for Tazrian and Fahima, and for any AI assistant helping them. It says what to run,
in which order, and what must not be changed. Read it fully before running anything.

## What this stage does

Every cleaned review that is not in the pilot (100) or main (400) run is scored by Gemini for
usefulness to a buyer, 1 to 10, together with feedback on what the review should improve. The
reviews are in `quality_eval/full/data/full_sample.csv` (6,822 reviews, shuffled). The first 316
were scored by Mastura before feedback was added; they are skipped automatically.

The scores will be used to train our own review-quality model, so the scoring must stay
consistent: same prompt, same model, same settings for every review.

The work is split into three parts, one per person, each with their own Gemini API key:

| Person | Part | Output file (written automatically) |
|---|---|---|
| Mastura | `--part 1 --of 3 --name Mastura` | `quality_eval/full/results/scores_raw_Mastura.csv` |
| Tazrian | `--part 2 --of 3 --name Tazrian` | `quality_eval/full/results/scores_raw_Tazrian.csv` |
| Fahima | `--part 3 --of 3 --name Fahima` | `quality_eval/full/results/scores_raw_Fahima.csv` |

## You stay on your own branch

You do **not** switch to Mastura's branch or merge it. You copy only the files needed for scoring
from `origin/Mastura` into your own branch, score there, and push your own branch. Mastura copies
your score file from your branch at the end.

## Before you start

Start only after Mastura has pushed the 40-review check with the verdict **"scores unchanged"**.
Check it without switching branches (from the repository folder `ai-review-trends`):

```powershell
git fetch origin
git show origin/Mastura:quality_eval/main/results/feedback_check_summary.txt
```

The last lines must say `verdict: scores unchanged`. If they do not, or the file is missing, do not
start. (A first version of the prompt, with a longer instruction for "reason", shifted the scores
and was replaced; its check is kept as `feedback_check_summary_try1.txt`.)

## Setup (once, in the VS Code terminal, PowerShell)

From the repository folder `ai-review-trends`. Commit or stash any unsaved work on your branch
first (`git status` should show nothing to commit).

```powershell
git switch Tazrian                 # Fahima: git switch Fahima   (your OWN branch)
git fetch origin
git checkout origin/Mastura -- quality_eval/scripts quality_eval/prompts quality_eval/SCORING_GUIDE.md quality_eval/full
git commit -m "Copy scoring files (scripts, prompt_v2_feedback, full set) from Mastura"
python -m venv .venv               # skip if .venv already exists
.\.venv\Scripts\Activate.ps1
python -m pip install google-genai pandas
```

The `git checkout origin/Mastura -- ...` line copies these into your branch, replacing older
versions of the same files:

| Copied | Why it is needed |
|---|---|
| `quality_eval/scripts/` | the scoring script `03_score.py` and `common.py` |
| `quality_eval/prompts/` | `prompt_v2_feedback.txt`, the prompt with feedback |
| `quality_eval/full/` | `full_sample.csv` (the 6,822 reviews) and Mastura's first 316 scores, so they are skipped |
| `quality_eval/SCORING_GUIDE.md` | this guide |

Check that the files are there:

```powershell
Get-ChildItem quality_eval\prompts\prompt_v2_feedback.txt, quality_eval\full\data\full_sample.csv
```

If Mastura says the scripts or prompt were updated, repeat only the `git fetch origin`,
`git checkout origin/Mastura -- quality_eval/scripts quality_eval/prompts quality_eval/SCORING_GUIDE.md`
and `git commit` lines. Do not copy `quality_eval/full` again after you have started scoring;
your own score file is safe either way, but there is no need.

## Run your part (every day until it is finished)

```powershell
cd quality_eval
$env:GEMINI_API_KEY = "<your own key>"
python scripts\03_score.py --folder full --runs 1 --prompt prompt_v2_feedback.txt --part 2 --of 3 --name Tazrian
```

Fahima uses `--part 3 --of 3 --name Fahima`.

- One line is printed per review, e.g. `run 1  317/2274  -> 5   improve: specific|personal`.
- About 5 seconds per review. The free daily quota stops it after a few hundred reviews; the script
  stops by itself after 3 failures in a row ("daily quota used up?"). That is expected.
- Run the same command again the next day (the quota resets at about 2 PM Bangladesh time). It
  continues where it stopped; nothing is scored twice.
- To score at most N reviews in a session, add `--limit N`.

## Save and share your progress (after each session)

From the repository folder `ai-review-trends`:

```powershell
git add quality_eval/full/results/scores_raw_Tazrian.csv          # Fahima: scores_raw_Fahima.csv
git commit -m "Full run: Tazrian's scores so far"
git push origin Tazrian                                           # Fahima: git push origin Fahima
```

Commit only your own `scores_raw_<name>.csv`. Mastura collects the three files at the end.

## Rules (for people and AI assistants)

1. **Never commit or paste an API key into any file.** Set it only with `$env:GEMINI_API_KEY` in the
   terminal. Do not put it in code, `.env` files that are committed, notebooks or screenshots.
2. **Do not edit the prompt** (`prompts/prompt_v2_feedback.txt`) or change the model
   (`gemini-3.5-flash-lite`) or settings in `scripts/03_score.py`. Different prompts or models
   would make the scores inconsistent and unusable for training.
3. **Always pass `--prompt prompt_v2_feedback.txt`.** Its scores are stored as `prompt_v2`, so
   reviews already scored are skipped. Using `prompt_v2.txt` would score without feedback.
4. **Use only your own `--part` and `--name`.** Do not run another person's part.
5. **Do not edit, delete or recreate** `full/data/full_sample.csv`, anyone's `scores_raw*.csv`,
   or anything in `pilot/` and `main/`. Do not run `scripts/11_make_full_set.py`.
6. **Do not score the `main` folder.** The 400 main reviews are the test set for our model and
   must keep their original scores.
7. **Work only on your own branch.** Do not switch to, merge, or push to `Mastura`; copy files
   from it only with the `git checkout origin/Mastura -- ...` command above.
8. If something fails in a way not described here (an error other than the quota message), stop
   and send the error to Mastura instead of changing code.

## What the output looks like

Each row of `scores_raw_<name>.csv`:

| Column | Example |
|---|---|
| `review_id` | `13614491696608` |
| `run` | `1` |
| `overall` | `5` (the score, 1 to 10) |
| `reason` | `The review gives a specific battery claim but no personal usage context.` |
| `weak_criteria` | `personal\|reasoned` (from: specific, personal, reasoned, relevant) |
| `how_to_improve` | `{"personal": "Say how long you have used it ...", "reasoned": "Explain why ..."}` |
| `model`, `prompt_version`, `prompt_file` | `gemini-3.5-flash-lite`, `prompt_v2`, `prompt_v2_feedback.txt` |

## At the end (Mastura)

```powershell
git fetch origin
git checkout origin/Tazrian -- quality_eval/full/results/scores_raw_Tazrian.csv
git checkout origin/Fahima -- quality_eval/full/results/scores_raw_Fahima.csv
cd quality_eval
python scripts\04_summarize.py --folder full --version prompt_v2
python scripts\12_combine_scores.py                 # all_scores.csv + all_scores.json, one row per review
python scripts\15_feedback_from_reasons.py          # feedback for the 816 reviews scored before (.csv + .json)
```

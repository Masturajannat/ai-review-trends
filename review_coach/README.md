# Review Coach

A small web app that rates a product review and suggests how to make it better, in Bangla,
Banglish or English. The reviewer writes freely; the app does two things, each only when asked:

- **Rate my review**: a score from 1 to 10 from our own trained model, with the parts of the
  review that raised or lowered it.
- **Suggest improvements**: reads this one review and gives at most three suggestions. Each
  points at a phrase the reviewer wrote, says what could be added or made clearer there, and
  offers a sentence starter with blanks (`Battery ___ ghonta chole`). It never changes the
  reviewer's opinion, never invents facts, and answers in the review's own language
  (`prompts/suggest_v3.txt`). **Not helpful: show different ones** asks for a new set.

There is no checklist and no product type to choose: a review does not have to follow a fixed
list of points to be useful, and the app works out what kind of product it is from the text.
The product name is optional.

## How the two parts are produced

| Part | Made by | API? |
|---|---|---|
| Score | **our trained model**: XLM-RoBERTa large fine-tuned on the 7,322 Gemini-scored reviews (`quality_model/`; test MAE 0.64, 80% within 1 point of Gemini). Shown in half points. | no, runs on this computer |
| Suggestions | Gemini with `prompts/suggest_v1.txt`, a separate prompt, only when the button is pressed | yes |

For comparison the score can also come from Gemini itself (the dataset's scoring prompt, with a
short "Why this score" paragraph) or from a mock judge for testing. With our model the page shows
only the score; the instructor asked us to remove the highlighting of review parts.
(`evaluator.part_importance` and `evaluator.word_importance` are still in the code for analysis.)
**Suggest improvements** then says, for this review, what would make it more useful.

Suggestions are written in the review's own language: the app detects Bangla, Banglish or English
itself, names it in the prompt (`prompts/suggest_v2.txt`) and asks Gemini again if the answer comes
back in another language.

## Run it (VS Code terminal, PowerShell, from the repository folder `ai-review-trends`)

Once:

1. Download the trained model from Google Drive (`review_quality_model/xlm-roberta-large`, about
   2.2 GB) and put the folder at `quality_model\models_noreadmore\xlm-roberta-large`, so that
   `quality_model\models_noreadmore\xlm-roberta-large\config.json` exists. It is not committed to git.
2. Install the packages (PyTorch for the CPU is enough):

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r review_coach\requirements.txt
```

Every time:

```powershell
.\.venv\Scripts\Activate.ps1
cd review_coach
$env:GEMINI_API_KEY = "<your key>"       # only needed for suggestions (or the Gemini score)
python -m streamlit run app.py --server.headless true
```

Open http://localhost:8501. The first rating loads the model (up to a minute); after that each
rating takes a second or two. Stop the app with Ctrl+C. To use a model in another folder, set
`$env:REVIEW_COACH_MODEL` to that folder before starting.

## Top bar

| Button | What it does |
|---|---|
| My reviews (n) | the reviews started in this browser tab, each with its last score; **Open** loads one again |
| + New review | clears the page for a new review |
| ☾ / ☀ | dark or light theme |
| ⚙ | settings for the project team (below) and **Download data (CSV)**; users don't need it |

## Settings (⚙, for the project team)

| Setting | What it does |
|---|---|
| Score from: our trained model | the default when the model folder is found; no API |
| Score from: Gemini | the dataset's scoring prompt, with a "Why this score" paragraph; one API call |
| Score from: Mock | rough rules, for testing the page only |
| Suggestions from: Gemini / Mock | real suggestions (one API call per press) or a placeholder for testing |

Pressing a button again for exactly the same text reuses the earlier answer. Under the suggestions, **Not helpful: show different
ones** records the rating and asks Gemini again, naming the suggestions already shown so the new
ones are different; it can be pressed again for a third set.

## Files

| File | Purpose |
|---|---|
| `app.py` | the Streamlit page |
| `evaluator.py` | `evaluate(product, review, judge)` for the score (judge `model`, `gemini` or `mock`) and `suggest(product, review, judge)` for the suggestions; the page calls only these |
| `prompts/suggest_v1.txt` | the suggestion prompt |
| `db.py` | SQLite database `review_coach.db` (created automatically, not committed) |
| `export_db.py` | writes every table to `db_export/*.csv` for the report and prints the headline numbers |
| `tests/test_evaluator.py` | checks that need no API key: `python -m pytest tests` (from `review_coach`) |

## Database (`review_coach.db`)

SQLite: one file, no server, Python's built-in `sqlite3`. Foreign keys are on, so a score cannot
point to a draft that does not exist.

| Table | One row per | Main fields |
|---|---|---|
| `sessions` | review a person starts | product_name, created_at, finished |
| `drafts` | version of the review text (the same text is saved once) | session_id, draft_no, product_name, review_text, text_hash, word_count, language |
| `scores` | rating of a draft | draft_id, score (shown), raw_score (exact model output), reason, explanation, judge, model, prompt_version, latency_ms, from_cache |
| `suggestion_sets` | click on "Suggest improvements" (attempt 1) or "Show different ones" (2, 3, ...) | draft_id, attempt, summary, judge, model, prompt_version, latency_ms, from_cache |
| `suggestion_items` | single suggestion | set_id, position, quote, suggestion, example |
| `feedback` | "Suggestions helped" (1) / "Not helpful" (0) | set_id, helpful |

The view `session_summary` gives per session: drafts, first and last score, the change, suggestion
sets and helpful votes. That is the number for the report: does the score go up after suggestions?

A result is reused (`from_cache = 1`) when exactly the same product + review was scored by the same
judge before (or got suggestions from the same prompt); nothing is sent to the API again.

A database made by the earlier version (tables `evaluations`, `suggestions`, `ratings`) is copied
into the new tables the first time the app opens it; the old tables are kept as `legacy_*`.

Export for the report: **⚙ → Download data (CSV)**, or

    python export_db.py          # writes db_export/<table>.csv and prints: helpful share,
                                 # mean score change first to last draft, time to score per judge

No names, emails or API keys are stored. With the Gemini judge the review text is sent to Google;
the project team should mention this to anyone testing the app.

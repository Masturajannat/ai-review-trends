# Review Coach

A small web app that helps a buyer write a more useful product review, in Bangla, Banglish or
English. The reviewer writes freely; the app does two things, each only when asked:

- **Check my review**: a score from 1 to 10 for how useful the review is to someone deciding
  whether to buy, with what the level means and a one-line reason.
- **Suggest improvements**: reads this one review and gives at most three suggestions. Each
  points at a phrase the reviewer wrote, asks what a buyer would still want to know there, and
  offers a sentence starter with blanks (`Battery ___ ghonta chole`). It never changes the
  reviewer's opinion, never invents facts, and answers in the review's own language.

There is no checklist and no product type to choose: a review does not have to follow a fixed
list of points to be useful, and the app works out what kind of product it is from the text.
The product name is optional.

## How the two parts are produced

| Part | Now | Later |
|---|---|---|
| Score | Gemini with the dataset's scoring prompt (`quality_eval/prompts/prompt_v2.txt`, `gemini-3.5-flash-lite`) | our own model trained on the scored dataset, no API |
| Suggestions | Gemini with `prompts/suggest_v1.txt`, a separate prompt that has nothing to do with scoring | stays an API call, because suggestions must be written for each review |

## Run it (VS Code terminal, PowerShell, from the repository folder `ai-review-trends`)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r review_coach\requirements.txt
cd review_coach
$env:GEMINI_API_KEY = "<your key>"       # skip this to use only the mock judge
python -m streamlit run app.py --server.headless true
```

Open http://localhost:8501. Stop the app with Ctrl+C in the terminal.

## Settings (left sidebar)

| Setting | What it does |
|---|---|
| Dark theme | switches the page colours |
| Judge: Gemini | real score and real suggestions; one API call per button press |
| Judge: Mock | rough rules and a placeholder suggestion, no API calls; only for testing the page |

Pressing a button again for exactly the same text reuses the earlier answer (no new API call).

## Files

| File | Purpose |
|---|---|
| `app.py` | the Streamlit page |
| `evaluator.py` | `evaluate(product, review, judge)` for the score and `suggest(product, review, judge)` for the suggestions; the page calls only these |
| `prompts/suggest_v1.txt` | the suggestion prompt |
| `db.py` | SQLite database `review_coach.db` (created automatically, not committed) |
| `tests/test_evaluator.py` | checks that need no API key: `python -m pytest tests` (from `review_coach`) |

## Database (`review_coach.db`)

| Table | One row per | Main fields |
|---|---|---|
| `sessions` | review being written | product_name, created_at, finished |
| `evaluations` | click on "Check my review" | draft_no, review_text, language, word_count, score, level, reason, judge, model, prompt_version, latency_ms |
| `suggestions` | click on "Suggest improvements" | review_text, summary, suggestions (JSON), n_suggestions, judge, model, prompt_version, latency_ms |
| `ratings` | "Suggestions helped" / "Not helpful" click | suggestion id, helpful |

No names, emails or API keys are stored. With the Gemini judge the review text is sent to Google;
the page says so in the sidebar.

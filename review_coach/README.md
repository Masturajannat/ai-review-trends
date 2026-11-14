# Review Coach (MVP)

A small web app that helps a buyer write a more useful product review. You type the product and
your review (Bangla, Banglish or English), press **Check my review**, and see:

- **Score 1 to 10** with what the level means and what the next level needs
- **Checklist of 10 yes/no checks**, grouped under the four criteria of a good review
  (specific, personal, reasoned, relevant)
- **How to improve**: one concrete tip per weak criterion, for this review and this product
- **Your drafts**: the score of each version you checked (e.g. 2 → 6 → 8)

The judging is the same as in our scored dataset: prompt `quality_eval/prompts/prompt_v2_checks.txt`
and model `gemini-3.5-flash-lite`. So what the app says matches the labels our own model will be
trained on. Later, the trained model can replace Gemini as the judge without changing the app.

## Run it (VS Code terminal, PowerShell, from the repository folder `ai-review-trends`)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r review_coach\requirements.txt
cd review_coach
$env:GEMINI_API_KEY = "<your key>"       # skip this to use only the mock judge
python -m streamlit run app.py --server.headless true
```

The app opens in the browser at http://localhost:8501. Stop it with Ctrl+C in the terminal.

## Judges (left sidebar)

| Judge | What it does | API calls |
|---|---|---|
| Gemini (real score) | same prompt and model as the dataset | 1 per check |
| Mock (for testing) | simple rules (numbers, time words, "but/kintu", ...); not a real score | none |

Use the mock judge while changing the layout, so the daily quota is not used up. Checking exactly
the same product and text again reuses the earlier answer (no new API call).

## Files

| File | Purpose |
|---|---|
| `evaluator.py` | `evaluate(product, review, judge)`: the only function the app calls; always returns the same keys |
| `db.py` | SQLite database `review_coach.db` (created automatically, not committed) |
| `app.py` | the Streamlit page |
| `.streamlit/config.toml` | colours |
| `tests/test_evaluator.py` | checks that need no API key: `python -m pytest tests` (from `review_coach`) |

## Database (`review_coach.db`)

| Table | One row per | Main fields |
|---|---|---|
| `sessions` | review being written | product_name, category, created_at, finished |
| `evaluations` | click on "Check my review" | draft_no, review_text, language, word_count, score, level, reason, check_product_detail ... check_on_topic, weak_criteria, how_to_improve, judge, model, prompt_version, latency_ms, cache_key, from_cache |
| `ratings` | "Tips helped" / "Not helpful" click | eval_id, helpful, comment |

No names, emails or API keys are stored. With the Gemini judge, the review text is sent to Google
to be checked; the app says so in the sidebar.

## Next steps

1. Try about 10 real reviews in all three languages with the Gemini judge.
2. Add an `own_model` judge in `evaluator.py` once our model is trained.
3. Optional: guided questions for each missing check (the user's own answers only).

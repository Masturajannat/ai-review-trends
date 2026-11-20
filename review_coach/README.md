# Review Coach

A small web app that helps a buyer write a more useful product review, in Bangla, Banglish or
English. The reviewer writes freely; the app does two things, each only when asked:

- **Rate my review**: a score from 1 to 10 for how useful the review is to someone deciding
  whether to buy, with what the level means and a short paragraph explaining the score:
  what the review tells a buyer and what keeps the score from being higher, written about this
  review in its own language.
- **Suggest improvements**: reads this one review and gives at most three suggestions. Each
  points at a phrase the reviewer wrote, asks what a buyer would still want to know there, and
  offers a sentence starter with blanks (`Battery ___ ghonta chole`). It never changes the
  reviewer's opinion, never invents facts, and answers in the review's own language.

There is no checklist and no product type to choose: a review does not have to follow a fixed
list of points to be useful, and the app works out what kind of product it is from the text.
The product name is optional.

## How the two parts are produced

| Part | Made by | API? |
|---|---|---|
| Score | **our trained model**: XLM-RoBERTa large fine-tuned on the 7,322 Gemini-scored reviews (`quality_model/`; test MAE 0.64, 80% within 1 point of Gemini). Shown in half points with what its level means. | no, runs on this computer |
| Suggestions | Gemini with `prompts/suggest_v1.txt`, a separate prompt, only when the button is pressed | yes |

For comparison the score can also come from Gemini itself (the dataset's scoring prompt, with a
short "Why this score" paragraph) or from a mock judge for testing. With our model there is no
paragraph. Instead the card **"What the score is based on"** shows the review cut into its parts
(sentences, and long sentences at commas and words like "but" / "kintu" / "তবে"), each shaded by
how much it moves the model's score: the score of the whole review minus the score with that part
left out. Blue parts raised it, red parts pulled it down, with the change in points (no API).
`evaluator.word_importance` gives the same per word (integrated gradients), but single words such
as "but", "a" or a full stop are hard for a reviewer to read, so the page shows parts.
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

## Settings (left sidebar)

| Setting | What it does |
|---|---|
| Dark theme | switches the page colours |
| Score from: our trained model | the default when the model folder is found; no API |
| Score from: Gemini | the dataset's scoring prompt, with a "Why this score" paragraph; one API call |
| Score from: Mock | rough rules, for testing the page only |
| Suggestions from: Gemini / Mock | real suggestions (one API call per press) or a placeholder for testing |

Pressing a button again for exactly the same text reuses the earlier answer.

## Files

| File | Purpose |
|---|---|
| `app.py` | the Streamlit page |
| `evaluator.py` | `evaluate(product, review, judge)` for the score (judge `model`, `gemini` or `mock`) and `suggest(product, review, judge)` for the suggestions; the page calls only these |
| `prompts/suggest_v1.txt` | the suggestion prompt |
| `db.py` | SQLite database `review_coach.db` (created automatically, not committed) |
| `tests/test_evaluator.py` | checks that need no API key: `python -m pytest tests` (from `review_coach`) |

## Database (`review_coach.db`)

| Table | One row per | Main fields |
|---|---|---|
| `sessions` | review being written | product_name, created_at, finished |
| `evaluations` | click on "Rate my review" | draft_no, review_text, language, word_count, score, level, reason, judge, model, prompt_version, latency_ms |
| `suggestions` | click on "Suggest improvements" | review_text, summary, suggestions (JSON), n_suggestions, judge, model, prompt_version, latency_ms |
| `ratings` | "Suggestions helped" / "Not helpful" click | suggestion id, helpful |

No names, emails or API keys are stored. With the Gemini judge the review text is sent to Google;
the page says so in the sidebar.

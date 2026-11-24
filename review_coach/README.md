# Review Coach

A small web app that rates a product review and suggests how to make it better, in Bangla,
Banglish or English. It is the second step of a demo: the reviewer first picks a product in
**ShopLite**, a very small dummy shop (folder `shop/`), then presses **Write a review** on the
product page, which opens Review Coach for that product. The reviewer writes freely; the app does
two things, each only when asked:

- **Rate my review**: a score from 1 to 10 from our own trained model, with the parts of the
  review that raised or lowered it.
- **Suggest improvements**: reads this one review and gives at most three suggestions. Each
  points at a phrase the reviewer wrote, says what could be added or made clearer there, and
  gives a complete example sentence for this product ("I used this face wash for 7 weeks before
  the bumps on my cheeks disappeared."), which the reviewer replaces with their own experience. It never
  changes the reviewer's opinion, and answers in the review's own language (`prompts/suggest_v5.txt`).
  If the review is about a different kind of product than the one chosen (a sofa review under a
  face wash), it gives one suggestion that says so. **Not helpful: show different ones** asks for a
  new set.
- **Submit review**: appears in the top bar once the review has a score (and only while the text is
  the one that was scored). It adds the review to the product's list in ShopLite.

There is no checklist to follow: a review does not have to cover a fixed list of points to be
useful. The product is not typed: it comes from the shop link (`?product=<id>`), is shown locked,
and its name and type (for example "body wash") are sent to Gemini with the review. Opened without
a product, the page asks the reviewer to pick one in the shop first.

The whole review page fits one screen without scrolling; the score is a bar, not a circle.

## How the two parts are produced

| Part | Made by | API? |
|---|---|---|
| Score | **our trained model**: XLM-RoBERTa large fine-tuned on the 7,322 Gemini-scored reviews (`quality_model/`; test MAE 0.64, 80% within 1 point of Gemini). Shown in half points. | no, runs on this computer |
| Suggestions | Gemini with `prompts/suggest_v5.txt`, a separate prompt, only when the button is pressed | yes |

For comparison the score can also come from Gemini itself (the dataset's scoring prompt, with a
short "Why this score" paragraph) or from a mock judge for testing. With our model the page shows
only the score; the instructor asked us to remove the highlighting of review parts.
(`evaluator.part_importance` and `evaluator.word_importance` are still in the code for analysis.)
**Suggest improvements** then says, for this review, what would make it more useful.

Suggestions are written in the review's own language: the app detects Bangla, Banglish or English
itself, names it in the prompt and asks Gemini again if the answer comes
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

Every time, the shop and the coach together (the first run also makes `shop\shop.db`):

```powershell
.\.venv\Scripts\Activate.ps1
$env:GEMINI_API_KEY = "<your key>"       # only needed for suggestions (or the Gemini score)
python run_demo.py
```

The shop opens at http://localhost:8502; the coach runs at http://localhost:8501 and is opened from a
product page. The first rating loads the model (up to a minute); after that each rating takes a
second or two. Stop both with Ctrl+C. To use a model in another folder, set `$env:REVIEW_COACH_MODEL`
to that folder before starting.

To start them by hand, in two terminals: `cd review_coach` then
`python -m streamlit run app.py --server.port 8501`, and `cd shop` then `python build_shop_db.py`
(once) and `python -m streamlit run shop_app.py --server.port 8502`. More in `shop\README.md`.

## How to use it (the demo)

1. In ShopLite, open a product (20 of the most reviewed products of the dataset) and read its reviews.
2. Press **Write a review**. Review Coach opens with that product fixed.
3. Write the review, press **Rate my review** to see the score, and **Suggest improvements** if wanted.
   Edit and rate again as often as you like.
4. After a score is shown, press **Submit review** (top bar). The review is saved in `shop.db`.
5. Press **Back to the product**: the review is at the top of the list, marked "New".
   **Write another review** starts again for the same product.

## What changed (22 Nov 2026)

| File | Change |
|---|---|
| `review_coach/app.py` | score shown as a bar, not a circle; tighter spacing so the page needs no scrolling; product comes from the shop link and is locked; "Pick a product in the shop first" screen; **Submit review** in the top bar after a score; "Review added" screen; "My reviews" lists only this product; examples shown with "e.g." |
| `review_coach/evaluator.py` | `suggest()` takes `product_type`; uses `suggest_v5.txt` |
| `review_coach/prompts/suggest_v5.txt` | new (replaces v3/v4): product-match check, questions that fit the product, complete example sentences instead of blanks, product type in the prompt |
| `shop/shop_app.py` | new: the dummy shop (product grid, product page, reviews with language filter) |
| `shop/shop_db.py` | new: reads and writes `shop.db` for the shop and the coach |
| `shop/build_shop_db.py` | new: makes `shop.db` from `combined_reviews.csv` (20 products, name and type written by hand in the file) |
| `shop/test_shop_db.py`, `shop/README.md` | new: tests and short notes |
| `run_demo.py` | new: starts the shop and the coach together |

## Top bar

| Button | What it does |
|---|---|
| My reviews (n) | the reviews started in this browser tab, each with its last score; **Open** loads one again |
| Submit review | shown only after the review has a score; adds it to the product in the shop |
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
| `prompts/suggest_v5.txt` | the suggestion prompt |
| `db.py` | SQLite database `review_coach.db` (created automatically, not committed) |
| `export_db.py` | writes every table to `db_export/*.csv` for the report and prints the headline numbers |
| `tests/test_evaluator.py` | checks that need no API key: `python -m pytest tests` (from `review_coach`) |
| `../shop/` | the dummy shop and its database `shop.db` (made by `build_shop_db.py`, not committed) |

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

The view `review_scores` lists every score with its product, review text, language and words (open it in
VS Code's SQLite Viewer or DB Browser for SQLite). The view `session_summary` gives per session: drafts, first and last score, the change, suggestion
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

## Shop database (`shop/shop.db`)

Separate from `review_coach.db`. Table `products` (product_id, platform, name, type) and table
`reviews` (product_id, review_text, language, score, written_at, source). `source` is `dataset` for
the original reviews and `coach` for reviews submitted here; their `score` is the one the reviewer saw.
Running `build_shop_db.py` again rebuilds it and removes the submitted reviews.

## Console log (terminal)

Each press of **Rate my review** prints a log in the terminal that runs the app (`run_demo.py`); the page
itself does not change. `console_log.py` prints, in order: the request (product, review, language, words),
how the score was made (tokens read, model output, rounding, level), what our model reacted to (points each
sentence added: the score of the whole review minus the score without that sentence), and the response sent to the page. After that, a short Gemini note arrives: Gemini is given the review,
the model's score and the sentence points, and only explains them (`prompts/console_note_v1.txt`). It does
not give a score and is not used for the score; the four criteria words in it are optional labels. The note
needs `GEMINI_API_KEY` and "Suggestions from: Gemini"; without them the console says "note unavailable".
Set `NOTE_IN_BACKGROUND = False` in `console_log.py` to print the note before the next step instead of when
it arrives.

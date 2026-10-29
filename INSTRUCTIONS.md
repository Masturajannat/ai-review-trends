# Instructions

Step-by-step guide for setting up the project, working with Git, running the analysis and adding
new reviews. For the research design and results, see `README.md` and `trend_analysis/README.md`.

## 1. Setup

### Requirements

- Python 3.10 or newer
- Git
- VS Code (recommended)

### Get the code

```powershell
git clone https://github.com/Masturajannat/ai-review-trends.git
cd ai-review-trends
git config core.autocrlf true      # avoids line-ending noise on Windows
```

### Python environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # the prompt now starts with (.venv)
pip install pandas numpy matplotlib
```

Only needed for scraping:

```powershell
pip install requests playwright
python -m playwright install chromium
```

In VS Code, select the same interpreter (`Ctrl+Shift+P` → **Python: Select Interpreter** →
`.venv`) so that import warnings disappear.

## 2. Working with Git

`main` holds the current, reviewed version of the project. Each team member works on a personal
branch (`Mastura`, `Tazrian`, `Fahima`).

### Start of a work session

```powershell
git switch <your-branch>
git fetch origin
git merge origin/main               # bring in the latest work from the team
```

### Save and share work

```powershell
git status                           # check what changed
git add <files>                      # add specific files; avoid "git add ." for data you did not mean to change
git commit -m "Short description of the change"
git push origin <your-branch>
```

### Update main

When the work on your branch is complete and the scripts run without errors:

```powershell
git switch main
git pull origin main
git merge <your-branch>
git push origin main
git switch <your-branch>
```

Alternatively, open a pull request on GitHub (**Pull requests → New → base: main, compare:
your-branch**) so that the team can review the change first.

### Rules

- Never put API keys in code, CSV files or commit messages. Set them in the terminal only, for
  example `$env:GEMINI_API_KEY = "..."`. If a key is ever committed or shared, revoke it and create
  a new one.
- `raw_daraz/` contains reviewer names and is excluded from Git (`.gitignore`). Keep it local.
- Close CSV files in Excel before running scripts or Git commands; Excel locks open files.
- Do not edit files in `archive/`; it records earlier approaches.

## 3. Running the analysis

Run all commands from the repository root with the virtual environment active. Each step reads the
output of the previous one, so run them in order after any change to the data.

| Step | Command | Produces |
|---|---|---|
| 1 | `python combine_reviews_all.py` | `combined_reviews.csv`: all scraped reviews in one file |
| 2 | `python trend_analysis\scripts\01_build_dataset.py` | Cleaned dataset with language tags and periods (`trend_analysis/data/`) |
| 3 | `python trend_analysis\scripts\02_build_ai_reference.py` | AI-generated reference reviews in the original language |
| 4 | `python trend_analysis\scripts\03_marker_words.py` | Candidate marker words, control words, held-out check |
| 5 | `python trend_analysis\scripts\04_trends.py` | Marker-word trends per platform and language, charts |
| 6 | `python trend_analysis\scripts\05_banglish.py` | Banglish standard-spelling share and cross-fitted markers |
| 7 | `python trend_analysis\scripts\06_language_mix.py` | Language of reviews over time |
| 8 | `python trend_analysis\scripts\07_ai_share.py` | Estimated AI share, validated on known mixtures |

Step 1 is needed only after the scraped files change. All results are written to
`trend_analysis/results/`; each script prints a summary when it finishes.

### Main outputs

| File | What it shows |
|---|---|
| `results/dataset_counts.csv` | Reviews per platform, language and period |
| `results/marker_check.csv` | How well the marker words separate AI from human reviews |
| `results/trend_changes.csv` | Change in marker words after ChatGPT, with confidence intervals and robustness checks |
| `results/fig_period_comparison.png` | Marker share before and after ChatGPT for each series |
| `results/fig_trend_halfyear.png` | Marker share by half-year |
| `results/fig_word_shift.png` | Each marker word before and after ChatGPT |
| `results/fig_banglish.png` | Banglish standard-spelling share and markers |
| `results/fig_language_mix.png` | Language of reviews by year |
| `results/fig_ai_share.png` | Validation of the AI-share estimate and estimates per series |

## 4. Adding new reviews

New reviews are collected in **rounds**. Each round writes a new CSV file; earlier files are never
overwritten. `sources.csv` lists every file to include, with its platform, scrape date and round
(`batch`):

```
file,platform,scrape_date,batch,note
rokomari_reviews.csv,Rokomari,2026-10-16,1,round 1
rokomari_reviews_round2.csv,Rokomari,2026-10-29,2,round 2: 12 additional books
```

1. **Choose products.** Prefer products that have reviews both before and after 30 November 2022,
   in the existing categories (Daraz: earphones and gadgets; Rokomari: books; Shajgoj: skincare).
2. **Rokomari:** put one book link per line in `rokomari_urls_round2.txt` (or a new URL file) and run
   ```powershell
   python rokomari_scraper_round2.py
   python rokomari_scraper_round2.py --urls rokomari_urls_round3.txt --out rokomari_reviews_round3.csv --batch 3
   ```
   The scraper skips reviews already in `rokomari_reviews.csv`, saves after every book and can be
   restarted; add `--redo` to collect books again, `--headed` to watch the browser.
   **Daraz and Shajgoj:** copy the scraper, change its product list and output file name so the
   round-1 file is not overwritten.
3. **Register the file:** add a row to `sources.csv` with the file name, platform, scrape date
   (YYYY-MM-DD) and the next batch number. The scrape date is used to convert Daraz dates such as
   "3 weeks ago", so it must be the day the file was collected.
4. **Rerun steps 1–8** of section 3. `combine_reviews_all.py` prints the number of reviews per
   file; a review that appears in two files is kept once, from the earlier round.
5. **Check** `results/dataset_counts.csv` and the summary printed by `01_build_dataset.py`
   (kept reviews by platform and batch). No date warnings should appear.

Scraped CSV files contain no reviewer names. Raw API responses (`raw_daraz/`) stay local and are
not committed.

## 5. Editing the word lists

Three hand-curated files define the analysis. Edit them carefully, keep a record in the commit
message, and choose words without looking at post-ChatGPT results.

| File | Purpose | Rule |
|---|---|---|
| `trend_analysis/markers.csv` | Marker words for Bangla, Banglish and English | Only evaluative adjectives/adverbs (`evaluative`) and formal function words (`formal`) from `results/marker_candidates_<language>.csv`; never product, shopping or topic words |
| `trend_analysis/banglish_variants.csv` | Banglish spelling variants and their standard (Avro Phonetic) form | One canonical form per word; a spelling may appear in only one family |
| `EVALUATIVE` list in `05_banglish.py` | Banglish evaluative words from which markers are chosen automatically | Evaluative words only, in canonical spelling |

After editing, rerun steps 2–8.

## 6. Troubleshooting

| Problem | Solution |
|---|---|
| `ModuleNotFoundError: No module named 'pandas'` | Activate the environment (`.venv\Scripts\Activate.ps1`) and run `pip install pandas numpy matplotlib` |
| `PermissionError` when saving a CSV | Close the file in Excel and run again |
| VS Code shows "Import could not be resolved" | Select the `.venv` interpreter (section 1) |
| Bengali words appear as boxes in charts | Install a Bengali font (e.g. Nirmala UI, included with Windows); charts label Bangla markers by their English meaning anyway |
| `git push` is rejected | Run `git fetch origin` and `git merge origin/<branch>` first, then push again |
| Many files show as modified after cloning | Run `git config core.autocrlf true` (line endings) |

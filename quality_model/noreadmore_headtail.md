# "Read More" strip and head+tail runs (19 Nov 2026)

Two follow-up experiments on the XLM-RoBERTa review-quality model, started from the Rokomari
investigation (`rokomari_check/rokomari.md`). Final decision at the bottom.

## Why we ran them

- Rokomari is the hardest platform for every model (xlm-r test MAE 0.78 against 0.55 on Daraz).
- 503 Rokomari reviews (30% of that platform, none on Daraz or Shajgoj) end with the scraping
  leftover "Read More". These are long reviews the site had cut to a preview. They score higher
  on average (5.96 against 4.15), and real users never type "Read More", so the model could have
  learned it as a shortcut. 22 of the 130 Rokomari test reviews have it.
- About 20% of the Rokomari training reviews are longer than 256 tokens, so the end of the review
  (where the verdict usually is) is cut off.

Two changes were tested, one at a time:

1. **Strip "Read More"** from the end of every review (train, validation and test).
2. **Head+tail** for reviews over 256 tokens: keep the first 128 and the last 128 tokens instead of
   the first 256.

## What changed in the code

| File | Change |
|---|---|
| `scripts/common.py` | New `RUN_TAG` environment variable. With a tag, results go to `results_<tag>/` and models to `models_<tag>/`. Tags starting with `noreadmore` also strip a trailing "Read More" in `load()`. With no tag nothing changes. |
| `scripts/03_train_transformer.py` | New `--head-tail` flag (off by default). The results header shows `(head+tail)` and `score_scale.json` records `head_tail`, so the app can cut text the same way. |
| `scripts/04_ensemble.py` | New. Averages the saved test predictions of several runs and estimates a straight-line calibration. No training, no GPU. |
| `.gitignore` | Added `models_*/` so the tagged model folders are not committed. |

## How to run

PowerShell, venv active, from `quality_model`, charger plugged in, fan on Performance. `RUN_TAG`
lasts only for that PowerShell window: set it again in a new window, and check it with
`echo $env:RUN_TAG`. To go back to the old behaviour: `Remove-Item Env:RUN_TAG`.

| `RUN_TAG` | `--head-tail` | What happens | Output folders |
|---|---|---|---|
| not set | no | the original run: "Read More" kept, first 256 tokens | `results/`, `models/` |
| not set | yes | head+tail, "Read More" still in the text | `results/`, `models/` |
| `noreadmore` | no | "Read More" stripped, first 256 tokens | `results_noreadmore/`, `models_noreadmore/` |
| `noreadmore_headtail` | yes | stripped and head+tail | `results_noreadmore_headtail/`, `models_noreadmore_headtail/` |

Running without a tag writes into the old `results/` and `models/` folders and can overwrite them.
Keep a copy first (`Copy-Item results results_backup -Recurse`).

### Strip only

```powershell
$env:RUN_TAG = "noreadmore"
python scripts/01_baseline.py
python scripts/03_train_transformer.py --model xlm-roberta-base
```

### Strip and head+tail

```powershell
$env:RUN_TAG = "noreadmore_headtail"
python scripts/01_baseline.py
python scripts/03_train_transformer.py --model xlm-roberta-base --head-tail
```

- `01_baseline.py` goes first because `03` reads the baseline predictions from the tagged folder to
  fill its baseline column. It takes about 2 minutes.
- If the baseline stops with `No module named 'matplotlib'`, run `pip install matplotlib`. The
  results and predictions are saved before the chart is drawn, so only `fig_baseline.png` is missing.
- Training takes about 7 minutes on the RTX 5050 laptop GPU (peak VRAM about 7 GB of 8 GB).
- Check that the first line says `on cuda`.
- Other tags (for example `noreadmore_lr3`) work too, as long as they start with `noreadmore`
  if the strip should apply.

### Ensemble check (no training)

```powershell
python scripts/04_ensemble.py
```

It reads the prediction files in `results_local/` and `results_colab/`. Edit the paths at the top
to point it at another folder.

## What was actually run

All with xlm-roberta-base, 5 epochs, learning rate 2e-5, batch 16, max 256 tokens, seed 299,
local RTX 5050. Train 6,230, validation 692, test 400 (the main-run reviews, never trained on).

| Run | Command | Folder |
|---|---|---|
| Old (before this work) | `python scripts/03_train_transformer.py --model xlm-roberta-base` | `results_local/` |
| Strip | `RUN_TAG=noreadmore`, baseline then `03 ... --model xlm-roberta-base` | `results_noreadmore/` |
| Strip + head+tail | `RUN_TAG=noreadmore_headtail`, baseline then `03 ... --model xlm-roberta-base --head-tail` | `results_noreadmore_headtail/` |

The baseline (TF-IDF + ridge) was also rerun with the strip. It did not change: MAE 0.84, within
1 point 66%, Rokomari 0.83.

## Results (400 test reviews)

| | Old | Strip | Strip + head+tail |
|---|---|---|---|
| MAE | 0.650 | 0.668 | 0.661 |
| RMSE | 0.93 | 0.96 | 0.91 |
| Within 1 point | 78.2% | 77.5% | 78.5% |
| Within 0.5 | 54% | 53% | 50% |
| Rank correlation | 0.870 | 0.862 | 0.868 |
| Daraz MAE | 0.55 | 0.56 | 0.57 |
| Rokomari MAE | 0.78 | 0.82 | 0.82 |
| Shajgoj MAE | 0.62 | 0.63 | 0.60 |
| Rokomari, the 22 with "Read More" | 1.20 | 1.47 | 1.35 |
| Rokomari, the other 108 | 0.70 | 0.68 | 0.72 |
| Reviews of 150+ words (11 in the test set) | 1.34 | 1.35 | 1.51 |
| Best epoch | 5 | 5 | 4 |
| Validation MAE | 0.56 | 0.59 | 0.57 |
| Training time | 419 s | 418 s | 409 s |

For scale: Gemini run 1 against run 2 has MAE 0.23, and the baseline has MAE 0.84.

Other checks on the saved predictions (`04_ensemble.py`):

- Averaging xlm-r and BanglaBERT (local and Colab) gives MAE 0.64 to 0.65, against 0.65 for xlm-r alone.
  It does not help Rokomari.
- A straight-line calibration is the identity (score = 1.01 x prediction - 0.05), so it adds nothing.

## What the results say

- **Stripping "Read More" made no real difference.** Overall MAE moved by 0.02 and Rokomari by
  0.04, both inside the roughly 0.03 noise of one seed on 400 reviews. The 22 reviews that had
  "Read More" got a little worse (1.20 to 1.47), so the model had used it as a weak length cue.
  That cue is not available to real users, so the stripped numbers are the honest ones for the app.
- **Head+tail did not help.** Rokomari stayed at 0.82, and the longest reviews got slightly worse
  (1.35 to 1.51, only 11 reviews). The one review we suspected of being cut (id `3d84d23523185154`,
  label 8) still scored 4.6 with its ending visible, so truncation was not the cause there.
- **Rokomari stays the weak spot** (MAE 0.82, rank correlation 0.71, against 0.90 or more on the
  other platforms). The errors are mostly long reviews, thanks messages, quotes and generic praise;
  Gemini's own labels on those are also the least settled.
- Reading the 22 "Read More" test reviews with Gemini's reasons, most labels looked fair. About 3
  or 4 plot-summary reviews end exactly where the reviewer's own opinion would start, so a low
  label there may be unfair. That cannot be checked because the hidden text was never scraped.

## Decision

**Use the stripped, plain 256-token model: `models_noreadmore/xlm-roberta-base`.**

- It is the simplest: no special text cutting is needed in the app.
- It cannot depend on "Read More", which users never write.
- Head+tail is not better, so it is not worth the extra code.
- Test numbers to report: MAE 0.67, 77.5% within 1 point, rank correlation 0.86 (one seed, 400 reviews).
- BanglaBERT and MuRIL were not retrained: the xlm-r result barely moved, and MuRIL was far behind before.
- No ensemble and no calibration for now: the gain is about 0.02 and costs several models in the app.
- `models_noreadmore_headtail/` is not needed and can be deleted (about 1 GB). Its results folder stays as a record.

## Limits

- One seed and 400 test reviews: differences under about 0.03 MAE are noise.
- The test text differs between the old and the stripped runs (the strip also applies to the test
  reviews), so the old and new numbers are not strictly on the same input.
- Only 22 test reviews have "Read More" and 11 are 150+ words; those rows are indicative only.
- Colab was not rerun: the notebook clones the `Mastura` branch, which does not have these changes.

## Next

Build the Streamlit app around `models_noreadmore/xlm-roberta-base` (the score only; tips and
explanations still need another source).

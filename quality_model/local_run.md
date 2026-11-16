# Local run: review-quality transformers

Local re-run of `scripts/03_train_transformer.py` on own laptop, to check against the Colab results.

## Setup

- Laptop: PyTorch reports the GPU as `NVIDIA GeForce RTX 5050 Laptop GPU`.
- Windows + PowerShell, PyTorch `cu128` build.
- Run one model at a time, charger plugged in, fan on Performance.
- Same settings for all three models: 5 epochs, learning rate 2e-5, batch 16, max 256 tokens, seed 299.
- Data: train 6230, validation 692, test 400 (the main-run reviews, never trained on).
- Each run keeps the epoch with the lowest validation MAE (epoch 5 for xlm-roberta-base and MuRIL, epoch 4 for BanglaBERT).
- No crashes, no out-of-memory errors, no reruns, `--batch 8` was never needed.
- Peak GPU temperature stayed around 65 to 69 C, and VRAM use was about 7.1 GB of 8 GB.

## Results (test set, 400 reviews)

| Model | MAE | RMSE | Within 1 point | Within 0.5 | Spearman | Train time |
|---|---|---|---|---|---|---|
| xlm-roberta-base | 0.650 | 0.93 | 78.2% | 54% | 0.870 | 419 s |
| csebuetnlp/banglabert | 0.681 | 0.96 | 74.2% | 54% | 0.857 | 298 s |
| google/muril-base-cased | 0.821 | 1.12 | 67.5% | 43% | 0.820 | 374 s |
| Baseline (TF-IDF + ridge) | 0.844 | 1.13 | 65.8% | 42% | 0.804 | n/a |
| Gemini run 1 vs run 2 (yardstick) | 0.225 | 0.49 | 99.2% | 78% | 0.965 | n/a |

Lower MAE is better. Higher within-1-point and Spearman are better.

## What I found

1. **All three transformers have a lower MAE than the baseline, but MuRIL only just beats it** (0.821 vs 0.844). Its within-1-point score (67.5%) is close to the baseline's (65.8%).
2. **xlm-roberta-base scored best on every headline number, but the gap to BanglaBERT is small.** The MAE difference is 0.03, and this is one seed on 400 test reviews, so I would not claim a firm ranking between those two.
3. **BanglaBERT trained fastest** (298 s) and overfit the most: its training loss fell to 0.07, and its best validation epoch was 4, not 5.
4. **No model gets close to the Gemini-vs-Gemini yardstick.** The best transformer has an MAE of 0.65 against 0.23 between two Gemini runs, so the models are a reasonable but not human-level or LLM-level scorer.

### By language (test MAE)

| Model | Bangla | Banglish | English |
|---|---|---|---|
| xlm-roberta-base | 0.68 | 0.59 | 0.66 |
| csebuetnlp/banglabert | 0.67 | 0.59 | 0.77 |
| google/muril-base-cased | 0.80 | 0.80 | 0.87 |

- Banglish is the easiest language for xlm-roberta-base and BanglaBERT.
- BanglaBERT is relatively weaker on English (0.77), which fits a model pretrained on Bangla.

### By platform (test MAE)

| Model | Daraz | Rokomari | Shajgoj |
|---|---|---|---|
| xlm-roberta-base | 0.55 | 0.78 | 0.62 |
| csebuetnlp/banglabert | 0.66 | 0.79 | 0.59 |
| google/muril-base-cased | 0.72 | 0.88 | 0.86 |

- **Rokomari is the hardest platform for every model.** Its Spearman is also the lowest each time (0.74, 0.72 and 0.66), compared with 0.87 to 0.92 elsewhere.

### By true score band (mean error)

| Model | Label 1-3 | Label 3.5-5 | Label 5.5-7 | Label 7.5-10 |
|---|---|---|---|---|
| xlm-roberta-base | +0.46 | +0.23 | -0.20 | -0.63 |
| csebuetnlp/banglabert | +0.36 | +0.13 | -0.44 | -0.73 |
| google/muril-base-cased | +0.46 | -0.02 | -0.59 | -1.16 |

- **All models pull scores toward the middle.** Low-scored reviews are over-predicted and high-scored reviews are under-predicted, and MuRIL does this most strongly (-1.16 for the 7.5-10 band, with only 22% within 1 point).
- **Within a single band, ranking is weak** (Spearman between 0.27 and 0.60). The models separate good reviews from bad ones overall, but are much less reliable at ordering reviews that have similar scores.
- The 7.5-10 band has only 32 test reviews, so its numbers are noisy.

## Where the files are

- Tables and test results from this local run: `quality_model/results_local/` (`model_comparison.csv` holds all models). They were moved out of `results/` so they do not clash with the Colab results when the branches are merged.
-Saved transformer models: `quality_model/models/` (xlm-roberta-base, google_muril-base-cased, csebuetnlp_banglabert). They are large, so they are git-ignored and not pushed. Rerun the script to regenerate them.
- Comparison with the Colab run: not done yet, because the Colab run has not been done at the time of writing.

# Local run vs Google Colab run

The three transformers were trained twice with the same code, data and settings: once on a laptop GPU
([local_run.md](local_run.md), results in `results_local/`) and once on a Google Colab T4 GPU
(results in `results_colab/`). This page checks whether the two runs agree.

## Colab setup

- Notebook: `train_transformer_colab.ipynb`, run on 2026-11-17 on a free Colab Tesla T4, code cloned from the `Tazrian` branch.
- Same settings as the local run: 5 epochs, learning rate 2e-5, batch 16, max 256 tokens, seed 299.
- Same data: 6,230 training, 692 validation, 400 test reviews (the main run, never trained on).
- The script keeps the epoch with the lowest validation MAE.

## Results on the 400 test reviews

| Model | MAE local | MAE Colab | Within 1 local | Within 1 Colab | Within 0.5 local | Within 0.5 Colab | Rank corr. local | Rank corr. Colab |
|---|---|---|---|---|---|---|---|---|
| xlm-roberta-base | **0.650** | **0.683** | 78.2% | 74.5% | 54.0% | 51.0% | 0.870 | 0.858 |
| csebuetnlp/banglabert | 0.681 | 0.688 | 74.2% | 75.0% | 53.5% | 53.2% | 0.857 | 0.856 |
| google/muril-base-cased | 0.821 | 0.807 | 67.5% | 71.0% | 42.8% | 44.8% | 0.820 | 0.814 |
| Baseline (TF-IDF + ridge) | 0.844 | 0.844 | 65.8% | 65.8% | 41.8% | 41.8% | 0.804 | 0.804 |
| Gemini run 1 vs run 2 (yardstick) | 0.225 | 0.225 | 99.2% | 99.2% | 78.2% | 78.2% | 0.965 | 0.965 |

The baseline and Gemini rows are identical because both runs use the same stored baseline predictions and Gemini scores.
The best epoch was the same in both runs for all three models (xlm-roberta-base 5, BanglaBERT 4, MuRIL 5).

## What we found

- **The two runs agree on the main picture.** xlm-roberta-base has the lowest MAE in both runs, BanglaBERT is a close second,
  and MuRIL is the weakest transformer. xlm-roberta-base and BanglaBERT beat the baseline in both runs.
- **The runs do not give identical numbers.** With the same seed and settings, MAE moved by up to 0.033 (xlm-roberta-base)
  and the share within 1 point by up to 3.7 percentage points. On 400 test reviews, 1 percentage point is 4 reviews,
  so 3.7 points is about 15 reviews.
- **The gap between xlm-roberta-base and BanglaBERT is within this run-to-run difference.** Locally xlm-roberta-base led by
  0.031 MAE; on Colab it leads by only 0.005, and BanglaBERT is slightly ahead on within 1 point and within 0.5.
  The two should be treated as roughly equal; "xlm-roberta-base is best" holds on MAE only, in both runs.
- **MuRIL is clearly behind in both runs.** Its small change between runs (MAE 0.821 to 0.807) does not change that.

## Why the numbers differ

A fixed seed does not make training identical across machines. The two runs used different GPUs and library versions,
and training uses mixed precision and GPU operations whose results can change slightly between runs.
These effects are small, but on a 400-review test set they are visible.

## Limits

- Each model was trained once per machine, so there are two runs per model, not an average over many seeds.
  Differences between models smaller than about 0.03 MAE should not be read as real.
- Per-language and per-platform numbers for the Colab run are in `results_colab/transformer_*_results.txt`.

## Files

- `results_colab/model_comparison.csv`: one row per model, Colab run
- `results_colab/transformer_<model>_predictions.csv`: predicted score for each of the 400 test reviews
- `results_colab/transformer_<model>_results.txt`: full numbers, by language, platform and score band

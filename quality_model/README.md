# Review-quality model

Our own model for the review-quality score, trained on the reviews that Gemini scored
(`quality_eval/all_scores_feedback.csv`: 7,322 reviews, each scored twice, label = mean of the two runs).

| Split | Reviews | Used for |
|---|---|---|
| train | 6,922 (full + pilot) | training and choosing settings (5-fold cross-validation) |
| test | 400 (main run) | tested once; never trained on. This is the set the human check was done on. |

## Step 1: baseline (no GPU, no API)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install scikit-learn scipy joblib matplotlib pandas
cd quality_model
python scripts\01_baseline.py
```

It takes a few minutes and writes:

| File | What it is |
|---|---|
| `results/baseline_results.txt` | all numbers: cross-validation, test set, by language, platform and score band |
| `results/baseline_predictions.csv` | the model's score for each of the 400 test reviews |
| `results/fig_baseline.png` | predicted vs Gemini score, and the share within 1 point per model |
| `models/baseline.joblib` | the saved baseline model |

### Results on the 400 test reviews

| Model | MAE | Within 1 point | Rank correlation |
|---|---|---|---|
| Always the average | 1.65 | 27% | – |
| Review length only | 1.25 | 47% | 0.63 |
| TF-IDF characters + ridge | 0.86 | 66% | 0.80 |
| **TF-IDF + length (baseline)** | **0.84** | **66%** | **0.80** |
| Gemini run 1 vs run 2 (yardstick) | 0.23 | 99% | 0.96 |

- The baseline is far better than guessing the average or using length alone, so the score is
  not just "longer is better".
- It ranks reviews well (0.80) but is not yet precise: one third of the reviews are more than
  1 point away from Gemini's score.
- It pulls scores towards the middle: reviews Gemini scored 1 to 3 get about 0.8 too much,
  reviews scored 7.5 and above about 0.8 too little.
- All three languages work; Banglish is best (73% within 1 point), Bangla lowest (59%).

## Step 2: can another classical model do better?

```powershell
python scripts\02_compare_models.py        # about 10 minutes, no GPU
```

Same split. The model is chosen by cross-validation on the training reviews, not on the test set.

| Model | Test MAE | Test within 1 point | Rank correlation |
|---|---|---|---|
| Ridge (step-1 baseline) | 0.84 | 66% | 0.80 |
| Ridge + signal features (digits, time words, "but", "because", ...) | 0.85 | 67% | 0.81 |
| Linear SVR | 0.87 | 68% | 0.79 |
| Logistic regression over score levels | 0.85 | 68% | 0.77 |
| Gradient-boosted trees (SVD features) | 0.94 | 60% | 0.77 |
| Blend of ridge, SVR and trees | 0.86 | 66% | 0.81 |
| Blend + straight-line correction | 0.84 | 68% | 0.81 |

All of them land in the same place: MAE about 0.85 and 66 to 68% within 1 point. Extra features,
other learners, blending and a correction for the pull towards the middle each move the result
by a point or two at most, which is within the noise of a 400-review test set. Models that only
see which characters and words occur have reached their limit here; what separates a 3 from a 6 is
what the review says, and that needs a model that reads the text in context.

Next: fine-tune a multilingual transformer (XLM-R, BanglaBERT) on the same split and compare.

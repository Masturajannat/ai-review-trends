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

## Step 3: fine-tune a transformer (needs a GPU)

`scripts/03_train_transformer.py` fine-tunes a pretrained multilingual model on the same split
(the training reviews are divided 90/10 into train and validation; the best epoch on validation is
kept; the main 400 are tested once at the end).

**On Google Colab (free GPU, no installation):** open
[`train_transformer_colab.ipynb`](https://colab.research.google.com/github/Masturajannat/ai-review-trends/blob/Mastura/quality_model/train_transformer_colab.ipynb),
choose **Runtime > Change runtime type > T4 GPU**, then **Runtime > Run all**. It trains
XLM-RoBERTa, MuRIL and BanglaBERT (about 10 minutes each), shows them side by side with the
baseline, and downloads `transformer_results.zip`. Unzip that into `quality_model/results`,
then commit and push.

**On a laptop with an NVIDIA GPU:**

```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cu121
python -m pip install transformers sentencepiece scipy pandas
cd quality_model
python scripts\03_train_transformer.py --model xlm-roberta-base            # add --batch 8 if the GPU runs out of memory
python scripts\03_train_transformer.py --model google/muril-base-cased
python scripts\03_train_transformer.py --model csebuetnlp/banglabert
```

`python scripts\03_train_transformer.py --test-run` checks the whole pipeline in a minute with a
tiny untrained model (no GPU, no download; its numbers mean nothing).

The fine-tuned models are saved under `models/<name>/` (about 1 GB each) and are not committed.
Results of each run go to `results/transformer_<name>_results.txt` and `results/model_comparison.csv`.

## Step 4: "Read More" strip and head+tail (19 Nov 2026)

Two follow-up runs on xlm-roberta-base, from the Rokomari investigation. Neither improved the
model clearly; the plain stripped model (`RUN_TAG=noreadmore`) is the one to use. Exact commands,
code changes, a comparison table and the decision are in [`noreadmore_headtail.md`](noreadmore_headtail.md).

## Step 5: finishing the model (from 19 Nov 2026)

What the runs so far show (`comparison.md`, `rokomari_check/rokomari.md`, `noreadmore_headtail.md`):
xlm-roberta-base is the best model so far (test MAE 0.65 to 0.68, 75 to 78% within 1 point,
rank correlation 0.86 to 0.87), BanglaBERT is level with it, and the same model trained twice
differs by up to 0.03 MAE. The chosen setting is "Read More" stripped, first 256 tokens.

Two things are still open before the numbers are final:

1. **Is the result stable?** Every model was trained with one seed. Train xlm-roberta-base with
   two more seeds and report the mean and spread; averaging the seeds' predictions may also help a little.
2. **Does a bigger model help?** `xlm-roberta-large` (three times bigger) is the most likely real
   improvement. It needs about 12 GB of GPU memory, so it runs on Colab, not on an 8 GB laptop.

New options in `03_train_transformer.py`: `--grad-accum N` (add up N batches per update),
`--grad-ckpt` (gradient checkpointing, much less memory), `--warmup`. A seed other than 299 also
changes the train/validation split and writes its own files (`..._seed1_...`), so runs do not
overwrite each other. `05_seeds.py` summarises the seeds of a model.

**Laptop GPU (seeds of the base model, about 7 minutes each):**

```powershell
$env:RUN_TAG = "noreadmore"
python scripts\03_train_transformer.py --model xlm-roberta-base --seed 1 --no-save
python scripts\03_train_transformer.py --model xlm-roberta-base --seed 2 --no-save
python scripts\05_seeds.py --model xlm-roberta-base
```

**Colab (xlm-roberta-large, about 1 hour on a T4):** open
[`train_transformer_colab.ipynb`](https://colab.research.google.com/github/Masturajannat/ai-review-trends/blob/Mastura/quality_model/train_transformer_colab.ipynb)
and run part A. The command it runs:

```
python scripts/03_train_transformer.py --model xlm-roberta-large --lr 1e-5 --batch 8 --grad-accum 2 --grad-ckpt --warmup 0.1
```

**Then decide:** if large beats base by clearly more than the seed spread, use large (and train it
with 2 more seeds if time allows); otherwise keep base. Report the mean and spread over seeds,
the per-platform numbers (Rokomari is the weakest), and the Gemini yardstick.


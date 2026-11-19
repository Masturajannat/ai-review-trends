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

## Step 5: finishing the model (plan from 19 Nov 2026)

Where we are (`comparison.md`, `rokomari_check/rokomari.md`, `noreadmore_headtail.md`):
xlm-roberta-base with "Read More" stripped is the best model so far (test MAE 0.67, 77.5% within
1 point, rank correlation 0.86), BanglaBERT is level with it, and the same run repeated differs by
up to 0.03 MAE. Rokomari is the weak platform (MAE 0.82 against 0.55 to 0.63); its worst misses are
short texts the model cannot place (thanks messages, lyrics, excerpts, generic praise).

Three open questions, answered with as few GPU runs as possible. All runs use `RUN_TAG=noreadmore`.

### Round 1 (laptop GPU, Tazrian, about 40 minutes): does the product name help?

Gemini saw the product name when it scored each review; the model so far sees only the review.
`--with-product` gives the model `(product name, review)`, and hides the name in 30% of training
examples so it still works when a user leaves the name empty (the result file also reports that case).
Five runs of about 7 minutes:

```powershell
$env:RUN_TAG = "noreadmore"
python scripts\03_train_transformer.py --model xlm-roberta-base --seed 1 --no-save
python scripts\03_train_transformer.py --model xlm-roberta-base --seed 2 --no-save
python scripts\03_train_transformer.py --model xlm-roberta-base --with-product
python scripts\03_train_transformer.py --model xlm-roberta-base --with-product --seed 1 --no-save
python scripts\03_train_transformer.py --model xlm-roberta-base --with-product --seed 2 --no-save
python scripts\05_seeds.py --model xlm-roberta-base --model xlm-roberta-base_product
```

(Seed 299 of the plain model already exists in `results_noreadmore/`.)

**Decision:** keep the product name if its mean MAE over the 3 seeds is lower than the plain model's
by more than the larger of the two spreads, and its Rokomari MAE is lower too. Also check the
"product name empty" line: it must not be worse than the plain model, or the app would suffer
when users leave the name out.

Optional, only if time is left: `--rokomari-weight 2` (Rokomari counted twice in the loss), one seed,
added to whichever variant won.

### Round 2 (Colab T4, Mastura, about 1 hour): does the large model help?

`train_transformer_colab.ipynb`, part A: A2 if round 1 kept the product name, otherwise A1.

**Decision:** large wins if its MAE is lower than the base model's 3-seed mean by more than twice the
base spread. If it wins and time allows, run 1 or 2 more seeds of large (part B, about 1 hour each,
can be on different days). If it does not win, the final model is the base model from round 1.

### Round 3: the final model

- Report: mean and spread over seeds, overall and by platform and language (`05_seeds.py` output),
  next to the baseline and the Gemini yardstick, and say why Rokomari is the hardest platform.
- Keep the saved model of seed 299 of the winner (`models_noreadmore/<name>/`) and share it through
  Google Drive (about 1 GB for base, 2 GB for large); it is too large for git.
- The app (`review_coach`) then gets the trained model as its score judge.

### Options in `03_train_transformer.py`

| Option | What it does |
|---|---|
| `--seed N` | other random start and train/validation split; seeds other than 299 write their own files (`..._seedN_...`) |
| `--with-product` | product name given with the review; `--product-dropout` (default 0.3) hides it in that share of training examples |
| `--rokomari-weight W` | Rokomari training reviews count W times in the loss |
| `--grad-accum N`, `--grad-ckpt`, `--warmup` | for xlm-roberta-large on a 16 GB GPU |
| `--no-save` | do not save the model (use for extra seeds) |

`05_seeds.py --model <name>` summarises the seeds of one variant (`xlm-roberta-base`,
`xlm-roberta-base_product`, `xlm-roberta-large`, ...): each seed, the mean and spread, and the
average of the seeds' predictions.

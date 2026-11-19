# Round 1: seeds and product name (19 Nov 2026)

Question: does giving the model the product name (`--with-product`) improve the score model?
Setup: xlm-roberta-base, `RUN_TAG=noreadmore`, 5 epochs, lr 2e-5, batch 16, 256 tokens, local RTX 5050.
Test set: the 400 main-run reviews, never trained on. Seeds: 299 (original), 1, 2.

## Commands

```powershell
$env:RUN_TAG = "noreadmore"
python scripts\03_train_transformer.py --model xlm-roberta-base --seed 1 --no-save
python scripts\03_train_transformer.py --model xlm-roberta-base --seed 2 --no-save
python scripts\03_train_transformer.py --model xlm-roberta-base --with-product
python scripts\03_train_transformer.py --model xlm-roberta-base --with-product --seed 1 --no-save
python scripts\03_train_transformer.py --model xlm-roberta-base --with-product --seed 2 --no-save
python scripts\05_seeds.py --model xlm-roberta-base --model xlm-roberta-base_product
```

## Results per seed (test MAE)

| Seed | Plain | With product name | Product name left empty |
|---|---|---|---|
| 299 | 0.67 | 0.66 | 0.65 |
| 1 | 0.71 | 0.67 | 0.68 |
| 2 | 0.70 | 0.72 | 0.73 |

## Mean and spread over the 3 seeds

| | Plain | With product name |
|---|---|---|
| MAE | 0.693 ± 0.022 | 0.683 ± 0.032 |
| RMSE | 0.972 ± 0.015 | 0.959 ± 0.024 |
| Within 1 point | 76.2% ± 1.8% | 76.2% ± 2.3% |
| Within 0.5 point | 50.5% ± 2.1% | 51.8% ± 2.6% |
| Rank correlation | 0.856 ± 0.007 | 0.859 ± 0.011 |
| Rokomari MAE (mean of 3 seeds) | about 0.86 | about 0.83 |

Average of the 3 seeds' predictions: MAE 0.67 (plain), 0.66 (with product name).
This is no better than the single seed 299, so a seed ensemble is not worth using.
For comparison: baseline (TF-IDF + ridge) MAE 0.84; Gemini run 1 vs run 2 MAE 0.23.

## Decision

Rule (from the README): keep the product name only if its 3-seed mean MAE is lower than the plain model's
by more than the larger spread, and its Rokomari MAE is lower too.

- MAE gain is 0.010; the larger spread is 0.032. The gain is smaller than the spread, so it is noise
  (seed 2 alone moved the product model by about 0.05).
- Rokomari is lower (about 0.83 against 0.86), but the first condition fails, so the rule fails.
- With the product name empty the model is not worse (mean MAE about 0.69), so the app would not suffer
  if users skip the name. This does not change the decision.

**The product name is not used. The final model stays plain xlm-roberta-base (`models_noreadmore/xlm-roberta-base`).**
Round 2 (xlm-roberta-large on Colab) therefore runs cell A1, without the product name.

## What to report

Plain xlm-roberta-base, mean over 3 seeds: MAE 0.69 ± 0.02, 76% within 1 point, rank correlation 0.86.
Use this instead of the best single seed (0.67).

## Limits

- 3 seeds and 400 test reviews: differences under about 0.03 MAE are not real.
- Rokomari stays the hardest platform in every run (MAE 0.79 to 0.89).
- All models over-predict low-scored reviews (labels 1 to 3 by about +0.4) and under-predict high ones
  (labels 7.5 and above by about -0.6); this did not change with seeds or the product name.
- The product-name model (seed 299) was saved in `models_noreadmore/xlm-roberta-base_product` (not committed, not used).
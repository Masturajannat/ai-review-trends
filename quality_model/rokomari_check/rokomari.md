# Rokomari: why the review-quality model does worse there

Model: xlm-roberta-base, trained to predict the Gemini review-quality score (1 to 10).
Test set: the 400 main-run reviews (132 Daraz, 130 Rokomari, 138 Shajgoj), never trained on.
Lower MAE is better. Higher rank correlation (Spearman) is better.

## 1. What we saw first

Rokomari is the hardest platform in every run we have. The 256-token runs are the original local run and the Colab run, with the same code, data and seed.

| xlm-roberta-base, test set | Daraz | Rokomari | Shajgoj |
|---|---|---|---|
| MAE, local (256 tokens) | 0.55 | **0.78** | 0.62 |
| MAE, Colab (256 tokens) | 0.57 | **0.82** | 0.66 |
| Rank corr., local | 0.90 | **0.74** | 0.91 |
| Rank corr., Colab | 0.89 | **0.71** | 0.91 |

- BanglaBERT and MuRIL also have Rokomari as their hardest platform (`local_run.md`).
- The TF-IDF + ridge baseline is also weakest there on rank correlation (0.67, against 0.83 and 0.86).
- On Rokomari the transformer barely beats the baseline: Colab 0.822 against the baseline's 0.828, local 0.782 against 0.828. On Daraz and Shajgoj it improves on the baseline by 0.2 to 0.3.

So this is not a glitch in one run or one model.

## 2. Things we ruled out first

- **The labels are not noisier on Rokomari.** Gemini run 1 vs run 2 differs by 0.22 MAE on Rokomari, against 0.27 on Daraz and 0.18 on Shajgoj. Within 1 point: 98%, 100% and 99%.
- **Short reviews are fine.** For reviews of 20 words or fewer (68 of the 130 Rokomari test reviews), Rokomari error is 0.56 (local) and 0.58 (Colab), the same as the other platforms (0.53 and 0.56).
- **The problem is in longer reviews.** Test MAE by length, Rokomari against the other two platforms:

| Words | Rokomari local | Others local | Rokomari Colab | Others Colab |
|---|---|---|---|---|
| 0 to 20 | 0.56 | 0.53 | 0.58 | 0.56 |
| 20 to 60 | 0.89 | 0.62 | 0.90 | 0.62 |
| 60 to 120 (10 Rokomari reviews) | 1.16 | 0.74 | 1.52 | 0.83 |
| 120 and over (10 Rokomari reviews) | 1.44 | 0.59 | 1.43 | 0.89 |

- **Narrow label spread explains only part of the rank-correlation drop.** Rokomari test labels have SD 1.56, against 1.79 (Daraz) and 2.29 (Shajgoj). That lowers rank correlation mechanically but does not explain the MAE gap.

## 3. Hypothesis: long reviews are cut at 256 tokens

`03_train_transformer.py` keeps only the first 256 tokens of each review. Rokomari reviews are the longest, and many have a plot summary first and the reader's own reaction at the end, so the model might never see the part Gemini scored.

### Check

`rokomari_check/01_token_lengths.py` counts tokens with the xlm-roberta tokenizer, without truncation, and compares test error on reviews kept whole against reviews that would be cut.

| Share of reviews over 256 tokens | Daraz | Rokomari | Shajgoj |
|---|---|---|---|
| Training reviews | 0.0% (n=3,339) | **20.1%** (n=1,528) | 0.4% (n=2,055) |
| Test reviews | 1.5% (n=132) | **7.7%** (n=130) | 0.7% (n=138) |

Truncation is almost only a Rokomari issue: about 300 of the 1,528 Rokomari training reviews lose their ending.

| Rokomari test MAE, xlm-roberta | Kept whole (n=120) | Cut at 256 (n=10) |
|---|---|---|
| Local | 0.73 | **1.44** |
| Colab | 0.77 | **1.43** |

Cut reviews have about twice the error, in both runs.

### How much does truncation explain?

Without the 10 cut reviews, Rokomari MAE falls by about 0.05 (0.78 to 0.73 local, 0.82 to 0.77 Colab). The gap to Daraz goes from about 0.23 to about 0.18, so **truncation explains roughly a fifth of the gap**. Whole-review Rokomari MAE (0.73 and 0.77) is still above Daraz (0.55) and Shajgoj (0.62).

### The 15 worst Rokomari misses (local run)

Saved in `rokomari_check/results/rokomari_worst_local.csv`.

- **3 of 15 are cut reviews** (516, 686 and 1,175 tokens). The 330-word thriller review (label 8, predicted 5.0) has a plot blurb first and the personal reaction after a "পাঠপ্রতিক্রিয়া" heading near the end, which the model probably never saw. The 255-word Himu review (label 3, predicted 7.0) opens like a normal review and drifts into unrelated personal talk later.
- **12 of 15 are short** (83 words or fewer), so truncation cannot explain them. The model over-predicts things that sound like a review but say little: a "thanks Rokomari, received the book" message (label 2.5, predicted 4.9), a song lyric (1.0 and 2.65), a pasted excerpt (2.0 and 3.7), generic praise (3.0 and 5.05). It under-predicts short, emotional, book-specific reviews, such as "I literally cried" (7.0 and 5.2).
- **"Read More" appears in the text of 5 of the 15** reviews. It is probably a scraping leftover.

### Over-marking is general, but worst on Rokomari

Mean error (predicted minus label) on test reviews scored 1 to 3, xlm-roberta:

| Platform | Local | Colab | Reviews over-marked by 1.5 or more (local / Colab) |
|---|---|---|---|
| Daraz | +0.32 | +0.23 | 4 of 44 / 3 of 44 |
| Rokomari | **+0.68** | **+0.65** | **8 of 51 / 8 of 51** |
| Shajgoj | +0.35 | +0.46 | 5 of 54 / 6 of 54 |

All platforms are pulled toward the middle (low scores too high, high scores too low), but Rokomari is about twice as bad on low-scored reviews. Rokomari has only 5 test reviews scored 7.5 or higher, so its high band is too thin to conclude anything.

## 4. What we changed and ran again

**Change:** `--max-len 512` instead of 256, with `--batch 8` (VRAM was nearly full at batch 16) and `--no-save`.

```
python scripts\03_train_transformer.py --model xlm-roberta-base --max-len 512 --batch 8 --no-save
```

**Why:** to see whether showing the model more of each long review improves Rokomari, since about 20% of its training reviews were cut.

**Kept the same:** data (6,230 train, 692 validation, 400 test), 5 epochs, learning rate 2e-5, seed 299, the same laptop (RTX 5050, 8 GB). Training took 733 s, against 419 s at 256 tokens. Output is in `rokomari_check/len512/`.

## 5. What the 512 run showed

| xlm-roberta-base | 256, local | 256, Colab | 512, local |
|---|---|---|---|
| Test MAE | 0.650 | 0.683 | 0.675 |
| Within 1 point | 78.2% | 74.5% | 76.2% |
| Rank corr. | 0.870 | 0.858 | 0.863 |
| Best validation MAE | 0.56 | 0.57 | 0.56 |
| Rokomari MAE | 0.78 | 0.82 | 0.78 |
| Rokomari rank corr. | 0.74 | 0.71 | 0.73 |
| Daraz MAE | 0.55 | 0.57 | 0.57 |
| Shajgoj MAE | 0.62 | 0.66 | 0.68 |

The 512 run lands between the two 256 runs on every line. Rokomari did not improve (0.78 at 256 locally, 0.78 at 512). Daraz and Shajgoj moved by 0.02 to 0.06 in both directions, which is the same size as the difference between the local and Colab runs.

## 6. Conclusion

- **Rokomari is the hardest platform for every model and run**, and the gap is not caused by noisier labels.
- **Truncation at 256 tokens is real but minor.** It affects about 20% of Rokomari training reviews, and reviews cut at 256 have about twice the error, but removing them explains only about a fifth of the gap to Daraz.
- **Raising the limit to 512 did not help.** Rokomari MAE stayed at 0.78 and validation MAE did not change, so we keep 256 as the setting.
- **Most of the remaining gap looks like the task, not the setup.** The worst misses are mostly short reviews that sound positive but say little, which the model scores too high, and short emotional, book-specific reviews, which it scores too low. This is our reading of the examples; we have not tested it.
- **For reporting:** give per-platform numbers rather than only the overall MAE, and state that Rokomari is the weakest platform and why.

## 7. Limits

- One seed per setting and 400 test reviews. Differences under about 0.03 MAE should not be read as real.
- Only 10 cut Rokomari test reviews and 5 Rokomari reviews scored 7.5 or higher, so the length and high-band numbers are noisy.
- We have not checked whether the 10 cut reviews improved in the 512 run. The predictions are in `rokomari_check/len512/`, so this can be done.
- 512 is the maximum for xlm-roberta, and reviews of 686 and 1,175 tokens would still be cut.
- The token counts use the xlm-roberta tokenizer, so BanglaBERT and MuRIL may cut slightly differently.
- The "Read More" count is from the 15 worst misses only. We have not measured how often it appears overall.

## 8. Possible next steps (not done)

- Keep the start and the end of long reviews (for example the first 128 and last 384 tokens), since the personal reaction is often at the end.
- Count how often "Read More" appears in `quality_eval/all_scores_feedback.csv`, and decide whether to strip it.
- Read the over-marked low-scored Rokomari reviews by hand next to Gemini's reasons, to check whether any labels are arguable.
- Repeat the runs with more seeds before claiming any difference smaller than 0.03 MAE.

## Files

- `rokomari_check/01_token_lengths.py`: the token-length check
- `rokomari_check/results/token_lengths.txt`: its output
- `rokomari_check/results/rokomari_worst_local.csv`: the 15 worst Rokomari misses, local run
- `rokomari_check/len512/`: results and predictions of the 512-token run

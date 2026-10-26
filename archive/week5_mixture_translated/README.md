# Corpus-level estimation of AI-generated review text

This module estimates the share of AI-generated text in a collection of e-commerce reviews without
classifying individual reviews. It adapts the distributional maximum-likelihood framework of
Liang et al. (2024) to Bangladeshi e-commerce reviews from Daraz, Rokomari and Shajgoj, and
tests whether the estimator recovers known AI shares before it is applied to post-ChatGPT data.

## Method

A collection of sentences is modelled as a mixture of a human-written distribution *P* and an
AI-generated distribution *Q*:

    sentence ~ (1 − α) · P + α · Q

Each sentence is represented as the set of adjectives and adverbs it contains (part-of-speech tags
from spaCy `en_core_web_sm`). Restricting the vocabulary in this way follows the paper's
adjective-based setting and removes product and topic words that vary between periods. For each
word *t*, *p_t* and *q_t* are the fractions of human and AI sentences that contain it. The
likelihood of a sentence under *P* is the product of *p_t* for words present and (1 − *p_t*) for
words absent, and likewise for *Q*. The AI share α is the value that maximises the log-likelihood
of the collection, found on a grid of 1,001 points. Confidence intervals are obtained by
bootstrapping reviews.

*P* and *Q* are fitted separately for each platform, as the paper does for each venue. A pooled
model assigned roughly 30% "AI" to pre-2022 Daraz reviews because its human distribution was
dominated by long Rokomari book reviews.

## Data

| File | Contents |
|---|---|
| `data/source_reviews_clean.csv` | All cleaned reviews (2,524) with English text |
| `data/human_reference.csv` | 402 pre-2022 reviews used to fit *P* |
| `data/human_validation.csv` | 399 held-out pre-2022 reviews used for validation |
| `data/ai_reference.csv` | 402 AI reviews, one per `human_reference` review, used to fit *Q* |
| `data/ai_validation.csv` | 399 AI reviews, one per `human_validation` review, used for validation |
| `data/pilot_*.csv` | 100 + 100 pilot subset used to develop the pipeline |

Reviews written before 2022 predate ChatGPT and are treated as human-written. The reference and
validation halves are split evenly within each platform and language group.

### AI-generated reviews

AI reviews were generated with Google Gemini (`gemini-3.5-flash-lite`). The model was used because
of API availability; each row records its `provider` and `model`. Two prompt types were used in
equal proportion:

- **Rewrite**: the human review is rewritten with the same meaning.
- **New**: a new review is written from the product name and rating, with the human review given
  only as a style sample.

Each prompt specifies the language and script of the source review (Bengali script, Banglish or
English) and the target length. Responses in the wrong script are regenerated. Bengali and
Banglish AI reviews are translated into English with the same translation pipeline used for the
real reviews (`translate_reviews_to_english.py`), so that both corpora share translation artefacts.

## Pipeline

Run all commands from the repository root.

| Step | Script | Purpose |
|---|---|---|
| 0 | `scripts/00_make_source.py` | Copy the cleaned review file into `data/` |
| 1 | `scripts/01_split.py` | Split pre-2022 reviews into reference and validation halves |
| 2 | `scripts/02_pilot.py` | Draw the 100 + 100 pilot subset |
| 3 | `scripts/03_generate_ai.py` | Generate one AI review per human review |
| 4 | `scripts/04_translate_ai.py` | Translate Bengali and Banglish AI reviews into English |
| 5 | `scripts/05_validate.py` | Validate the estimator and apply it to the real data |

```powershell
pip install pandas numpy matplotlib requests translators deep-translator spacy
python -m spacy download en_core_web_sm

$env:GEMINI_API_KEY = "<key>"                                   # never commit API keys
python mixture_estimation\scripts\03_generate_ai.py --full      # resumable; stops at the daily quota
python mixture_estimation\scripts\04_translate_ai.py --full
python mixture_estimation\scripts\05_validate.py --full
```

Options for `05_validate.py`: `--words adjadv|adj|all` (default `adjadv`),
`--fit per-platform|pooled` (default `per-platform`). Omitting `--full` runs the pilot subset.
`03_generate_ai.py --provider openai` uses the OpenAI API instead of Gemini.

## Validation

Held-out pre-2022 reviews were mixed with held-out AI reviews at known shares. A human review and
the AI review generated from it never appear in the same mixture. Each platform was tested with
300 random mixtures of 100 reviews. Because α is a share of sentences, the true value is the share
of AI sentences in each mixture.

| Platform | True share | Mean estimate | 5th–95th percentile | Bias (points) |
|---|---|---|---|---|
| Daraz | 0.0% | 7.9% | 0.0–16.9% | +7.9 |
| Daraz | 10.9% | 19.9% | 8.1–31.4% | +9.0 |
| Daraz | 21.1% | 29.4% | 17.2–41.7% | +8.3 |
| Rokomari | 0.0% | 2.5% | 0.0–7.1% | +2.5 |
| Rokomari | 9.1% | 10.8% | 2.4–20.8% | +1.7 |
| Rokomari | 18.2% | 19.7% | 9.8–33.3% | +1.5 |
| Shajgoj | 0.0% | 4.2% | 0.0–13.1% | +4.2 |
| Shajgoj | 9.6% | 13.2% | 0.0–27.7% | +3.6 |
| Shajgoj | 18.8% | 24.0% | 5.6–41.8% | +5.2 |

The estimator tracks the true share on all three platforms. Rokomari is within about 2 points,
which is comparable to the error reported by Liang et al.; Shajgoj and Daraz overestimate by about
4 and 8 points. The spread across mixtures is wide (about ±10 points) because each platform has
only 120–150 human reviews to fit *P*. The paper fitted its distributions on tens of thousands of
reviews.

Development history: the pilot (100 AI reviews, all words, pooled fit) estimated 13.0% for a 10%
mixture; the full AI set with all words and a pooled fit estimated 17.9%. Restricting the
vocabulary to adjectives and adverbs and fitting each platform separately produced the results
above.

## Results on the real data

Estimates are restricted to products that also have pre-2022 reviews. The pre-2022 group excludes
the reviews used to fit *P*.

| Platform | Pre-2022 | 2022 | Post-2022 |
|---|---|---|---|
| Daraz | 8.1% (0.0–29.3) | 0.0% (0.0–23.4) | 15.9% (5.3–27.7) |
| Rokomari | 2.3% (0.0–14.7) | 68.1% (34.6–100) | 31.8% (11.5–65.7) |
| Shajgoj | 1.9% (0.0–31.3) | 0.0% (0.0–24.4) | 9.1% (0.0–42.9) |

Values are the estimated share of AI sentences with 95% bootstrap intervals.

These estimates should not be read as AI prevalence. ChatGPT was released on 30 November 2022,
so reviews dated 2022 are almost entirely pre-ChatGPT and serve as a negative control: their
estimate should match the pre-2022 level. Rokomari fails this check (68.1% in 2022 against 2.3%
before 2022). The median Rokomari review is 14 words before 2022 but 6 words in 2022 and 9.5 words
after 2022, so the estimator appears to respond to the shift towards shorter reviews rather than
to AI-generated text. Daraz and Shajgoj show no change that is distinguishable from zero.

## Limitations

- The human distribution is fitted on about 130 reviews per platform, which makes estimates noisy.
- Changes in review length and product mix between periods are confounded with AI use.
- *Q* is fitted on Gemini output. Post-2022 AI-written reviews are more likely to come from
  ChatGPT, whose word use differs, so the estimator may under-detect them.
- Bengali and Banglish reviews are analysed through machine translation.

## Next steps

1. Compare periods within matched length bands to remove the length effect.
2. Collect more pre-2022 reviews, particularly short reviews and Daraz reviews, to improve *P*.
3. Test cross-model robustness by mixing ChatGPT-generated reviews into the validation set while
   keeping *Q* fitted on Gemini output.

## Outputs

Results are written to `results/<full|pilot>_<words>_<fit>/`:

- `validation_summary.csv`, `validation_runs_<platform>.csv`, `validation_chart.png`: validation
- `real_data_estimates.csv`: estimates for all reviews and for same-product reviews
- `real_data_change.csv`: change relative to pre-2022 within each platform, with bootstrap intervals

`results/validation_*.csv` and `results/real_data_estimates.csv` contain the earlier pilot run
(all words, pooled fit).

## Reference

Liang, W., Izzo, Z., Zhang, Y., Lepp, H., Cao, H., Zhao, X., Chen, L., Ye, H., Liu, S., Huang, Z.,
McFarland, D. A., & Zou, J. Y. (2024). *Monitoring AI-Modified Content at Scale: A Case Study on
the Impact of ChatGPT on AI Conference Peer Reviews.* Proceedings of the 41st International
Conference on Machine Learning. [arXiv:2403.07183](https://arxiv.org/abs/2403.07183)

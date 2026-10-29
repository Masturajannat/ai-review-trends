# Trend analysis on original-language reviews

This folder contains the current analysis pipeline. It examines whether AI-style language in
e-commerce reviews increased after the release of ChatGPT (30 November 2022), following the
word-frequency approach of Liang et al. (2024). Reviews are analysed in their original language
(Bengali script, Banglish or English) without translation, and each platform is analysed separately.

## Phase 1: dataset

```powershell
python trend_analysis\scripts\01_build_dataset.py
python trend_analysis\scripts\02_build_ai_reference.py
```

### `01_build_dataset.py`

Reads `combined_reviews.csv` (all scraped reviews) and produces the analysis dataset.

| Step | Rule |
|---|---|
| Cleaning | Emojis, text emoticons (`:)`, `<3`, `xD`) and other symbols removed; HTML entities decoded |
| Word count | Whitespace tokens of the cleaned text that contain at least one letter |
| Language | `bangla`: at least 80% of letters in Bengali script. `mixed`: 20–80%. Latin-script text is `banglish` if it contains two or more common Banglish words (or one, with at most two common English words), otherwise `english`. The Banglish word list includes every spelling variant in `banglish_variants.csv` |
| Date | Parsed from the review date. Daraz shows reviews newer than about a month as "x weeks ago"; these are converted using the scrape date of the file the review came from (`sources.csv`) and marked `date_is_approx` |
| Period | `period`: `pre_chatgpt` (before 30 Nov 2022) or `post_chatgpt` (30 Nov 2022 onwards). `period_detail` splits the pre-ChatGPT period into `pre_2022` and `jan_nov_2022`, used for a placebo check. Calendar half-years in `half_year` |
| Exclusion | In order: duplicate review ID; no text; exact repeat of a review on the same platform (earliest kept); restock or availability request of 15 words or fewer; **5 words or fewer** |

`keep_10` and `keep_25` mark reviews longer than 10 and 25 words, for sensitivity checks.

Reviews come from two collection rounds, listed in `sources.csv` and recorded in the `batch` and
`scrape_date` columns:

| Round | Files | Scraped | Kept |
|---|---|---|---|
| 1 (16 Oct 2026) | Daraz, Rokomari, Shajgoj | 2,899 | 1,740 |
| 2 (29 Oct 2026) | Rokomari, 12 additional books | 2,250 | 1,339 |
| 2 (29 Oct 2026) | Daraz, 14 household products with many 2019–2021 reviews | 6,089 | 2,522 |

Of 11,238 scraped reviews, 5,601 are kept (3,165 too short, 2,316 exact repeats, 100 stock requests,
56 without text). Most exact repeats are one-word reviews such as "Good" or অসাধারণ. Rokomari's
"Read More" link text, captured at the end of truncated reviews, is removed during cleaning.

**Kept reviews by platform, language and period**

| Platform | Language | Pre-ChatGPT | of which pre-2022 | of which Jan–Nov 2022 | Post-ChatGPT |
|---|---|---|---|---|---|
| Daraz | Bangla | 941 | 766 | 175 | 598 |
| Daraz | Banglish | 397 | 324 | 73 | 254 |
| Daraz | English | 904 | 793 | 111 | 377 |
| Rokomari | Bangla | 1,003 | 884 | 119 | 342 |
| Rokomari | English | 179 | 144 | 35 | 68 |
| Shajgoj | Banglish | 95 | 75 | 20 | 62 |
| Shajgoj | English | 118 | 89 | 29 | 25 |
| Shajgoj | Bangla | 29 | 21 | 8 | 32 |

Smaller groups (Rokomari Banglish, mixed-script reviews) are in `results/dataset_counts.csv`.

The earlier pipeline labelled many English reviews as Banglish and translated them. With the
corrected language tags, English is a substantial group on Daraz and Shajgoj.

Daraz round 1 covers gadgets and accessories, most reviewed after ChatGPT; Daraz round 2 covers
household products (detergent, hand wash, disinfectant, masks, prayer mats), most reviewed in
2019–2021. The two rounds therefore contribute unequally to the two periods, which matters for the
Daraz results (see Phase 2).

### `02_build_ai_reference.py`

Collects 949 Gemini-generated reviews in their original language from the archived Week 4 and
Week 5 work and cleans and tags them with the same functions as the real reviews. 742 are longer
than five words. English is under-represented (88 reviews) because the earlier generator inherited
the incorrect language labels; additional English AI reviews are needed before the English analysis.

### `textutil.py`

Shared cleaning, word-counting, language-tagging and Banglish spelling-normalisation functions, used
by all scripts so that real and AI-generated reviews are processed identically.

## Phase 2: marker-word trend

```powershell
python trend_analysis\scripts\03_marker_words.py
python trend_analysis\scripts\04_trends.py
```

### Design

Following Liang et al. (2024), the analysis tracks words that AI-generated reviews use far more often
than human reviews, instead of classifying individual reviews.

1. **Periods and split.** Reviews are compared before and after ChatGPT's release on
   30 November 2022. Pre-2022 reviews are divided into a discovery half and a held-out half (the
   split used in the earlier work). Marker words are chosen on the discovery half only. The
   pre-ChatGPT baseline consists of the held-out pre-2022 reviews and all Jan–Nov 2022 reviews;
   choosing words and measuring the baseline on the same reviews would make the baseline
   artificially low.
2. **Ranking (`03_marker_words.py`).** For each language, words are ranked by the log-odds ratio
   with an informative Dirichlet prior (Monroe, Colaresi & Quinn, 2008) between AI reviews and
   pre-2022 human reviews, using word occurrence per review. Candidate lists are in
   `results/marker_candidates_<language>.csv`.
3. **Curation (`markers.csv`).** Following the paper's use of adjectives, the final list keeps
   evaluative adjectives and adverbs (`evaluative`, e.g. চমৎকার "excellent", সত্যিই "truly",
   *truly*, *highly*, *amazing*) and, separately, formal function words that replace colloquial
   forms in AI text (`formal`, e.g. এটি for এটা, একটি for একটা, এবং for আর). Product, shopping and topic
   words were excluded, including words introduced by the generation prompt ("bought online": অনলাইন,
   ডেলিভারি, অর্ডার, হার্ডকভার), book titles and author names. Curation used only the discovery half.
4. **Control words.** Frequent words with no AI/human difference (|z| < 0.5) that occur in at least
   three products, so they do not track the product mix (`results/control_words.csv`).
5. **Trend (`04_trends.py`).** For each platform and language with at least 30 reviews in both
   periods, the share of reviews containing an evaluative marker and the number of markers per
   100 words are compared before and after ChatGPT, with 95% bootstrap intervals, and plotted by
   half-year. Robustness: reviews over 10 and over 25 words; products that also have pre-ChatGPT
   reviews; a baseline of pre-2022 reviews only.
6. **Placebo check.** Jan–Nov 2022 is compared with pre-2022. Both are before ChatGPT, so no change
   is expected; a clear difference would point to drift unrelated to AI.

### Marker check on held-out data

Share of held-out reviews containing at least one word of each group:

| Language | Group | AI reviews | Human pre-2022 reviews |
|---|---|---|---|
| Bangla | evaluative (20 words) | 85.7% | 28.7% |
| Bangla | formal (4 words) | 65.5% | 36.6% |
| Bangla | control (15 words) | 81.5% | 80.9% |
| Banglish | evaluative (7 words) | 72.8% | 13.4% |
| Banglish | control (10 words) | 79.0% | 56.2% |
| English | evaluative (6 words) | 54.5% | 6.6% |
| English | control (15 words) | 90.9% | 87.6% |

Held-out human reviews: 1,549 Bangla, 372 Banglish, 929 English. The markers separate AI from human
text on reviews they were not selected on; the control words do not (Bangla, English) or only
weakly (Banglish). Rokomari book reviews use evaluative words such as অসাধারণ more often than product
reviews, so each platform's own baseline is used in the trend. The English list rests on 44 AI
reviews and is the least reliable.

### Results

Six series meet the size requirement. Share of reviews containing an evaluative marker word, with
95% bootstrap intervals:

| Series | Pre-ChatGPT | Post-ChatGPT | Change (points) | Same products only |
|---|---|---|---|---|
| Daraz – Bangla | 11.2% (n = 904) | 16.7% (n = 598) | **+5.5 [+2.2, +9.4]** | +1.4 [−2.6, +5.0] |
| Daraz – Banglish | 13.3% (n = 376) | 9.4% (n = 254) | −3.8 [−9.0, +1.3] | −2.0 [−8.4, +4.9] |
| Daraz – English | 6.3% (n = 871) | 11.9% (n = 377) | **+5.6 [+2.1, +9.2]** | +2.5 [−1.8, +7.2] |
| Rokomari – Bangla | 42.5% (n = 927) | 39.5% (n = 342) | −3.0 [−9.2, +3.2] | −3.1 [−9.3, +2.9] |
| Rokomari – English | 9.9% (n = 161) | 16.2% (n = 68) | +6.2 [−3.8, +16.5] | +5.4 [−4.8, +15.0] |
| Shajgoj – Banglish | 19.3% (n = 57) | 12.9% (n = 62) | −8.0 [−20.4, +4.4] | −7.8 [−21.5, +4.5] |

**Daraz Bangla and Daraz English show a clear increase overall, but not within the same products.**
The pooled increase comes from the change in product mix between the periods:

| Daraz | Round 1 (gadgets): pre → post | Round 2 (household): pre → post |
|---|---|---|
| Bangla | 14.5% (69) → 20.2% (372) | 10.9% (835) → 11.1% (226) |
| Banglish | 17.9% (39) → 8.2% (183) | 12.8% (337) → 12.7% (71) |
| English | 14.3% (42) → 14.7% (211) | 5.9% (829) → 8.4% (166) |

The pre-ChatGPT period is now mostly household reviews, which use few evaluative words; the
post-ChatGPT period is mostly gadget reviews, which use more. Within each round the rates barely
move. Products with at least 10 reviews in both periods give an average within-product change of
+3.1 points (Bangla, 7 products) and +1.9 points (English, 7 products). Control words also rise in
the pooled Daraz Bangla comparison (+8.1 points), which a change in AI use would not cause. The
pooled Daraz increase is therefore not evidence of AI use; the same-product comparison is the
appropriate one for Daraz.

- **Placebo.** Jan–Nov 2022 does not differ from pre-2022 on Daraz (Bangla +2.4, Banglish +3.9,
  English 0.0 points; all intervals include zero), Rokomari English or Shajgoj. Rokomari Bangla
  (45.0% vs 25.2%, −19.8 points) shows that Rokomari reviewing changed before ChatGPT; its
  before/after comparison should be read alongside the half-year trend.
- **Longer reviews.** Among Daraz Bangla reviews over 25 words the share rose by 11.2 points
  [+0.4, +22.0] (124 vs 111 reviews); this subset has the same product-mix problem.
- **Markers per 100 words, Rokomari Bangla.** Rose from 1.6 to 2.6, but control words per 100 words
  rose even more (7.8 to 10.1), already before ChatGPT. Post-ChatGPT Rokomari reviews are shorter,
  which raises all per-100-word rates.
- **Formal words, Rokomari Bangla.** The share containing a formal word (এটি, একটি, এবং …) fell from
  52.0% to 34.5%, against the direction expected from AI use, and also in the placebo comparison.

### Interpretation and limitations

- No series shows an increase in AI-associated words that survives a same-product comparison.
- Daraz pre- and post-ChatGPT reviews come largely from different products. Comparisons across
  rounds must hold the product (or product category) fixed; additional post-ChatGPT reviews of the
  round-2 household products, or pre-ChatGPT reviews of gadgets, would make the Daraz comparison
  balanced.
- Rokomari's review style changed before ChatGPT (placebo), so a constant-baseline comparison is less
  reliable there than the size of its sample suggests.
- Shajgoj and Rokomari English still have small samples (57–161 pre-ChatGPT reviews).
- Marker words were derived from Gemini output; reviews written with ChatGPT may favour other words.
- The English marker list is based on 44 AI reviews.
- Banglish spelling varies widely; this analysis counts spellings as written. The Banglish-specific
  analysis below normalises spelling and supersedes the Banglish rows of this table.

## Phase 3: Banglish and language mix

```powershell
python trend_analysis\scripts\05_banglish.py
python trend_analysis\scripts\06_language_mix.py
```

### Spelling variants (`banglish_variants.csv`)

Banglish has no fixed spelling: "good" appears as *valo* (231 times), *vlo* (57), *bhalo* (20),
*balo* and *vhalo*. The table maps 150 variant spellings onto 51 families and assigns each a canonical
form, the standard Avro Phonetic spelling of the Bangla word. Families are of three types:

| Type | Example | Families |
|---|---|---|
| `spelling` | vlo, valo, balo → *bhalo*; onk, onak → *onek*; akdom → *ekdom*; amr → *amar* | 34 |
| `register` | colloquial hoise, hoice → standard *hoyeche*; paisi → *peyechi*; gese → *geche* | 7 |
| `loanword` | misspelled English words: coyalety → *quality*; prefect → *perfect*; orginal → *original* | 10 |

Candidate groups were generated from consonant skeletons (bh/v, sh/s, ch/s/c merged; vowels
removed) and checked by hand. `textutil.tokens(..., normalize=True)` applies the table.

### Standard-form share (`05_banglish.py`, part A)

For each Banglish review, the share of variant-family words written in their canonical form.
AI-generated Banglish uses standard spellings far more consistently than reviewers do:

| Group | Reviews | Standard-form share |
|---|---|---|
| AI (Gemini) | 314 | 81.4% |
| Human pre-2022, held-out half | 332 | 46.8% |
| Human pre-2022, all | 387 | 48.4% |

Before and after ChatGPT (95% bootstrap interval):

| Platform | Pre-ChatGPT | Post-ChatGPT | Change (points) | Placebo (Jan–Nov 2022 − pre-2022) |
|---|---|---|---|---|
| Daraz | 45.5% (n = 355) | 45.4% (n = 233) | −0.1 [−5.7, +5.5] | −0.3 [−9.1, +9.0] |
| Shajgoj | 58.3% (n = 83) | 53.7% (n = 54) | −4.6 [−17.1, +8.4] | −4.0 [−20.8, +13.5] |

Spelling has not moved towards the AI pattern on either platform.

### Cross-fitted marker words (`05_banglish.py`, part B)

Marker words are counted after spelling normalisation, so *akdom* and *ekdom* count as the same
word. To use every pre-ChatGPT review, the analysis is cross-fitted: markers are chosen on one half
of the pre-2022 reviews and the baseline is measured on the other half, then the halves are swapped
and the two estimates averaged. Markers are selected automatically from a fixed list of evaluative
words (`EVALUATIVE` in the script, defined before the analysis) as those with log-odds z ≥ 1.

| Fold | Markers selected | Held-out AI | Held-out human |
|---|---|---|---|
| A | darun, ekdom, highly, khub, khuboi, recommended, shobcheye | 72.8% | 15.9% |
| B | awesome, darun, ekdom, highly, khub, khubi, osadharon, perfect, recommended, sundor | 76.2% | 26.2% |

Both halves select largely the same words.

| Platform | Pre-ChatGPT | Post-ChatGPT | Change (points) |
|---|---|---|---|
| Daraz | 19.4% (n = 397) | 15.7% (n = 254) | −3.7 [−10.3, +2.9] |
| Shajgoj | 21.7% (n = 95) | 15.3% (n = 62) | −6.4 [−17.9, +5.1] |

Banglish reviews did not become more AI-like after ChatGPT on either platform.

### Language mix (`06_language_mix.py`)

AI assistants write standard Bengali script or English by default. A shift away from Banglish after
ChatGPT would therefore be one possible trace of AI use, although keyboard habits and the reviewer
population also affect it. Change in the share of reviews in each language, post- minus
pre-ChatGPT, for products reviewed in both periods:

| Platform | Bengali script | Banglish | English |
|---|---|---|---|
| Daraz (2,292 → 702 reviews) | +12.5 [+8.2, +16.9] | +0.3 [−2.8, +3.6] | −12.0 [−15.6, −8.1] |
| Rokomari (1,226 → 443) | −5.0 [−9.2, −0.5] | +3.5 [+1.2, +6.1] | +0.1 [−3.9, +3.9] |
| Shajgoj (218 → 124) | +13.9 [+5.1, +23.1] | +13.3 [+2.4, +24.5] | −29.4 [−39.0, −20.0] |

The Banglish share did not fall on any platform; on Shajgoj and Rokomari it rose. English declined on Daraz
and Shajgoj, while Bengali script grew. This pattern does not match a shift towards
AI-produced text, which would favour polished English or Bengali script over Banglish; it is more
consistent with a broader move towards Bengali-language reviewing.

### Limitations

- The Shajgoj Banglish groups are small (95 and 62 reviews).
- The AI reference is Gemini's Banglish, which overuses some words (*khub* in 49% of AI reviews
  against 10% of human ones). Banglish written with ChatGPT may differ.
- The variant table covers frequent words; rarer variants remain unnormalised.

## Phase 4: estimated AI share

```powershell
python trend_analysis\scripts\07_ai_share.py
```

### Method

The marker rates can be turned into an estimate of the share of AI-generated reviews. If a share α
of reviews is AI-generated, the expected share of reviews containing an evaluative marker is
(1 − α)·h + α·a, so

    α = (m − h) / (a − h)

with h the marker rate in pre-ChatGPT human reviews (excluding the discovery half), a the rate in
held-out AI reviews (not used to choose the markers; platform-specific where at least 40 exist,
otherwise all platforms), and m the rate in post-ChatGPT reviews. Banglish words are
spelling-normalised. Intervals come from bootstrapping all three groups.

**Validation on known mixtures.** For each series, the human baseline and the AI reviews are each
split at random into two halves. One half gives h and a; the other halves are mixed with a known AI
share (0%, 5%, 10%, 20%) into a sample the size of the series' post-ChatGPT sample, and α is
estimated. This is repeated 1,000 times.

### Validation results

| Series | Mixture size | 0% → | 10% → | 20% → | 90% range at 10% |
|---|---|---|---|---|---|
| Daraz – Bangla | 598 | −0.2% | 10.1% | 20.0% | 4 to 17% |
| Daraz – Banglish | 254 | −0.1% | 10.0% | 20.2% | −2 to 21% |
| Daraz – English | 377 | −0.1% | 10.5% | 21.2% | 2 to 21% |
| Rokomari – Bangla | 342 | −0.5% | 10.2% | 20.0% | −3 to 23% |
| Rokomari – English | 68 | −0.2% | 9.0% | 21.0% | −14 to 34% |
| Shajgoj – Banglish | 62 | −1.0% | 7.2% | 19.0% | −35 to 42% |

On average the estimator recovers the true share (bias within 3 points). With the round-2 Daraz
baselines, a 10% AI share is now distinguishable from zero for Daraz Bangla and English; Shajgoj and
Rokomari English remain imprecise. The validation halves the baseline, so it somewhat overstates the spread
of the real estimates.

### Estimates after ChatGPT

| Series | Human rate h | AI rate a | Post rate m | Estimated AI share (95% CI) | Placebo (Jan–Nov 2022) |
|---|---|---|---|---|---|
| Daraz – Bangla | 11.2% | 78.3% | 16.7% | 8.3% (3.1, 14.0) | 3.6% (−4, 12) |
| Daraz – Banglish | 15.4% | 81.4% | 12.2% | −4.9% (−14.1, 3.0) | 1.9% (−12, 17) |
| Daraz – English | 6.3% | 54.5% | 11.9% | 11.7% (4.2, 21.6) | 0.0% (−10, 11) |
| Rokomari – Bangla | 42.5% | 93.4% | 39.5% | −6.0% (−19.2, 6.0) | −41.0% (−63, −23) |
| Rokomari – English | 9.9% | 54.5% | 16.2% | 14.0% (−8.0, 39.5) | −3.9% (−30, 22) |
| Shajgoj – Banglish | 19.3% | 68.2% | 12.9% | −13.1% (−51.1, 13.2) | −14.2% (−78, 29) |

- The Daraz Bangla (8.3%) and Daraz English (11.7%) estimates are above zero and their placebo
  estimates are not, but they compare different products before and after ChatGPT (see Phase 2).
  Using the same-product changes instead (+1.4 and +2.5 points) gives roughly 2% and 5%, with
  intervals that include zero. These figures are upper limits rather than evidence of AI use.
- Rokomari Bangla gives −6.0% with an upper bound of 4.0%, but its placebo estimate (−41%) shows that
  the Rokomari marker rate was already falling before ChatGPT.
- A negative estimate means that human use of marker words fell; the model assumes that human
  writing stays constant over time, so the estimates measure AI use together with changes in human
  writing style and product mix.

### Sample size needed

Reviews needed in each period (pre- and post-ChatGPT, equal sizes) for a 95% interval of about
±10 percentage points, from the normal approximation (`reviews_needed_pm10` in
`results/ai_share_estimates.csv`):

| Series | Daraz Bangla | Daraz Banglish | Daraz English | Rokomari Bangla | Rokomari English | Shajgoj Banglish |
|---|---|---|---|---|---|---|
| Needed per period | 207 | 212 | 311 | 720 | 553 | 463 |
| Current pre-ChatGPT | 904 | 376 | 871 | 927 | 161 | 57 |
| Current post-ChatGPT | 598 | 254 | 377 | 342 | 68 | 62 |

Daraz and Rokomari Bangla now meet the size target; for Daraz the remaining problem is balance
between product types, not size. Shajgoj and Rokomari English still need several times more reviews.

## Files

| Path | Contents |
|---|---|
| `data/reviews_all.csv` | All 11,238 reviews with cleaned text, word count, language, date, period, `keep` flags and `exclude_reason` |
| `data/reviews_daraz.csv`, `reviews_rokomari.csv`, `reviews_shajgoj.csv` | Kept reviews, one file per platform |
| `data/ai_reference_original.csv` | AI-generated reference reviews in the original language |
| `markers.csv` | Curated marker words by language and group |
| `results/dataset_counts.csv`, `dataset_counts_halfyear.csv`, `exclusions.csv` | Phase 1 counts |
| `results/marker_candidates_<language>.csv` | Ranked candidate words (discovery half) |
| `results/control_words.csv`, `marker_check.csv` | Control words; held-out check of the markers |
| `results/trend_series.csv` | Reviews per platform, language and period; which series are analysed |
| `results/trend_periods.csv` | Marker and control-word measures per series and period |
| `results/trend_changes.csv` | Post- minus pre-ChatGPT changes with bootstrap intervals, robustness subsets and the placebo check |
| `results/trend_halfyear.csv`, `word_shift.csv` | Half-year shares; per-word shares before and after |
| `results/fig_period_comparison.png` | Marker share before and after ChatGPT for each series |
| `results/fig_trend_halfyear.png` | Marker and control-word share by half-year |
| `results/fig_word_shift.png` | Each evaluative marker before and after ChatGPT |
| `banglish_variants.csv` | Banglish spelling-variant families with canonical forms |
| `results/banglish_standard_check.csv`, `banglish_standard_periods.csv`, `banglish_standard_changes.csv` | Standard-form share: AI vs human check; by platform and period; changes |
| `results/banglish_markers_crossfit.csv` | Cross-fitted Banglish markers per fold and changes by platform |
| `results/fig_banglish.png` | Standard-form share by year and period; cross-fitted markers |
| `results/language_mix_by_year.csv`, `language_mix_changes.csv` | Language shares by platform and year; changes |
| `results/fig_language_mix.png` | Language of reviews by year and platform |
| `results/ai_share_validation.csv` | Known-mixture validation of the AI-share estimate |
| `results/ai_share_estimates.csv` | Estimated AI share after ChatGPT, placebo, reviews needed |
| `results/fig_ai_share.png` | Validation and estimates |

## Next phases

1. Make the Daraz comparison product-balanced (post-ChatGPT reviews of household products or
   pre-ChatGPT reviews of gadgets) and add a product-stratified estimate; collect more Shajgoj
   reviews and post-ChatGPT Rokomari reviews; rerun scripts 01–07.
2. Generate additional English AI reviews (and a small ChatGPT-written set) to strengthen the
   English marker list and check that the markers are not specific to Gemini.
3. Apply AI-text detectors to the original text where a suitable detector exists (Bengali script,
   English), after validating them on pre-2022 reviews and the AI reference corpus.

## Reference

Liang, W., Izzo, Z., Zhang, Y., Lepp, H., Cao, H., Zhao, X., Chen, L., Ye, H., Liu, S., Huang, Z.,
McFarland, D. A., & Zou, J. Y. (2024). *Monitoring AI-Modified Content at Scale: A Case Study on
the Impact of ChatGPT on AI Conference Peer Reviews.* ICML 2024.
[arXiv:2403.07183](https://arxiv.org/abs/2403.07183)

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

Of 5,149 scraped reviews, 3,079 are kept (1,318 too short, 626 exact repeats, 99 stock requests,
27 without text). Most exact repeats are one-word reviews such as "Good" or অসাধারণ. Rokomari's
"Read More" link text, captured at the end of truncated reviews, is removed during cleaning.

**Kept reviews by platform, language and period**

| Platform | Language | Pre-ChatGPT | of which pre-2022 | of which Jan–Nov 2022 | Post-ChatGPT |
|---|---|---|---|---|---|
| Daraz | Bangla | 106 | 77 | 29 | 372 |
| Daraz | Banglish | 60 | 47 | 13 | 183 |
| Daraz | English | 75 | 63 | 12 | 211 |
| Rokomari | Bangla | 1,003 | 884 | 119 | 342 |
| Rokomari | English | 179 | 144 | 35 | 68 |
| Shajgoj | Banglish | 95 | 75 | 20 | 62 |
| Shajgoj | English | 118 | 89 | 29 | 25 |
| Shajgoj | Bangla | 29 | 21 | 8 | 32 |

Smaller groups (Rokomari Banglish, mixed-script reviews) are in `results/dataset_counts.csv`.

The earlier pipeline labelled many English reviews as Banglish and translated them. With the
corrected language tags, English is a substantial group on Daraz and Shajgoj.

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
| Bangla | evaluative (20 words) | 85.7% | 43.3% |
| Bangla | formal (4 words) | 65.5% | 53.6% |
| Bangla | control (15 words) | 81.5% | 89.4% |
| Banglish | evaluative (7 words) | 72.8% | 16.8% |
| Banglish | control (10 words) | 79.0% | 67.4% |
| English | evaluative (6 words) | 54.5% | 9.5% |
| English | control (15 words) | 90.9% | 90.5% |

The markers separate AI from human text on reviews they were not selected on; the control words do
not. The held-out Bangla reviews (860) are now mostly Rokomari book reviews, which use evaluative
words such as অসাধারণ more often than product reviews; the human rate is therefore higher than in
round 1 (29.4%), and each platform's own baseline is used in the trend. The English list rests on
44 AI reviews and is the least reliable.

### Results

Six series meet the size requirement. Share of reviews containing an evaluative marker word, with
95% bootstrap intervals:

| Series | Pre-ChatGPT | Post-ChatGPT | Change (points) |
|---|---|---|---|
| Daraz – Bangla | 14.5% (n = 69) | 20.2% (n = 372) | +5.7 [−4.0, +14.4] |
| Daraz – Banglish | 17.9% (n = 39) | 8.2% (n = 183) | −9.8 [−23.0, +1.8] |
| Daraz – English | 14.3% (n = 42) | 14.7% (n = 211) | +0.4 [−11.5, +11.4] |
| Rokomari – Bangla | 42.5% (n = 927) | 39.5% (n = 342) | −3.0 [−9.1, +3.5] |
| Rokomari – English | 9.9% (n = 161) | 16.2% (n = 68) | +6.2 [−3.1, +16.5] |
| Shajgoj – Banglish | 19.3% (n = 57) | 11.3% (n = 62) | −8.0 [−21.5, +4.3] |

No series shows a clear increase in the share of reviews containing AI-associated words after
ChatGPT's release. Reviews over 10 words, same-product reviews and a pre-2022-only baseline lead to
the same conclusion (`results/trend_changes.csv`). With 927 baseline reviews, Rokomari Bangla is now
precise enough to rule out an increase of more than about 3.5 points.

- **Markers per 100 words, Rokomari Bangla.** This measure rose from 1.6 to 2.6 (+1.05 [+0.54,
  +1.61]). Control words per 100 words rose even more (7.8 to 10.1), and the same increase already
  appears between pre-2022 and Jan–Nov 2022. Post-ChatGPT Rokomari reviews are shorter, which raises
  all per-100-word rates; the change is not specific to AI-associated words.
- **Formal words, Rokomari Bangla.** The share containing a formal word (এটি, একটি, এবং …) fell from
  52.0% to 34.5%. AI text uses these words more, so the change runs against AI use; it also appears
  in the placebo comparison.

- **Longer reviews.** Among reviews over 25 words, Daraz Bangla (+26.9 points [+11.8, +40.2]) and
  Daraz English (+13.0 [+5.6, +22.2]) show increases, but their pre-ChatGPT groups contain only 19 and
  6 reviews. These are two of 30 robustness comparisons and are treated as leads, not findings.
- **Placebo.** Jan–Nov 2022 does not differ from pre-2022 in four of six series. Daraz English
  (−20 points) fails because no marker appears in its 12 Jan–Nov 2022 reviews. Rokomari Bangla
  (45.0% vs 25.2%, −19.8 points) shows that Rokomari reviewing changed before ChatGPT; its
  before/after comparison should therefore be read alongside the half-year trend, not as a
  stand-alone effect.
- **Control words** show no clear change on Daraz and Shajgoj. On Rokomari the share of reviews
  containing a control word fell slightly (Bangla −6.5 points), again consistent with shorter
  reviews.
- **Rokomari English, reviews over 10 words.** Markers per 100 words increased (+1.35 [+0.13,
  +2.72]; 94 vs 31 reviews), the only per-word increase outside Rokomari Bangla. One of many
  comparisons; treated as a lead.
- **Word level** (`fig_word_shift.png`). On Daraz, অসাধারণ "extraordinary" rose from 2.9% to 9.7% of
  Bangla reviews and একদম "absolutely" from 1.4% to 4.8%; these individual shifts are not reflected in
  the overall marker share.

### Interpretation and limitations

- Outside Rokomari Bangla the baselines are small (39–161 reviews per series), so changes of about
  10–15 points cannot be ruled out.
- Rokomari's review style changed before ChatGPT (placebo), so a constant-baseline comparison
  is less reliable there than the size of its sample suggests.
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
| Human pre-2022, held-out half | 87 | 50.4% |
| Human pre-2022, all | 142 | 53.2% |

Before and after ChatGPT (95% bootstrap interval):

| Platform | Pre-ChatGPT | Post-ChatGPT | Change (points) | Placebo (Jan–Nov 2022 − pre-2022) |
|---|---|---|---|---|
| Daraz | 43.3% (n = 57) | 46.0% (n = 166) | +2.7 [−7.1, +12.8] | −8.3 [−27.0, +10.1] |
| Shajgoj | 58.3% (n = 83) | 53.7% (n = 54) | −4.6 [−17.4, +7.9] | −4.0 [−21.3, +12.1] |

Spelling has not moved towards the AI pattern on either platform.

### Cross-fitted marker words (`05_banglish.py`, part B)

Marker words are counted after spelling normalisation, so *akdom* and *ekdom* count as the same
word. To use every pre-ChatGPT review, the analysis is cross-fitted: markers are chosen on one half
of the pre-2022 reviews and the baseline is measured on the other half, then the halves are swapped
and the two estimates averaged. Markers are selected automatically from a fixed list of evaluative
words (`EVALUATIVE` in the script, defined before the analysis) as those with log-odds z ≥ 1.

| Fold | Markers selected | Held-out AI | Held-out human |
|---|---|---|---|
| A | darun, ekdom, highly, khub, khuboi, recommended, shobcheye | 72.8% | 21.1% |
| B | awesome, darun, ekdom, highly, khub, khubi, perfect, recommended | 75.6% | 24.6% |

Both halves select largely the same words.

| Platform | Pre-ChatGPT | Post-ChatGPT | Change (points) |
|---|---|---|---|
| Daraz | 26.1% (n = 60) | 12.6% (n = 183) | −13.5 [−26.4, −1.6] |
| Shajgoj | 20.9% (n = 95) | 13.7% (n = 62) | −7.1 [−19.0, +4.4] |

Banglish reviews did not become more AI-like after ChatGPT; on Daraz, marker words became less
frequent.

### Language mix (`06_language_mix.py`)

AI assistants write standard Bengali script or English by default. A shift away from Banglish after
ChatGPT would therefore be one possible trace of AI use, although keyboard habits and the reviewer
population also affect it. Change in the share of reviews in each language, post- minus
pre-ChatGPT, for products reviewed in both periods:

| Platform | Bengali script | Banglish | English |
|---|---|---|---|
| Daraz (240 → 232 reviews) | +20.9 [+12.4, +29.7] | −2.2 [−9.8, +5.4] | −18.8 [−25.9, −11.9] |
| Rokomari (1,226 → 443) | −5.0 [−9.2, −0.5] | +3.5 [+1.2, +6.1] | +0.1 [−3.9, +3.9] |
| Shajgoj (218 → 124) | +13.9 [+5.1, +23.1] | +13.3 [+2.4, +24.5] | −29.4 [−39.0, −20.0] |

The Banglish share did not fall on any platform; on Shajgoj and Rokomari it rose. English declined on Daraz
and Shajgoj, while Bengali script grew. This pattern does not match a shift towards
AI-produced text, which would favour polished English or Bengali script over Banglish; it is more
consistent with a broader move towards Bengali-language reviewing.

### Limitations

- The pre-ChatGPT Banglish groups are small (57–95 reviews).
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
| Daraz – Bangla | 372 | −1.1% | 9.2% | 20.0% | −13 to 29% |
| Daraz – Banglish | 183 | −3.2% | 7.3% | 18.4% | −37 to 42% |
| Daraz – English | 211 | −4.9% | 5.8% | 17.2% | −51 to 49% |
| Rokomari – Bangla | 342 | 0.0% | 9.8% | 19.8% | −4 to 22% |
| Rokomari – English | 68 | −0.4% | 9.7% | 20.6% | −13 to 34% |
| Shajgoj – Banglish | 62 | −1.4% | 7.2% | 18.9% | −33 to 45% |

On average the estimator recovers the true share (bias within 5 points; a 10% mixture returns
6–10%). Single estimates, however, are very imprecise at the current sample sizes, mainly because the
human baselines are small. The validation halves the baseline, so it somewhat overstates the spread
of the real estimates.

### Estimates after ChatGPT

| Series | Human rate h | AI rate a | Post rate m | Estimated AI share (95% CI) | Placebo (Jan–Nov 2022) |
|---|---|---|---|---|---|
| Daraz – Bangla | 14.5% | 78.3% | 20.2% | 8.9% (−6.5, 20.6) | −1.9% (−31, 23) |
| Daraz – Banglish | 25.6% | 81.4% | 10.9% | −26.4% (−72.9, −1.9) | −7.1% (−77, 43) |
| Daraz – English | 14.3% | 54.5% | 14.7% | 1.0% (−44.1, 25.6) | −57.9% (−214, −15) |
| Rokomari – Bangla | 42.5% | 93.4% | 39.5% | −6.0% (−18.6, 5.6) | −41.0% (−62, −22) |
| Rokomari – English | 9.9% | 54.5% | 16.2% | 14.0% (−8.2, 38.3) | −3.9% (−32, 23) |
| Shajgoj – Banglish | 19.3% | 68.2% | 12.9% | −13.1% (−52.5, 11.9) | −14.2% (−79, 28) |

- No series shows an AI share clearly above zero. Daraz Bangla gives 8.9% with a one-sided 95%
  upper bound of 18.7%. With the round-2 reviews, Rokomari Bangla gives −6.0% with an upper bound of
  4.1%, but its placebo estimate (−41%) shows that the Rokomari marker rate was already falling
  before ChatGPT, so this bound should not be taken at face value.
- A negative estimate means that human use of marker words fell; the model assumes that human
  writing stays constant over time. The clearly negative Daraz Banglish estimate shows that this
  assumption does not fully hold, so the estimates measure AI use together with changes in human
  writing style.
- The placebo estimate includes zero in four of six series. Daraz English fails because none of its
  12 Jan–Nov 2022 reviews contains a marker; Rokomari Bangla fails as described above.

### Sample size needed

Reviews needed in each period (pre- and post-ChatGPT, equal sizes) for a 95% interval of about
±10 percentage points, from the normal approximation (`reviews_needed_pm10` in
`results/ai_share_estimates.csv`):

| Series | Daraz Bangla | Daraz Banglish | Daraz English | Rokomari Bangla | Rokomari English | Shajgoj Banglish |
|---|---|---|---|---|---|---|
| Needed per period | 275 | 459 | 589 | 720 | 553 | 463 |
| Current pre-ChatGPT | 69 | 39 | 42 | 927 | 161 | 57 |
| Current post-ChatGPT | 372 | 183 | 211 | 342 | 68 | 62 |

After round 2, Rokomari Bangla meets the pre-ChatGPT target; its post-ChatGPT side (342) is the
limiting group. The other series need roughly 3–15 times more pre-ChatGPT reviews.

## Files

| Path | Contents |
|---|---|
| `data/reviews_all.csv` | All 5,149 reviews with cleaned text, word count, language, date, period, `keep` flags and `exclude_reason` |
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

1. Collect additional reviews, prioritising the pre-ChatGPT baselines on Daraz and Shajgoj and
   post-ChatGPT Rokomari reviews (round 2 covered the Rokomari baseline), then rerun scripts 01–07.
2. Generate additional English AI reviews (and a small ChatGPT-written set) to strengthen the
   English marker list and check that the markers are not specific to Gemini.
3. Apply AI-text detectors to the original text where a suitable detector exists (Bengali script,
   English), after validating them on pre-2022 reviews and the AI reference corpus.

## Reference

Liang, W., Izzo, Z., Zhang, Y., Lepp, H., Cao, H., Zhao, X., Chen, L., Ye, H., Liu, S., Huang, Z.,
McFarland, D. A., & Zou, J. Y. (2024). *Monitoring AI-Modified Content at Scale: A Case Study on
the Impact of ChatGPT on AI Conference Peer Reviews.* ICML 2024.
[arXiv:2403.07183](https://arxiv.org/abs/2403.07183)

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
| Language | `bangla`: at least 80% of letters in Bengali script. `mixed`: 20–80%. Latin-script text is `banglish` if it contains two or more common Banglish words (or one, with at most two common English words), otherwise `english` |
| Date | Parsed from the review date. Daraz shows reviews newer than about a month as "x weeks ago"; these are converted using the scrape date (16 Oct 2026) and marked `date_is_approx` |
| Period | `period`: `pre_chatgpt` (before 30 Nov 2022) or `post_chatgpt` (30 Nov 2022 onwards). `period_detail` splits the pre-ChatGPT period into `pre_2022` and `jan_nov_2022`, used for a placebo check. Calendar half-years in `half_year` |
| Exclusion | In order: duplicate review ID; no text; exact repeat of a review on the same platform (earliest kept); restock or availability request of 15 words or fewer; **5 words or fewer** |

`keep_10` and `keep_25` mark reviews longer than 10 and 25 words, for sensitivity checks.

Of 2,899 scraped reviews, 1,740 are kept (774 too short, 279 exact repeats, 99 stock requests,
7 without text).

**Kept reviews by platform, language and period**

| Platform | Language | Pre-ChatGPT | of which pre-2022 | of which Jan–Nov 2022 | Post-ChatGPT |
|---|---|---|---|---|---|
| Daraz | Bangla | 106 | 77 | 29 | 372 |
| Daraz | Banglish | 59 | 46 | 13 | 183 |
| Daraz | English | 76 | 64 | 12 | 211 |
| Rokomari | Bangla | 172 | 150 | 22 | 55 |
| Rokomari | English | 58 | 43 | 15 | 31 |
| Shajgoj | Banglish | 95 | 75 | 20 | 59 |
| Shajgoj | English | 118 | 89 | 29 | 28 |
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

Shared cleaning, word-counting and language-tagging functions, used by both scripts so that real
and AI-generated reviews are processed identically.

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
| Bangla | evaluative (20 words) | 85.7% | 29.4% |
| Bangla | formal (4 words) | 65.5% | 40.5% |
| Bangla | control (15 words) | 81.5% | 78.6% |
| Banglish | evaluative (7 words) | 72.8% | 19.1% |
| Banglish | control (10 words) | 79.0% | 72.1% |
| English | evaluative (6 words) | 54.5% | 9.2% |
| English | control (15 words) | 90.9% | 90.8% |

The markers separate AI from human text on reviews they were not selected on; the control words do
not. The English list rests on 44 AI reviews and is the least reliable.

### Results

Six series meet the size requirement. Share of reviews containing an evaluative marker word, with
95% bootstrap intervals:

| Series | Pre-ChatGPT | Post-ChatGPT | Change (points) |
|---|---|---|---|
| Daraz – Bangla | 14.5% (n = 69) | 20.2% (n = 372) | +5.7 [−4.0, +14.4] |
| Daraz – Banglish | 17.9% (n = 39) | 8.2% (n = 183) | −9.8 [−23.0, +1.8] |
| Daraz – English | 14.3% (n = 42) | 14.7% (n = 211) | +0.4 [−11.5, +11.4] |
| Rokomari – Bangla | 36.5% (n = 96) | 30.9% (n = 55) | −5.5 [−21.1, +10.3] |
| Rokomari – English | 15.0% (n = 40) | 19.4% (n = 31) | +4.4 [−13.5, +21.5] |
| Shajgoj – Banglish | 19.3% (n = 57) | 11.9% (n = 59) | −7.4 [−21.2, +4.9] |

No series shows a clear increase in AI-associated words after ChatGPT's release. Markers per
100 words, reviews over 10 words, same-product reviews and a pre-2022-only baseline lead to the
same conclusion (all `no clear change` in `results/trend_changes.csv`).

- **Longer reviews.** Among reviews over 25 words, Daraz Bangla (+26.9 points [+11.8, +40.2]) and
  Daraz English (+13.0 [+5.6, +22.2]) show increases, but their pre-ChatGPT groups contain only 19 and
  6 reviews. These are two of 30 robustness comparisons and are treated as leads, not findings.
- **Placebo.** Jan–Nov 2022 does not differ from pre-2022 in five of six series. The exception is
  Daraz English (−20 points), where no marker appears in the 12 Jan–Nov 2022 reviews.
- **Control words** show no clear change in five of six series; Rokomari English shows a decrease
  (−24 points, 40 vs 31 reviews).
- **Word level** (`fig_word_shift.png`). On Daraz, অসাধারণ "extraordinary" rose from 2.9% to 9.7% of
  Bangla reviews and একদম "absolutely" from 1.4% to 4.8%; these individual shifts are not reflected in
  the overall marker share.

### Interpretation and limitations

- The baselines are small (39–96 reviews per series), so changes of about 10–15 points cannot be
  ruled out.
- Marker words were derived from Gemini output; reviews written with ChatGPT may favour other words.
- The English marker list is based on 44 AI reviews.
- Banglish spelling varies widely; only repeated letters are normalised.

## Files

| Path | Contents |
|---|---|
| `data/reviews_all.csv` | All 2,899 reviews with cleaned text, word count, language, date, period, `keep` flags and `exclude_reason` |
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

## Next phases

1. Collect additional reviews, prioritising the pre-ChatGPT baselines (Daraz, Shajgoj) and
   post-ChatGPT Rokomari and Shajgoj reviews, then rerun scripts 01–04.
2. Generate additional English AI reviews (and a small ChatGPT-written set) to strengthen the
   English marker list and check that the markers are not specific to Gemini.
3. Apply AI-text detectors to the original text where a suitable detector exists (Bengali script,
   English), after validating them on pre-2022 reviews and the AI reference corpus.

## Reference

Liang, W., Izzo, Z., Zhang, Y., Lepp, H., Cao, H., Zhao, X., Chen, L., Ye, H., Liu, S., Huang, Z.,
McFarland, D. A., & Zou, J. Y. (2024). *Monitoring AI-Modified Content at Scale: A Case Study on
the Impact of ChatGPT on AI Conference Peer Reviews.* ICML 2024.
[arXiv:2403.07183](https://arxiv.org/abs/2403.07183)

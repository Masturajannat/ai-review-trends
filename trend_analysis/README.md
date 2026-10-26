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
| Period | `pre_2022`; `2022_control` (1 Jan – 29 Nov 2022, before ChatGPT); `post_chatgpt` (30 Nov 2022 onwards). Calendar half-years in `half_year` |
| Exclusion | In order: duplicate review ID; no text; exact repeat of a review on the same platform (earliest kept); restock or availability request of 15 words or fewer; **5 words or fewer** |

`keep_10` and `keep_25` mark reviews longer than 10 and 25 words, for sensitivity checks.

Of 2,899 scraped reviews, 1,740 are kept (774 too short, 279 exact repeats, 99 stock requests,
7 without text).

**Kept reviews by platform, language and period**

| Platform | Language | Pre-2022 | 2022 control | Post-ChatGPT |
|---|---|---|---|---|
| Daraz | Bangla | 77 | 29 | 372 |
| Daraz | Banglish | 46 | 13 | 183 |
| Daraz | English | 64 | 12 | 211 |
| Rokomari | Bangla | 150 | 22 | 55 |
| Rokomari | English | 43 | 15 | 31 |
| Shajgoj | Banglish | 75 | 20 | 59 |
| Shajgoj | English | 89 | 29 | 28 |
| Shajgoj | Bangla | 21 | 8 | 32 |

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

## Files

| Path | Contents |
|---|---|
| `data/reviews_all.csv` | All 2,899 reviews with cleaned text, word count, language, date, period, `keep` flags and `exclude_reason` |
| `data/reviews_daraz.csv`, `reviews_rokomari.csv`, `reviews_shajgoj.csv` | Kept reviews, one file per platform |
| `data/ai_reference_original.csv` | AI-generated reference reviews in the original language |
| `results/dataset_counts.csv` | Kept reviews by platform, language and period |
| `results/dataset_counts_halfyear.csv` | Kept reviews by platform, language and half-year |
| `results/exclusions.csv` | Number of reviews removed, by reason |

## Next phases

1. Collect additional reviews, prioritising post-ChatGPT Rokomari and Shajgoj reviews and
   pre-2022 Daraz reviews of the same products.
2. Identify AI-associated words in each language by comparing the AI reference corpus with pre-2022
   reviews, and track their frequency by half-year on each platform, with control words.
3. Apply AI-text detectors to the original text where a suitable detector exists (Bengali script,
   English), after validating them on pre-2022 reviews and the AI reference corpus.

## Reference

Liang, W., Izzo, Z., Zhang, Y., Lepp, H., Cao, H., Zhao, X., Chen, L., Ye, H., Liu, S., Huang, Z.,
McFarland, D. A., & Zou, J. Y. (2024). *Monitoring AI-Modified Content at Scale: A Case Study on
the Impact of ChatGPT on AI Conference Peer Reviews.* ICML 2024.
[arXiv:2403.07183](https://arxiv.org/abs/2403.07183)

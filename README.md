# ai-review-trends

## Project overview

This repository investigates the prevalence of AI-generated content in Bangladeshi e-commerce
reviews. The project aims to determine whether the emergence and accessibility of generative AI
tools have led to a measurable increase in AI-synthesized feedback within the local e-commerce
landscape.

Reviews were collected from three platforms: Daraz (electronics), Rokomari (books) and Shajgoj
(skincare). They are written in Bengali script, Banglish (Bengali in Latin letters) and English.
Reviews posted before 2022 predate ChatGPT (released 30 November 2022) and serve as the human
baseline.

CSE299 Junior Design, Department of ECE, North South University, Fall 2026.

## Approach

The current analysis (`trend_analysis/`) works on the original review text, without translation,
and analyses each platform separately. Following Liang et al. (2024), it identifies words that
AI-generated reviews use far more often than pre-2022 human reviews and tracks how often these
words appear before and after ChatGPT's release, with reviews from January to November 2022 used
as a placebo check.

Earlier approaches applied an AI-text detector (Week 4) and a distributional estimator (Week 5)
to machine-translated reviews. They are kept in `archive/` with a summary of why they were replaced.

## Repository structure

| Path | Contents |
|---|---|
| `daraz_scraper_v2.py`, `rokomari_scraper.py`, `shajgoj_scraper.py` | Review scrapers for each platform |
| `inspect_daraz_api.py`, `shajgoj_discover.py` | Helpers used to locate each site's review API |
| `daraz_reviews_v2.csv`, `rokomari_reviews.csv`, `shajgoj_reviews.csv` | Scraped reviews per platform |
| `raw_daraz/` | Raw Daraz API responses |
| `combine_reviews_all.py` → `combined_reviews.csv` | All 2,899 scraped reviews in one file, original text |
| `trend_analysis/` | Current pipeline: dataset preparation and trend analysis (see its README) |
| `INSTRUCTIONS.md` | Setup, Git workflow, running the pipeline, adding new reviews |
| `archive/` | Earlier translation-based approaches (see its README) |

## Running the pipeline

See `INSTRUCTIONS.md` for setup and the full workflow.

```powershell
python combine_reviews_all.py                              # merge the scraped files
python trend_analysis\scripts\01_build_dataset.py          # clean, tag language, assign periods
python trend_analysis\scripts\02_build_ai_reference.py     # AI reference reviews, original language
python trend_analysis\scripts\03_marker_words.py          # AI-associated marker words per language
python trend_analysis\scripts\04_trends.py                # marker-word trends per platform
python trend_analysis\scripts\05_banglish.py              # Banglish spelling and marker analysis
python trend_analysis\scripts\06_language_mix.py          # language of reviews over time
python trend_analysis\scripts\07_ai_share.py              # estimated AI share, validated on known mixtures
```

Requires Python 3.10+ with `pandas`, `numpy` and `matplotlib`.

## Reference

Liang, W., Izzo, Z., Zhang, Y., Lepp, H., Cao, H., Zhao, X., Chen, L., Ye, H., Liu, S., Huang, Z.,
McFarland, D. A., & Zou, J. Y. (2024). *Monitoring AI-Modified Content at Scale: A Case Study on
the Impact of ChatGPT on AI Conference Peer Reviews.* ICML 2024.
[arXiv:2403.07183](https://arxiv.org/abs/2403.07183)

# Archive

Earlier approaches, kept for the record. The scripts are stored as they were run; their file paths
were not updated after the move, so they are not expected to run from this folder.

All three approaches analysed **machine-translated English text**: Bengali and Banglish reviews (and
some English reviews that were misclassified as Banglish) were translated with Google/Bing machine
translation before analysis, and the Week 4 test pairs were translated with Gemini. Translation
removes the original writing style, and translated text is itself machine-generated, which makes it
unsuitable for detecting AI-written reviews. The current pipeline in `trend_analysis/` works on the
original text instead.

| Folder | Period | Approach | Why it was replaced |
|---|---|---|---|
| `translation/` | Weeks 2–3 | Translation of all non-English reviews to English (`translate_reviews_to_english.py`, `fix_translations.py`) and the translated datasets | Analysis now uses the original text |
| `week4_translated_detector/` | Week 4 | RoBERTa AI-text detector (`Hello-SimpleAI/chatgpt-detector-roberta`) on translated reviews; flag rates by period; detector test on 148 human/AI pairs; error-corrected AI share | Detector was weak on this data (recall 0.23, AUC 0.71) and flagged pre-2022 reviews; operated on translated text |
| `week5_mixture_translated/` | Week 5 | Distributional AI-share estimator (Liang et al., 2024) on translated reviews; 801 Gemini reference reviews; per-platform validation | Estimates were driven by review length: very short reviews were assigned to the AI distribution in every period, including before 2022. Operated on translated text. See its `README.md` |
| `old_scripts/` | Week 2 | `combine_reviews.py`, an early version of `combine_reviews_all.py` (Daraz and Shajgoj only) | Superseded |

Material reused by the current pipeline:

- `week5_mixture_translated/data/ai_reference.csv`, `ai_validation.csv`: the original-language text of
  the 801 Gemini reviews (`review_text` column)
- `week4_translated_detector/analysis/labeled_set.csv`: the original-language text of the 148 Gemini
  rewrites (`text_original` column, rows with `label_name = ai`)

Both are collected into `trend_analysis/data/ai_reference_original.csv` by
`trend_analysis/scripts/02_build_ai_reference.py`.

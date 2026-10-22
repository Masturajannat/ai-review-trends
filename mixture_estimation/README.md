# Mixture estimation (Liang et al., 2024)

Estimates the **share of AI-written text** in a set of reviews without labelling single reviews, following
[Monitoring AI-Modified Content at Scale](https://arxiv.org/abs/2403.07183). Human word use (P) is learned
from pre-2022 reviews and AI word use (Q) from AI-generated reviews, then the AI share α of any review set
is found by maximum likelihood over sentences.

## Steps (run from the `ai-review-trends` folder)

| Step | Script | What it does |
|---|---|---|
| 0 | `scripts/00_make_source.py` | Copies the cleaned review file into `data/source_reviews_clean.csv` |
| 1 | `scripts/01_split.py` | Splits pre-2022 reviews into `human_reference` (learn P) and `human_validation` (testing), same platform/language mix in both |
| 2 | `scripts/02_pilot.py` | Draws a 100 + 100 pilot sample from the two halves |
| 3 | `scripts/03_generate_ai.py` | Makes one AI review per pilot human review (half rewrites, half new reviews from product + rating) |
| 4 | `scripts/04_translate_ai.py` | Translates Bangla/Banglish AI reviews with the **same** translator as the real data |
| 5 | `scripts/05_validate.py` | Validation: mixes known AI shares (0–25%) into held-out human reviews and checks the estimate; then estimates the real data |

```powershell
$env:GEMINI_API_KEY="your-key"          # never put keys in code or commit them
python mixture_estimation\scripts\03_generate_ai.py            # Gemini is the default (free tier)
python mixture_estimation\scripts\03_generate_ai.py --provider openai   # needs OPENAI_API_KEY and credits
python mixture_estimation\scripts\04_translate_ai.py
python mixture_estimation\scripts\05_validate.py
```

## Generator: Gemini instead of OpenAI

The OpenAI account had no API credits, so the AI reviews were generated with **Gemini (`gemini-3.5-flash-lite`,
free tier)**. Every AI review stores its `provider` and `model`. Consequences to state in the report:

- Q describes *Gemini* word habits; real post-2022 AI reviews are more likely ChatGPT-written, so the
  estimate may miss some ChatGPT text (a lower bound). A small cross-model check with ChatGPT-written
  reviews is planned.
- The earlier RoBERTa test set (`02_build_labeled_set.py`) was also made with Gemini, so this is consistent.

`03_generate_ai.py` also: names the exact language in the prompt (Bangla script / Banglish / English) and
re-asks when the answer comes back in the wrong script; leaves the rating out when a review has none;
saves after every review so a run can be stopped and resumed; never saves failed requests as blank rows.

## Pilot results (100 AI reviews to learn Q, 100 to test)

| True AI share in mix | 0% | 5% | 10% | 15% | 20% | 25% |
|---|---|---|---|---|---|---|
| Estimated (mean of 200 mixes) | 7.5% | 10.3% | 13.0% | 16.0% | 19.2% | 22.0% |

The estimate tracks the truth but is pulled toward the middle (10% → 13%; the paper reaches about ±2 points).
Main reason: Q is learned from only 100 AI reviews (316 sentences). **Next step:** generate one AI review for
every human review in `human_reference` and `human_validation` (~800), translate, and rerun step 5.
Real-data numbers in `results/real_data_estimates.csv` are preliminary until the validation passes.

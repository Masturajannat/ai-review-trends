"""
Find words that AI-generated reviews use much more often than pre-2022 human reviews (marker words),
separately for Bangla, Banglish and English, and check them on held-out data.

The pre-2022 reviews are split in two (the split from the earlier work, archive/week5_mixture_translated/
data/human_reference.csv):
  discovery half - used here to rank words
  held-out half  - never used to choose words; used to check the markers and, in 04_trends.py, as the
                   pre-2022 baseline. Choosing words and measuring the trend on the same reviews would
                   make the pre-2022 rate look artificially low.
AI reviews are split the same way (by the half their source review belongs to).

Ranking: log-odds ratio with an informative Dirichlet prior (Monroe, Colaresi & Quinn, 2008), computed on
word OCCURRENCE per review (a review either contains a word or not), as in Liang et al. (2024).

Output (trend_analysis/results/)
  marker_candidates_<language>.csv   all words seen in at least 5 AI reviews, ranked by z
  control_words.csv                  frequent words with no AI/human difference (|z| < 0.5) that occur in at
                                     least 3 products (no product over half the occurrences), per language
  marker_check.csv                   share of held-out reviews containing a marker: AI vs human

The final marker list is trend_analysis/markers.csv. It was curated from the candidate lists by word
class, following the paper's use of adjectives: evaluative adjectives and adverbs ("evaluative") and
formal function words ("formal"). Product, shopping and topic words (e.g. delivery, online, hardcover,
book titles, author names) were excluded; several reflect the wording of the generation prompt rather
than AI style. The curation used only the discovery half.

Run from the repository root:  python trend_analysis/scripts/03_marker_words.py
"""
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import textutil as tu  # noqa: E402

ROOT = HERE.parents[1]
TA = ROOT / "trend_analysis"
REF_SPLIT = ROOT / "archive" / "week5_mixture_translated" / "data" / "human_reference.csv"
LANGUAGES = ["bangla", "banglish", "english"]


def load():
    reviews = pd.read_csv(TA / "data" / "reviews_all.csv", encoding="utf-8-sig", dtype={"review_id": str})
    reviews = reviews[reviews.keep]
    ai = pd.read_csv(TA / "data" / "ai_reference_original.csv", encoding="utf-8-sig",
                     dtype={"source_review_id": str})
    ai = ai[ai.keep]
    ref_ids = set(pd.read_csv(REF_SPLIT, dtype={"review_id": str}).review_id)
    reviews["half"] = np.where(reviews.review_id.isin(ref_ids), "discovery", "heldout")
    ai["half"] = np.where(ai.source_review_id.isin(ref_ids), "discovery", "heldout")
    return reviews, ai


def word_sets(texts, language):
    return [set(tu.tokens(t, language)) for t in texts]


def log_odds(ai_sets, human_sets, prior_scale=0.01):
    """Monroe et al. (2008) log-odds with informative Dirichlet prior, on review-level occurrence."""
    ca = Counter(w for s in ai_sets for w in s)
    ch = Counter(w for s in human_sets for w in s)
    vocab = sorted(set(ca) | set(ch))
    total = sum(ca[w] + ch[w] for w in vocab)
    a0 = prior_scale * len(vocab) * 100
    na, nh = sum(ca.values()), sum(ch.values())
    rows = []
    for w in vocab:
        aw = (ca[w] + ch[w]) / total * a0
        la = np.log((ca[w] + aw) / (na + a0 - ca[w] - aw))
        lh = np.log((ch[w] + aw) / (nh + a0 - ch[w] - aw))
        z = (la - lh) / np.sqrt(1 / (ca[w] + aw) + 1 / (ch[w] + aw))
        rows.append((w, ca[w], ch[w], ca[w] / len(ai_sets), ch[w] / len(human_sets), z))
    return (pd.DataFrame(rows, columns=["word", "ai_reviews", "human_reviews", "ai_rate", "human_rate", "z"])
            .sort_values("z", ascending=False))


def contains_any(texts, language, words):
    words = set(words)
    return np.array([bool(words & set(tu.tokens(t, language))) for t in texts])


def main():
    reviews, ai = load()
    markers = pd.read_csv(TA / "markers.csv")
    out = TA / "results"
    out.mkdir(parents=True, exist_ok=True)
    controls, checks = [], []
    for lang in LANGUAGES:
        h_disc = reviews[(reviews.language == lang) & (reviews.period_detail == "pre_2022") & (reviews.half == "discovery")]
        a_disc = ai[(ai.language == lang) & (ai.half == "discovery")]
        cand = log_odds(word_sets(a_disc.text_clean, lang), word_sets(h_disc.text_clean, lang))
        cand["in_markers"] = cand.word.isin(markers[markers.language == lang].word)
        cand[cand.ai_reviews >= 5].to_csv(out / f"marker_candidates_{lang}.csv", index=False, encoding="utf-8-sig")
        print(f"{lang}: discovery = {len(a_disc)} AI vs {len(h_disc)} human reviews")

        # control words: frequent in human reviews, no AI/human difference, not a marker, and spread
        # over several products (so they do not rise or fall with the product mix, e.g. book titles)
        ctrl = cand[(cand.z.abs() < 0.5) & ~cand.in_markers & (cand.human_reviews >= 5)].copy()
        h_sets = word_sets(h_disc.text_clean, lang)
        products = h_disc.product_id.astype(str).to_numpy()

        def spread(word):
            hits = Counter(p for p, s in zip(products, h_sets) if word in s)
            return len(hits), max(hits.values()) / sum(hits.values())
        ctrl[["n_products", "top_product_share"]] = [spread(w) for w in ctrl.word]
        ctrl = ctrl[(ctrl.n_products >= 3) & (ctrl.top_product_share <= 0.5)]
        ctrl = ctrl.sort_values("human_rate", ascending=False).head(15)
        controls.append(ctrl.assign(language=lang)[["language", "word", "ai_rate", "human_rate", "z",
                                                    "n_products", "top_product_share"]])

        # held-out check: do the curated markers separate AI from human text they were not chosen on?
        h_out = reviews[(reviews.language == lang) & (reviews.period_detail == "pre_2022") & (reviews.half == "heldout")]
        a_out = ai[(ai.language == lang) & (ai.half == "heldout")]
        for group in ["evaluative", "formal", "control"]:
            words = ctrl.word if group == "control" else markers[(markers.language == lang) & (markers.group == group)].word
            if len(words) == 0:
                continue
            hr, ar = contains_any(h_out.text_clean, lang, words), contains_any(a_out.text_clean, lang, words)
            checks.append(dict(language=lang, group=group, n_words=len(words), heldout_ai_reviews=len(ar),
                               heldout_human_reviews=len(hr), ai_share=ar.mean(), human_share=hr.mean(),
                               ratio=ar.mean() / max(hr.mean(), 1e-9)))

    pd.concat(controls).to_csv(out / "control_words.csv", index=False, encoding="utf-8-sig")
    chk = pd.DataFrame(checks)
    chk.to_csv(out / "marker_check.csv", index=False)
    show = chk.copy()
    for c in ["ai_share", "human_share"]:
        show[c] = (show[c] * 100).round(1)
    print("\nHeld-out check: % of reviews containing at least one word of the group")
    print(show.round(2).to_string(index=False))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()

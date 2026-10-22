"""
Validate the distributional AI-share estimator (Liang et al. 2024, arXiv:2403.07183) on our reviews,
then apply it to the real data.

The instructor's test: take pre-ChatGPT (human) reviews, mix in a KNOWN share of AI reviews (e.g. 10%),
and check that the estimated AI share comes back close to the truth. Only if it does do we trust it on
real 2022 / post-2022 reviews.

Data (all from earlier steps, in ../data):
  human_reference.csv   pre-2022 human reviews -> learn the HUMAN word distribution P
  pilot_ai_reference.csv  AI reviews (made from pilot_human_reference) -> learn the AI distribution Q
  human_validation.csv  held-out pre-2022 human reviews -> the "human" part of each test mix
  pilot_ai_validation.csv held-out AI reviews -> the "AI" part of each test mix
  source_reviews_clean.csv all real reviews -> real-data estimates per period and platform
A test mix never contains the human review an AI review in the same mix was made from.

Method (as in the paper): every review is split into sentences; each sentence is a SET of words.
p_t = share of human sentences containing word t, q_t = same for AI. A sentence's likelihood under P is
prod_t (p_t if t in sentence else 1 - p_t), same for Q. The AI share alpha maximises
sum_s log((1 - alpha) P(s) + alpha Q(s)). The estimate is a share of SENTENCES, so the truth we compare
to is the share of AI sentences in the mix (the share of AI reviews is reported too).

RUN (from the ai-review-trends folder; pandas, numpy, matplotlib only; about a minute)
  python mixture_estimation\\scripts\\05_validate.py
  python mixture_estimation\\scripts\\05_validate.py --reps 100      # quicker
Outputs go to mixture_estimation/results/.
"""
import argparse
import html
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "results"
GRID = np.linspace(0, 1, 1001)
WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


# ------------------------------------------------------------------ text -> sentences -> word sets
def clean(text):
    return html.unescape(str(text)) if pd.notna(text) else ""


def sentences(text, min_words=3):
    """Sentences with at least min_words words, each as a set of lowercase words."""
    out = []
    for s in SPLIT.split(clean(text)):
        words = WORD.findall(s.lower())
        if len(words) >= min_words:
            out.append(set(words))
    return out


def all_sentences(texts):
    return [s for t in texts for s in sentences(t)]


# ------------------------------------------------------------------ estimator
class Estimator:
    def __init__(self, human_texts, ai_texts, min_docs=3, smooth=0.5):
        h, a = all_sentences(human_texts), all_sentences(ai_texts)
        ch, ca = Counter(w for s in h for w in s), Counter(w for s in a for w in s)
        # words seen in at least min_docs sentences on each side
        self.vocab = sorted(w for w in set(ch) | set(ca) if ch[w] >= min_docs and ca[w] >= min_docs)
        self.idx = {w: i for i, w in enumerate(self.vocab)}
        p = np.array([(ch[w] + smooth) / (len(h) + 2 * smooth) for w in self.vocab])
        q = np.array([(ca[w] + smooth) / (len(a) + 2 * smooth) for w in self.vocab])
        self.dp, self.dq = np.log(p) - np.log1p(-p), np.log(q) - np.log1p(-q)
        self.bp, self.bq = np.log1p(-p).sum(), np.log1p(-q).sum()
        self.n_human_sent, self.n_ai_sent = len(h), len(a)

    def loglik(self, sents):
        """(log P(s), log Q(s)) for each sentence."""
        lp, lq = np.empty(len(sents)), np.empty(len(sents))
        for k, s in enumerate(sents):
            ids = [self.idx[w] for w in s if w in self.idx]
            lp[k], lq[k] = self.bp + self.dp[ids].sum(), self.bq + self.dq[ids].sum()
        return lp, lq

    @staticmethod
    def mle(lp, lq):
        if len(lp) == 0:
            return np.nan
        a = GRID[:, None]
        with np.errstate(divide="ignore"):
            ll = np.logaddexp(np.log1p(-a) + lp, np.log(a) + lq).sum(axis=1)
        return float(GRID[np.argmax(ll)])

    def estimate(self, texts, n_boot=300, seed=0):
        """alpha with a bootstrap 95% interval (resampling REVIEWS, not sentences)."""
        per_review = [self.loglik(sentences(t)) for t in texts]
        per_review = [x for x in per_review if len(x[0])]
        if not per_review:
            return np.nan, np.nan, np.nan, 0
        lp = np.concatenate([x[0] for x in per_review]); lq = np.concatenate([x[1] for x in per_review])
        est = self.mle(lp, lq)
        rng, boots = np.random.default_rng(seed), []
        for _ in range(n_boot):
            pick = rng.integers(0, len(per_review), len(per_review))
            boots.append(self.mle(np.concatenate([per_review[i][0] for i in pick]),
                                  np.concatenate([per_review[i][1] for i in pick])))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        return est, lo, hi, len(lp)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=300, help="random test mixes per AI share")
    ap.add_argument("--mix-size", type=int, default=250, help="reviews in each test mix")
    ap.add_argument("--min-docs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    read = lambda f: pd.read_csv(DATA / f, dtype={"review_id": str})

    h_ref, h_val = read("human_reference.csv"), read("human_validation.csv")
    ai_ref, ai_val = read("pilot_ai_reference.csv"), read("pilot_ai_validation.csv")
    src_val = set(read("pilot_human_validation.csv").review_id)
    h_pool = h_val[~h_val.review_id.isin(src_val)]          # human test reviews: never an AI source
    print(f"P from {len(h_ref)} human reviews, Q from {len(ai_ref)} AI reviews")
    print(f"Test pool: {len(h_pool)} held-out human reviews + {len(ai_val)} held-out AI reviews")

    est = Estimator(h_ref.translated_review_en, ai_ref.translated_review_en, args.min_docs)
    print(f"Vocabulary: {len(est.vocab)} words  (sentences: human {est.n_human_sent}, AI {est.n_ai_sent})")

    # sentence log-likelihoods per review, computed once
    def per_review(texts):
        return [est.loglik(sentences(t)) for t in texts]
    H, A = per_review(h_pool.translated_review_en), per_review(ai_val.translated_review_en)

    # ---------------- 1. sanity: pure human and pure AI
    cat = lambda xs: (np.concatenate([x[0] for x in xs]), np.concatenate([x[1] for x in xs]))
    pure_h, pure_a = est.mle(*cat(H)), est.mle(*cat(A))
    print(f"\nSanity checks: all-human test pool -> {pure_h:.1%} AI (should be ~0%),"
          f" all-AI test set -> {pure_a:.1%} AI (should be ~100%)")

    # ---------------- 2. known-share mixes
    rng, rows = np.random.default_rng(args.seed), []
    for target in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]:
        n_ai = int(round(target * args.mix_size))
        n_h = args.mix_size - n_ai
        if n_ai > len(A) or n_h > len(H):
            print(f"  skip {target:.0%}: not enough reviews"); continue
        for r in range(args.reps):
            hi = rng.choice(len(H), n_h, replace=False)
            ai = rng.choice(len(A), n_ai, replace=False)
            parts = [H[i] for i in hi] + [A[i] for i in ai]
            lp, lq = cat(parts)
            ai_sent = sum(len(A[i][0]) for i in ai)
            rows.append(dict(target_review_share=target, true_sentence_share=ai_sent / len(lp),
                             estimate=est.mle(lp, lq)))
    v = pd.DataFrame(rows)
    v["error"] = v.estimate - v.true_sentence_share
    s = v.groupby("target_review_share").agg(
        true_sentence_share=("true_sentence_share", "mean"), mean_estimate=("estimate", "mean"),
        p5=("estimate", lambda x: x.quantile(.05)), p95=("estimate", lambda x: x.quantile(.95)),
        mean_error=("error", "mean"), mean_abs_error=("error", lambda x: x.abs().mean())).reset_index()
    s.to_csv(OUT / "validation_summary.csv", index=False)
    v.to_csv(OUT / "validation_runs.csv", index=False)
    print("\nVALIDATION (estimates are shares of sentences; 'true' = real share of AI sentences in the mix)")
    print((s.set_index("target_review_share") * 100).round(1).to_string())

    # ---------------- 3. real data
    real = read("source_reviews_clean.csv")
    real["text"] = np.where(real.text_source == "translated", real.translated_review_en, real.review_text)
    ref_ids = set(h_ref.review_id)
    groups = [("pre_2022 (held out)", real[(real.period == "pre_2022") & ~real.review_id.isin(ref_ids)]),
              ("2022", real[real.period == "2022"]), ("post_2022", real[real.period == "post_2022"])]
    res = []
    for platform in [None, "Daraz", "Rokomari", "Shajgoj"]:
        for name, g in groups:
            g = g if platform is None else g[g.platform == platform]
            a, lo, hi, n_sent = est.estimate(g.text, seed=args.seed)
            res.append(dict(platform=platform or "All", period=name, reviews=len(g), sentences=n_sent,
                            ai_share=a, ci_low=lo, ci_high=hi))
    res = pd.DataFrame(res)
    res.to_csv(OUT / "real_data_estimates.csv", index=False)
    show = res.copy()
    for c in ["ai_share", "ci_low", "ci_high"]:
        show[c] = (show[c] * 100).round(1)
    print("\nREAL DATA (share of AI sentences, 95% bootstrap interval)")
    print(show.to_string(index=False))

    # ---------------- chart
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5.4, 4.4))
    lim = max(s.p95.max(), s.true_sentence_share.max()) * 100 + 3
    ax.plot([0, lim], [0, lim], ls="--", color="#999", lw=1, label="perfect estimate")
    ax.errorbar(s.true_sentence_share * 100, s.mean_estimate * 100,
                yerr=[(s.mean_estimate - s.p5) * 100, (s.p95 - s.mean_estimate) * 100],
                fmt="o", color="#1f6fb4", capsize=4, label="estimate (mean, 5-95% of mixes)")
    ax.set_xlabel("True AI share in the mix (% of sentences)")
    ax.set_ylabel("Estimated AI share (%)")
    ax.set_title(f"Validation on held-out pre-2022 reviews ({args.reps} mixes each)", fontsize=10)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "validation_chart.png", dpi=160)
    print(f"\nSaved results to {OUT}")


if __name__ == "__main__":
    main()

"""
Validate the distributional AI-share estimator (Liang et al. 2024, arXiv:2403.07183) on our reviews,
then apply it to the real data.

Validation design: held-out pre-ChatGPT (human) reviews are mixed with a known share of AI reviews
(0-25%) and the estimate is compared with the true share. The estimator is applied to 2022 and post-2022
reviews only to the extent that it recovers these known shares.

Data (in ../data, from earlier steps):
  human_reference.csv     pre-2022 human reviews  -> learn the HUMAN word distribution P
  ai_reference.csv        one AI review per human_reference review -> learn the AI distribution Q
                          (pilot mode: pilot_ai_reference.csv)
  human_validation.csv    held-out pre-2022 human reviews -> the human part of each test mix
  ai_validation.csv       held-out AI reviews -> the AI part of each test mix (pilot: pilot_ai_validation.csv)
  source_reviews_clean.csv  all real reviews -> real-data estimates
A test mix never contains the human review that one of its AI reviews was made from.

Method (as in the paper): reviews are split into sentences (>= 3 words); each sentence becomes the SET
of its words of the chosen kind (default: adjectives + adverbs, like the paper's adjective setting; this
also drops product/topic words such as "earphone" or "novel"). p_t / q_t = share of human / AI sentences
containing word t. A sentence's likelihood under P is prod_t (p_t if t in sentence else 1 - p_t), same for Q.
alpha maximises sum_s log((1 - alpha) P(s) + alpha Q(s)). alpha is a share of SENTENCES, so the truth we
compare it with is the share of AI sentences in the mix.

By default P and Q are fitted SEPARATELY FOR EACH PLATFORM (like the paper, which fits each venue on its
own). With one pooled fit, short generic Daraz reviews looked ~30% "AI" even before 2022, because P was
dominated by long Rokomari book reviews.

What it reports (results/<run>/)
  1. validation for each platform: known AI shares 0/10/20% mixed into held-out pre-2022 reviews
     (validation_summary.csv, validation_chart.png)
  2. real data per platform and period, for ALL reviews and for SAME-PRODUCT reviews only (products that
     also have pre-2022 reviews); "All" = platforms weighted by sentences  (real_data_estimates.csv)
  3. the CHANGE after-2022 minus before-2022 within each platform, same products only, with a bootstrap
     95% interval (real_data_change.csv). A platform's own bias is in both periods, so the change is
     more trustworthy than the levels.

RUN (from the ai-review-trends folder)
  pip install spacy
  python -m spacy download en_core_web_sm          # once, for --words adjadv / adj
  python mixture_estimation\\scripts\\05_validate.py --full                 # full set, adjectives+adverbs
  python mixture_estimation\\scripts\\05_validate.py --full --words all     # every word (old setting)
  python mixture_estimation\\scripts\\05_validate.py                        # pilot set
  python mixture_estimation\\scripts\\05_validate.py --full --fit pooled  # one model for all platforms
Outputs go to mixture_estimation/results/<full|pilot>_<words>_<fit>/.
"""
import argparse
import html
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "results"
GRID = np.linspace(0, 1, 1001)
WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
POS_SETS = {"adjadv": {"ADJ", "ADV"}, "adj": {"ADJ"}, "all": None}
PLATFORMS = ["Daraz", "Rokomari", "Shajgoj"]


# ------------------------------------------------------------------ text -> sentences -> word sets
def clean(text):
    return html.unescape(str(text)) if pd.notna(text) else ""


class Sentencizer:
    """Turns a review into a list of word sets (one per sentence), keeping only the chosen word kinds.
    Results are cached, so every text is tagged once."""

    def __init__(self, words, min_words=3):
        self.pos = POS_SETS[words]
        self.min_words = min_words
        self.cache = {}
        self.nlp = None
        if self.pos is not None:
            try:
                import spacy
                self.nlp = spacy.load("en_core_web_sm", disable=["ner", "parser", "lemmatizer"])
            except (ImportError, OSError):
                sys.exit("This setting needs spaCy and its English model. Run once:\n"
                         "  pip install spacy\n  python -m spacy download en_core_web_sm\n"
                         "(or use --words all)")

    def raw_sentences(self, text):
        return [s for s in SPLIT.split(clean(text)) if len(WORD.findall(s.lower())) >= self.min_words]

    def prepare(self, texts):
        """Tag many texts at once (much faster than one by one)."""
        todo = list({clean(t) for t in texts if clean(t) not in self.cache})
        if self.pos is None:
            for t in todo:
                self.cache[t] = [set(WORD.findall(s.lower())) for s in self.raw_sentences(t)]
            return
        flat, owner = [], []
        for t in todo:
            ss = self.raw_sentences(t)
            self.cache[t] = []
            flat += ss
            owner += [t] * len(ss)
        for t, doc in zip(owner, self.nlp.pipe(flat, batch_size=256)):
            self.cache[t].append({tok.lower_ for tok in doc if tok.pos_ in self.pos and WORD.fullmatch(tok.lower_)})

    def __call__(self, text):
        t = clean(text)
        if t not in self.cache:
            self.prepare([t])
        return self.cache[t]


# ------------------------------------------------------------------ estimator
class Estimator:
    def __init__(self, sent, human_texts, ai_texts, min_docs=3, smooth=0.5):
        self.sent = sent
        h = [s for t in human_texts for s in sent(t)]
        a = [s for t in ai_texts for s in sent(t)]
        ch, ca = Counter(w for s in h for w in s), Counter(w for s in a for w in s)
        # words seen in at least min_docs sentences on each side
        self.vocab = sorted(w for w in set(ch) | set(ca) if ch[w] >= min_docs and ca[w] >= min_docs)
        self.idx = {w: i for i, w in enumerate(self.vocab)}
        p = np.array([(ch[w] + smooth) / (len(h) + 2 * smooth) for w in self.vocab])
        q = np.array([(ca[w] + smooth) / (len(a) + 2 * smooth) for w in self.vocab])
        self.dp, self.dq = np.log(p) - np.log1p(-p), np.log(q) - np.log1p(-q)
        self.bp, self.bq = np.log1p(-p).sum(), np.log1p(-q).sum()
        self.n_human_sent, self.n_ai_sent = len(h), len(a)

    def review_loglik(self, text):
        """(log P(s), log Q(s)) for each sentence of one review."""
        sents = self.sent(text)
        lp, lq = np.empty(len(sents)), np.empty(len(sents))
        for k, s in enumerate(sents):
            ids = [self.idx[w] for w in s if w in self.idx]
            lp[k], lq[k] = self.bp + self.dp[ids].sum(), self.bq + self.dq[ids].sum()
        return lp, lq

    def per_review(self, texts):
        return [self.review_loglik(t) for t in texts]

    @staticmethod
    def mle(parts):
        parts = [x for x in parts if len(x[0])]
        if not parts:
            return np.nan
        lp = np.concatenate([x[0] for x in parts]); lq = np.concatenate([x[1] for x in parts])
        a = GRID[:, None]
        with np.errstate(divide="ignore"):
            ll = np.logaddexp(np.log1p(-a) + lp, np.log(a) + lq).sum(axis=1)
        return float(GRID[np.argmax(ll)])

    def bootstrap(self, texts, n_boot, rng):
        """Point estimate and bootstrap draws (resampling REVIEWS)."""
        parts = [x for x in self.per_review(texts) if len(x[0])]
        if not parts:
            return np.nan, np.array([np.nan]), 0, 0
        boots = np.array([self.mle([parts[i] for i in rng.integers(0, len(parts), len(parts))])
                          for _ in range(n_boot)])
        return self.mle(parts), boots, len(parts), sum(len(x[0]) for x in parts)


# ------------------------------------------------------------------ validation
def validate(est, h_pool, ai_val, targets, mix_size, reps, rng):
    """Mixes of held-out human + AI reviews at known shares. Returns one row per mix."""
    H, A = est.per_review(h_pool.text), est.per_review(ai_val.text)
    h_ids, a_ids = h_pool.review_id.to_numpy(), ai_val.review_id.to_numpy()
    rows = []
    for target in targets:
        n_ai = int(round(target * mix_size))
        n_h = mix_size - n_ai
        if n_ai > len(A) or n_h > len(H) - n_ai:
            continue
        for _ in range(reps):
            ai = rng.choice(len(A), n_ai, replace=False)
            allowed = np.flatnonzero(~np.isin(h_ids, a_ids[ai]))   # never a review next to its AI twin
            hi = rng.choice(allowed, n_h, replace=False)
            parts = [H[i] for i in hi] + [A[i] for i in ai]
            n_sent = sum(len(x[0]) for x in parts)
            ai_sent = sum(len(A[i][0]) for i in ai)
            rows.append(dict(target_review_share=target, true_sentence_share=ai_sent / max(n_sent, 1),
                             estimate=est.mle(parts)))
    v = pd.DataFrame(rows)
    v["error"] = v.estimate - v.true_sentence_share
    return v


def summarise(v, by):
    return v.groupby(by).agg(
        true_sentence_share=("true_sentence_share", "mean"), mean_estimate=("estimate", "mean"),
        p5=("estimate", lambda x: x.quantile(.05)), p95=("estimate", lambda x: x.quantile(.95)),
        mean_error=("error", "mean"), mean_abs_error=("error", lambda x: x.abs().mean())).reset_index()


def pct(df, cols):
    df = df.copy()
    for c in cols:
        df[c] = (df[c] * 100).round(1)
    return df


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="use ai_*.csv (all reviews) instead of the pilot")
    ap.add_argument("--words", choices=list(POS_SETS), default="adjadv",
                    help="adjadv = adjectives+adverbs (default), adj = adjectives, all = every word")
    ap.add_argument("--reps", type=int, default=300, help="random test mixes per AI share")
    ap.add_argument("--mix-size", type=int, default=250, help="reviews in each overall test mix")
    ap.add_argument("--platform-mix-size", type=int, default=100, help="reviews in each per-platform mix")
    ap.add_argument("--boot", type=int, default=300, help="bootstrap rounds for real-data intervals")
    ap.add_argument("--fit", choices=["per-platform", "pooled"], default="per-platform",
                    help="per-platform: separate P and Q for each platform (default); pooled: one for all")
    ap.add_argument("--min-docs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    prefix = "ai" if args.full else "pilot_ai"
    out = OUT / f"{'full' if args.full else 'pilot'}_{args.words}_{args.fit}"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    read = lambda f: pd.read_csv(DATA / f, dtype={"review_id": str, "product_id": str})

    # ---------------- data
    h_ref, h_val = read("human_reference.csv"), read("human_validation.csv")
    ai_ref, ai_val = read(f"{prefix}_reference.csv"), read(f"{prefix}_validation.csv")
    for d in (h_ref, h_val, ai_ref, ai_val):
        d["text"] = d.translated_review_en.fillna("")
    for name, d in [("reference", ai_ref), ("validation", ai_val)]:
        missing = (d.text.str.strip() == "").sum()
        if missing:
            print(f"WARNING: {missing} AI {name} reviews have no English text yet - run 04_translate_ai.py"
                  f"{' --full' if args.full else ''} first. They are left out.")
    ai_ref, ai_val = ai_ref[ai_ref.text.str.strip() != ""], ai_val[ai_val.text.str.strip() != ""]
    real = read("source_reviews_clean.csv")
    real["text"] = np.where(real.text_source == "translated", real.translated_review_en, real.review_text)
    real["text"] = real["text"].fillna("")

    sent = Sentencizer(args.words)
    print(f"Preparing sentences ({args.words}) ...")
    sent.prepare(pd.concat([h_ref.text, h_val.text, ai_ref.text, ai_val.text, real.text]))

    # one estimator per platform (default; the paper fits each venue separately) or one pooled estimator
    groups = PLATFORMS if args.fit == "per-platform" else ["All"]
    sel = lambda d, g: d if g == "All" else d[d.platform == g]
    ests = {}
    for g in groups:
        ests[g] = Estimator(sent, sel(h_ref, g).text, sel(ai_ref, g).text, args.min_docs)
        e = ests[g]
        print(f"[{g}] P from {len(sel(h_ref, g))} human reviews, Q from {len(sel(ai_ref, g))} AI reviews; "
              f"vocabulary {len(e.vocab)} words; held-out human -> {e.mle(e.per_review(sel(h_val, g).text)):.1%} AI "
              f"(should be ~0%), held-out AI -> {e.mle(e.per_review(sel(ai_val, g).text)):.1%} (should be ~100%)")
    est_for = lambda p: ests[p] if p in ests else ests["All"]

    # ---------------- 1. validation for each platform (and pooled, if fitted pooled)
    rows = []
    checks = PLATFORMS + (["All"] if args.fit == "pooled" else [])
    for p in checks:
        size = args.mix_size if p == "All" else args.platform_mix_size
        tg = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25] if p == "All" else [0.0, 0.10, 0.20]
        vp = validate(est_for(p), sel(h_val, p), sel(ai_val, p), tg, size, args.reps, rng)
        if len(vp):
            vp.assign(platform=p).to_csv(out / f"validation_runs_{p}.csv", index=False)
            rows.append(summarise(vp, "target_review_share").assign(platform=p, mix_size=size))
    bp = pd.concat(rows)[["platform", "mix_size", "target_review_share", "true_sentence_share", "mean_estimate",
                          "p5", "p95", "mean_error", "mean_abs_error"]]
    bp.to_csv(out / "validation_summary.csv", index=False)
    print(f"\n1. VALIDATION ({args.fit} fit, {args.reps} mixes each; % of sentences; mean_error = bias)")
    print(pct(bp, bp.columns[2:]).to_string(index=False))

    # ---------------- 2. real data per platform, all reviews and same products
    ref_ids = set(h_ref.review_id)
    pre_products = set(real[real.period == "pre_2022"].product_id)
    periods = [("pre_2022 (held out)", (real.period == "pre_2022") & ~real.review_id.isin(ref_ids)),
               ("2022", real.period == "2022"), ("post_2022", real.period == "post_2022")]
    res, boots = [], {}
    for subset in ["all reviews", "same products"]:
        base = real if subset == "all reviews" else real[real.product_id.isin(pre_products)]
        for name, mask in periods:
            per_p = {}
            for p in PLATFORMS:
                g = base[mask.reindex(base.index)]
                g = g[g.platform == p]
                a, b, n_rev, n_sent = est_for(p).bootstrap(g.text, args.boot, rng)
                per_p[p] = (a, b, n_rev, n_sent)
            # "All" = the platforms' AI shares weighted by their number of sentences
            w = np.array([per_p[p][3] for p in PLATFORMS], float)
            ok = w > 0
            a_all = np.nansum([per_p[p][0] * w[i] for i, p in enumerate(PLATFORMS) if ok[i]]) / w[ok].sum()
            b_all = sum(per_p[p][1] * w[i] for i, p in enumerate(PLATFORMS) if ok[i]) / w[ok].sum()
            per_p["All"] = (a_all, b_all, sum(per_p[p][2] for p in PLATFORMS), int(w.sum()))
            for p in ["All"] + PLATFORMS:
                a, b, n_rev, n_sent = per_p[p]
                boots[(subset, p, name)] = b
                lo, hi = np.nanpercentile(b, [2.5, 97.5]) if n_rev else (np.nan, np.nan)
                res.append(dict(subset=subset, platform=p, period=name, reviews=n_rev, sentences=n_sent,
                                ai_share=a, ci_low=lo, ci_high=hi))
    res = pd.DataFrame(res).sort_values(["subset", "platform"], kind="stable")
    res.to_csv(out / "real_data_estimates.csv", index=False)
    print("\n2. REAL DATA (share of AI sentences, 95% bootstrap interval)")
    print(pct(res, ["ai_share", "ci_low", "ci_high"]).to_string(index=False))

    # ---------------- 3. change after-2022 minus before-2022, same products, within platform
    ch = []
    for p in ["All"] + PLATFORMS:
        r = res[(res.subset == "same products") & (res.platform == p)].set_index("period")
        for later in ["2022", "post_2022"]:
            d = boots[("same products", p, later)] - boots[("same products", p, "pre_2022 (held out)")]
            lo, hi = np.nanpercentile(d, [2.5, 97.5])
            ch.append(dict(platform=p, comparison=f"{later} minus pre_2022",
                           change=r.ai_share[later] - r.ai_share["pre_2022 (held out)"], ci_low=lo, ci_high=hi,
                           clear_increase=bool(lo > 0)))
    ch = pd.DataFrame(ch)
    ch.to_csv(out / "real_data_change.csv", index=False)
    print("\n3. CHANGE vs before 2022 (same products, within platform; percentage points)")
    print(pct(ch, ["change", "ci_low", "ci_high"]).to_string(index=False))

    # ---------------- chart
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = list(bp.platform.unique())
    fig, axes = plt.subplots(1, len(panels), figsize=(3.6 * len(panels), 3.8), sharey=True)
    colors = {"Daraz": "#e8743b", "Rokomari": "#2a9d8f", "Shajgoj": "#8e6cc9", "All": "#1f6fb4"}
    for ax, p in zip(np.atleast_1d(axes), panels):
        g = bp[bp.platform == p]
        lim = max(g.p95.max(), g.true_sentence_share.max()) * 100 + 3
        ax.plot([0, lim], [0, lim], ls="--", color="#999", lw=1, label="perfect")
        ax.errorbar(g.true_sentence_share * 100, g.mean_estimate * 100,
                    yerr=[(g.mean_estimate - g.p5) * 100, (g.p95 - g.mean_estimate) * 100],
                    fmt="o", color=colors[p], capsize=4, label="mean, 5-95% of mixes")
        ax.set_title(f"{p} ({int(g.mix_size.iloc[0])}-review mixes)", fontsize=10)
        ax.set_xlabel("True AI share (% of sentences)")
    np.atleast_1d(axes)[0].set_ylabel("Estimated AI share (%)")
    np.atleast_1d(axes)[0].legend(frameon=False, fontsize=8)
    fig.suptitle(f"Validation on held-out pre-2022 reviews ({args.fit} fit, {args.words})", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "validation_chart.png", dpi=160)
    print(f"\nSaved results to {out}")


if __name__ == "__main__":
    main()

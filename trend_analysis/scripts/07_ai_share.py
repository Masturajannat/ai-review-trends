"""
Estimate the share of AI-generated reviews from the marker-word rates, and validate the estimate on
mixtures with a known AI share.

If a share alpha of reviews is AI-generated, the expected share of reviews containing an evaluative
marker word is

    m = (1 - alpha) * h + alpha * a

where h is the marker rate in human reviews and a the marker rate in AI reviews. Hence

    alpha = (m - h) / (a - h)

  h : pre-ChatGPT reviews of the same platform and language, excluding the discovery half used to
      choose the markers
  a : AI reference reviews of the same language that were NOT used to choose the markers (held-out
      half); platform-specific when at least MIN_AI held-out AI reviews exist, otherwise all platforms
  m : post-ChatGPT reviews

Banglish words are spelling-normalised (textutil.tokens(..., normalize=True)) for all three rates.

Validation (the known-mixture test). For each series, the held-out human baseline and the held-out AI
reviews are each split at random into two halves. One half of each gives h and a; the other halves
are mixed with a known AI share (0%, 5%, 10%, 20%) into a sample of the same size as the series'
post-ChatGPT sample, and alpha is estimated. Repeated REPS times, this shows the bias and the spread of
the estimate at the sample sizes we actually have.

Outputs (trend_analysis/results/)
  ai_share_validation.csv   per series and true share: mean estimate, 5th-95th percentile, bias
  ai_share_estimates.csv    estimated AI share after ChatGPT with bootstrap 95% CI and upper bound,
                            plus the placebo estimate (Jan-Nov 2022 against pre-2022) and the number of
                            reviews per period needed for a 95% interval of +/- 10 percentage points
  fig_ai_share.png

Run from the repository root:  python trend_analysis/scripts/07_ai_share.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import textutil as tu  # noqa: E402

ROOT = HERE.parents[1]
TA = ROOT / "trend_analysis"
OUT = TA / "results"
REF_SPLIT = ROOT / "archive" / "week5_mixture_translated" / "data" / "human_reference.csv"
MIN_REVIEWS = 30
MIN_AI = 40
TRUE_SHARES = [0.0, 0.05, 0.10, 0.20]
REPS = 1000
BOOT = 2000
COLORS = {"Daraz": "#2a78d6", "Rokomari": "#eb6834", "Shajgoj": "#1baf7a"}


def marker_flags(texts, language, words):
    return np.array([float(bool(words & set(tu.tokens(t, language, normalize=True)))) for t in texts])


def alpha(m, h, a):
    return (m - h) / (a - h) if a - h > 0.05 else np.nan


def reviews_needed(h, m, a, n_ai, half_width=0.10):
    """Reviews needed in EACH period (pre and post, equal sizes) so that the 95% interval of alpha is
    about +/- half_width, from the normal approximation of the variance of (m - h) / (a - h)."""
    d = a - h
    if d <= 0.05:
        return np.nan
    var_a = a * (1 - a) / n_ai * ((m - h) / d) ** 2       # contribution of the AI rate
    target = (half_width / 1.96 * d) ** 2 - var_a
    if target <= 0:
        return np.nan
    return int(np.ceil((h * (1 - h) + m * (1 - m)) / target))


def load():
    ref_ids = set(pd.read_csv(REF_SPLIT, dtype={"review_id": str}).review_id)
    rev = pd.read_csv(TA / "data" / "reviews_all.csv", encoding="utf-8-sig", dtype={"review_id": str})
    rev = rev[rev.keep & rev.language.isin(["bangla", "banglish", "english"])]
    rev = rev[~((rev.period_detail == "pre_2022") & rev.review_id.isin(ref_ids))]   # drop discovery half
    ai = pd.read_csv(TA / "data" / "ai_reference_original.csv", encoding="utf-8-sig",
                     dtype={"source_review_id": str})
    ai = ai[ai.keep & ~ai.source_review_id.isin(ref_ids)]                            # held-out AI only
    markers = pd.read_csv(TA / "markers.csv")
    return rev, ai, markers


def main():
    rng = np.random.default_rng(42)
    rev, ai, markers = load()
    val_rows, est_rows = [], []
    series = []
    for (p, lang), s in rev.groupby(["platform", "language"]):
        pre, post = s[s.period == "pre_chatgpt"], s[s.period == "post_chatgpt"]
        if len(pre) < MIN_REVIEWS or len(post) < MIN_REVIEWS:
            continue
        words = set(markers[(markers.language == lang) & (markers.group == "evaluative")].word)
        a_pool = ai[(ai.language == lang) & (ai.platform == p)]
        ai_source = p
        if len(a_pool) < MIN_AI:
            a_pool, ai_source = ai[ai.language == lang], "all platforms"
        H = marker_flags(pre.text_clean, lang, words)
        A = marker_flags(a_pool.text_clean, lang, words)
        M = marker_flags(post.text_clean, lang, words)
        series.append((p, lang))

        # ---------------- validation: known mixtures
        for true in TRUE_SHARES:
            ests = []
            for _ in range(REPS):
                hp, ap = rng.permutation(len(H)), rng.permutation(len(A))
                h_fit, h_mix = H[hp[: len(H) // 2]], H[hp[len(H) // 2:]]
                a_fit, a_mix = A[ap[: len(A) // 2]], A[ap[len(A) // 2:]]
                n_ai = rng.binomial(len(M), true)
                mix = np.concatenate([rng.choice(h_mix, len(M) - n_ai), rng.choice(a_mix, n_ai)])
                ests.append(alpha(mix.mean(), h_fit.mean(), a_fit.mean()))
            ests = np.array(ests)
            val_rows.append(dict(platform=p, language=lang, true_share=true, mix_size=len(M),
                                 mean_estimate=np.nanmean(ests), p5=np.nanpercentile(ests, 5),
                                 p95=np.nanpercentile(ests, 95), bias=np.nanmean(ests) - true))

        # ---------------- estimate on real data, with bootstrap
        def boot_alpha(m_arr, h_arr):
            b = np.array([alpha(m_arr[rng.integers(0, len(m_arr), len(m_arr))].mean(),
                                h_arr[rng.integers(0, len(h_arr), len(h_arr))].mean(),
                                A[rng.integers(0, len(A), len(A))].mean()) for _ in range(BOOT)])
            return b
        b = boot_alpha(M, H)
        lo, hi = np.nanpercentile(b, [2.5, 97.5])
        row = dict(platform=p, language=lang, ai_rate_from=ai_source, ai_reviews=len(A),
                   human_rate=H.mean(), ai_rate=A.mean(), post_rate=M.mean(),
                   pre_reviews=len(H), post_reviews=len(M),
                   ai_share=alpha(M.mean(), H.mean(), A.mean()), ci_low=lo, ci_high=hi,
                   upper_95=np.nanpercentile(b, 95),
                   reviews_needed_pm10=reviews_needed(H.mean(), M.mean(), A.mean(), len(A)))
        # placebo: Jan-Nov 2022 against pre-2022 (both before ChatGPT; should be about 0)
        P0 = marker_flags(pre[pre.period_detail == "pre_2022"].text_clean, lang, words)
        P1 = marker_flags(pre[pre.period_detail == "jan_nov_2022"].text_clean, lang, words)
        if len(P0) >= 10 and len(P1) >= 10:
            bp = boot_alpha(P1, P0)
            row.update(placebo_share=alpha(P1.mean(), P0.mean(), A.mean()),
                       placebo_ci_low=np.nanpercentile(bp, 2.5), placebo_ci_high=np.nanpercentile(bp, 97.5),
                       placebo_reviews=len(P1))
        est_rows.append(row)

    val, est = pd.DataFrame(val_rows), pd.DataFrame(est_rows)
    val.to_csv(OUT / "ai_share_validation.csv", index=False)
    est.to_csv(OUT / "ai_share_estimates.csv", index=False)
    pct = lambda d, cols: d.assign(**{c: (d[c] * 100).round(1) for c in cols if c in d})
    print("VALIDATION: estimated AI share for mixtures with a known share (%), at each series' sample size")
    print(pct(val, ["true_share", "mean_estimate", "p5", "p95", "bias"]).to_string(index=False))
    print("\nESTIMATED AI SHARE AFTER ChatGPT (%)")
    cols = ["platform", "language", "pre_reviews", "post_reviews", "human_rate", "ai_rate", "post_rate",
            "ai_share", "ci_low", "ci_high", "upper_95", "placebo_share", "placebo_ci_low", "placebo_ci_high",
            "reviews_needed_pm10"]
    print(pct(est, cols[4:-1])[[c for c in cols if c in est]].to_string(index=False))
    plot(series, val, est)
    print(f"\nSaved to {OUT}")


def plot(series, val, est):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.color": "#e6e5e1", "axes.axisbelow": True, "font.size": 9})
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axs[0]
    ax.plot([0, 22], [0, 22], "--", color="#999", lw=1, label="perfect estimate")
    for i, (p, lang) in enumerate(series):
        g = val[(val.platform == p) & (val.language == lang)]
        x = g.true_share * 100 + (i - len(series) / 2) * 0.35
        style = "o-" if lang == "bangla" else "s-" if lang == "banglish" else "^-"
        ax.errorbar(x, g.mean_estimate * 100, yerr=[(g.mean_estimate - g.p5) * 100, (g.p95 - g.mean_estimate) * 100],
                    fmt=style, color=COLORS[p], capsize=2, lw=1, ms=4,
                    label=f"{p} - {lang} (n={int(g.mix_size.iloc[0])})")
    ax.set_xlabel("True AI share in the mixture (%)")
    ax.set_ylabel("Estimated AI share (%)")
    ax.set_title("Validation on known mixtures (mean and 5th-95th percentile)", loc="left", fontsize=9)
    ax.legend(frameon=False, fontsize=7.5)
    ax = axs[1]
    y = np.arange(len(est))
    ax.axvline(0, color="#999", lw=1)
    for i, r in enumerate(est.itertuples()):
        ax.errorbar(r.ai_share * 100, i, xerr=[[(r.ai_share - r.ci_low) * 100], [(r.ci_high - r.ai_share) * 100]],
                    fmt="o", color=COLORS[r.platform], capsize=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r.platform} - {r.language}" for r in est.itertuples()])
    ax.invert_yaxis()
    ax.set_xlabel("Estimated AI share of post-ChatGPT reviews (%)")
    ax.set_title("Estimate with 95% bootstrap interval", loc="left", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_ai_share.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()

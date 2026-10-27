"""
Track AI-associated marker words over time, separately for each platform and language.

Inputs : trend_analysis/data/reviews_all.csv, trend_analysis/markers.csv,
         trend_analysis/results/control_words.csv (from 03_marker_words.py)
Outputs: trend_analysis/results/
  trend_series.csv        which platform-language series are analysed, with review counts
  trend_periods.csv       per series and period: share of reviews with a marker, markers per 100 words
  trend_changes.csv       post-ChatGPT minus pre-ChatGPT with bootstrap 95% CI, for all reviews and for the
                          robustness subsets, plus the placebo comparison (Jan-Nov 2022 minus pre-2022)
  trend_halfyear.csv      share of reviews with a marker by half-year
  word_shift.csv          each marker word: share of reviews containing it, pre-2022 vs post-ChatGPT
  fig_trend_halfyear.png, fig_period_comparison.png, fig_word_shift.png

Design
  * Two periods, split at ChatGPT's release on 30 Nov 2022: pre_chatgpt and post_chatgpt.
  * Baseline = pre-ChatGPT reviews, excluding the discovery half of the pre-2022 reviews. That half was
    used to choose the marker words, so including it would bias the baseline downwards.
  * Robustness subsets: reviews over 10 and over 25 words; products that also have pre-ChatGPT reviews;
    baseline restricted to pre-2022 (without Jan-Nov 2022).
  * Placebo check: Jan-Nov 2022 minus pre-2022. Both periods are before ChatGPT, so no change is expected;
    a clear difference would indicate drift unrelated to AI.
  * Measures per review: contains at least one evaluative marker (yes/no) and evaluative markers per
    100 words (adjusts for review length). The same is computed for formal markers and control words.
    Control words should not change; if they do, the change is not specific to AI-style language.
  * A series is analysed if it has at least MIN_REVIEWS reviews in both periods.
  * 95% intervals: bootstrap over reviews (BOOT rounds).

Run from the repository root:  python trend_analysis/scripts/04_trends.py
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
PERIODS = ["pre_chatgpt", "post_chatgpt"]
PERIOD_LABEL = {"pre_chatgpt": "Pre-ChatGPT", "post_chatgpt": "Post-ChatGPT",
                "pre_2022": "Pre-2022", "jan_nov_2022": "Jan-Nov 2022"}
MIN_REVIEWS = 30
MIN_HALFYEAR = 10
BOOT = 2000
CHATGPT_RELEASE = pd.Timestamp("2022-11-30")
COLORS = {"Daraz": "#2a78d6", "Rokomari": "#eb6834", "Shajgoj": "#1baf7a"}


def load():
    df = pd.read_csv(TA / "data" / "reviews_all.csv", encoding="utf-8-sig",
                     dtype={"review_id": str, "product_id": str})
    df = df[df.keep & df.language.isin(["bangla", "banglish", "english"])].copy()
    ref_ids = set(pd.read_csv(REF_SPLIT, dtype={"review_id": str}).review_id)
    # drop the discovery half of pre-2022 (used to choose the markers)
    df = df[~((df.period_detail == "pre_2022") & df.review_id.isin(ref_ids))].copy()
    df["date"] = pd.to_datetime(df.date)
    markers = pd.read_csv(TA / "markers.csv")
    controls = pd.read_csv(OUT / "control_words.csv")
    return df, markers, controls


def add_measures(df, markers, controls):
    groups = {"eval": lambda l: markers[(markers.language == l) & (markers.group == "evaluative")].word,
              "formal": lambda l: markers[(markers.language == l) & (markers.group == "formal")].word,
              "control": lambda l: controls[controls.language == l].word}
    for g in groups:
        df[f"has_{g}"], df[f"{g}_per100"] = np.nan, np.nan
    for lang, idx in df.groupby("language").groups.items():
        toks = [tu.tokens(t, lang) for t in df.loc[idx, "text_clean"]]
        n = df.loc[idx, "n_words"].to_numpy()
        for g, get in groups.items():
            words = set(get(lang))
            if not words:
                continue
            hits = np.array([sum(w in words for w in t) for t in toks])
            df.loc[idx, f"has_{g}"] = (hits > 0).astype(float)
            df.loc[idx, f"{g}_per100"] = hits / n * 100
    return df


def boot_mean(x, rng):
    x = np.asarray(x, float)
    return np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(BOOT)])


def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def main():
    rng = np.random.default_rng(42)
    df, markers, controls = load()
    df = add_measures(df, markers, controls)

    # ---------------- series
    cnt = df.groupby(["platform", "language", "period_detail"]).size().unstack(fill_value=0).reindex(
        columns=["pre_2022", "jan_nov_2022", "post_chatgpt"], fill_value=0)
    cnt.insert(2, "pre_chatgpt", cnt.pre_2022 + cnt.jan_nov_2022)
    cnt["analysed"] = (cnt.pre_chatgpt >= MIN_REVIEWS) & (cnt.post_chatgpt >= MIN_REVIEWS)
    cnt.to_csv(OUT / "trend_series.csv")
    series = [s for s, ok in cnt.analysed.items() if ok]
    print("Reviews per series (pre-2022 = held-out half only; pre-ChatGPT = pre-2022 + Jan-Nov 2022):")
    print(cnt.to_string())

    # ---------------- period levels and changes
    measures = ["has_eval", "eval_per100", "has_formal", "has_control", "control_per100"]
    levels, changes = [], []
    main_cmp = ("post_chatgpt - pre_chatgpt", "period", "post_chatgpt", "pre_chatgpt")
    for (p, lang) in series:
        s = df[(df.platform == p) & (df.language == lang)]
        pre_products = set(s[s.period == "pre_chatgpt"].product_id)
        # (subset name, reviews, comparisons as (label, column, value a, value b))
        subsets = [
            ("all", s, [main_cmp]),
            ("words>10", s[s.keep_10], [main_cmp]),
            ("words>25", s[s.keep_25], [main_cmp]),
            ("same products", s[s.product_id.isin(pre_products)], [main_cmp]),
            ("baseline pre-2022 only", s[s.period_detail != "jan_nov_2022"], [main_cmp]),
            ("placebo", s, [("jan_nov_2022 - pre_2022", "period_detail", "jan_nov_2022", "pre_2022")]),
        ]
        for m in measures:
            if s[m].isna().all():
                continue
            for per_col, per in [("period", "pre_chatgpt"), ("period", "post_chatgpt"),
                                 ("period_detail", "pre_2022"), ("period_detail", "jan_nov_2022")]:
                x = s[s[per_col] == per][m].dropna()
                b = boot_mean(x, rng) if len(x) >= 5 else None
                lo, hi = np.percentile(b, [2.5, 97.5]) if b is not None else (np.nan, np.nan)
                levels.append(dict(platform=p, language=lang, measure=m, period=per, reviews=len(x),
                                   value=x.mean() if len(x) else np.nan, ci_low=lo, ci_high=hi))
            for sub_name, g, comparisons in subsets:
                for label, col, a, b_ in comparisons:
                    xa, xb = g[g[col] == a][m].dropna(), g[g[col] == b_][m].dropna()
                    if len(xa) < 5 or len(xb) < 5:
                        continue
                    d = boot_mean(xa, rng) - boot_mean(xb, rng)
                    lo, hi = np.percentile(d, [2.5, 97.5])
                    changes.append(dict(platform=p, language=lang, subset=sub_name, measure=m, comparison=label,
                                        n_a=len(xa), n_b=len(xb), change=xa.mean() - xb.mean(), ci_low=lo,
                                        ci_high=hi,
                                        clear=("increase" if lo > 0 else "decrease" if hi < 0 else "no clear change")))
    levels, changes = pd.DataFrame(levels), pd.DataFrame(changes)
    levels.to_csv(OUT / "trend_periods.csv", index=False)
    changes.to_csv(OUT / "trend_changes.csv", index=False)

    main_tab = changes[changes.subset.isin(["all", "placebo"]) &
                       changes.measure.isin(["has_eval", "has_control"])].copy()
    for c in ["change", "ci_low", "ci_high"]:
        main_tab[c] = (main_tab[c] * 100).round(1)
    print("\nChange in % of reviews containing a marker (has_eval) or a control word (has_control):")
    print(main_tab[["platform", "language", "measure", "comparison", "n_a", "n_b", "change", "ci_low",
                    "ci_high", "clear"]].to_string(index=False))

    # ---------------- half-year trend
    hy = []
    for (p, lang) in series:
        s = df[(df.platform == p) & (df.language == lang)]
        for h, g in s.groupby("half_year"):
            if len(g) < MIN_HALFYEAR:
                continue
            k = int(g.has_eval.sum())
            lo, hi = wilson(k, len(g))
            year, half = int(h[:4]), int(h[-1])
            hy.append(dict(platform=p, language=lang, half_year=h, mid=pd.Timestamp(year, 4 if half == 1 else 10, 1),
                           reviews=len(g), share=k / len(g), ci_low=lo, ci_high=hi,
                           control_share=g.has_control.mean()))
    hy = pd.DataFrame(hy)
    hy.drop(columns="mid").to_csv(OUT / "trend_halfyear.csv", index=False)

    # ---------------- word shift
    ws = []
    for (p, lang) in series:
        s = df[(df.platform == p) & (df.language == lang)]
        pre, post = s[s.period == "pre_chatgpt"], s[s.period == "post_chatgpt"]
        pre_t = [set(tu.tokens(t, lang)) for t in pre.text_clean]
        post_t = [set(tu.tokens(t, lang)) for t in post.text_clean]
        for r in markers[markers.language == lang].itertuples():
            ws.append(dict(platform=p, language=lang, word=r.word, meaning=r.meaning, group=r.group,
                           pre_share=np.mean([r.word in t for t in pre_t]),
                           post_share=np.mean([r.word in t for t in post_t])))
    ws = pd.DataFrame(ws)
    ws.to_csv(OUT / "word_shift.csv", index=False, encoding="utf-8-sig")

    plot(series, hy, levels, ws)
    print(f"\nSaved to {OUT}")


def plot(series, hy, levels, ws):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    # a font with Bengali glyphs, if one is installed (word_shift labels use the English meaning anyway)
    for name in ["Nirmala UI", "Vrinda", "Noto Sans Bengali", "Lohit Bengali"]:
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = ["DejaVu Sans", name]
            break
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.color": "#e6e5e1", "axes.axisbelow": True, "font.size": 9})
    title = lambda p, l: f"{p} - {l.capitalize()}"
    n = len(series)
    cols = min(n, 3)
    rows_ = int(np.ceil(n / cols))

    # 1. half-year trend
    fig, axs = plt.subplots(rows_, cols, figsize=(4.2 * cols, 3.3 * rows_), squeeze=False, sharey=True)
    for ax, (p, lang) in zip(axs.flat, series):
        g = hy[(hy.platform == p) & (hy.language == lang)].sort_values("mid")
        ax.axvline(CHATGPT_RELEASE, color="#888", ls="--", lw=1)
        ax.fill_between(g.mid, g.ci_low * 100, g.ci_high * 100, color=COLORS[p], alpha=.15, lw=0)
        ax.plot(g.mid, g.share * 100, "o-", color=COLORS[p], ms=4, label="AI-marker words")
        ax.plot(g.mid, g.control_share * 100, "s:", color="#777", ms=3, lw=1, label="control words")
        ax.set_title(title(p, lang), loc="left")
        ax.set_ylim(0, 100)
    for ax in axs.flat[n:]:
        ax.axis("off")
    axs[0, 0].set_ylabel("% of reviews containing the words")
    axs[0, 0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("Share of reviews with AI-marker words by half-year (dashed line: ChatGPT release, 30 Nov 2022)",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig_trend_halfyear.png", dpi=170)
    plt.close(fig)

    # 2. period comparison
    fig, axs = plt.subplots(rows_, cols, figsize=(4.2 * cols, 3.3 * rows_), squeeze=False, sharey=True)
    for ax, (p, lang) in zip(axs.flat, series):
        g = levels[(levels.platform == p) & (levels.language == lang) & (levels.measure == "has_eval")]
        g = g.set_index("period").reindex(PERIODS)
        y = g.value * 100
        ax.bar(range(len(PERIODS)), y, color=COLORS[p], alpha=.85, width=.5)
        ax.errorbar(range(len(PERIODS)), y, yerr=[y - g.ci_low * 100, g.ci_high * 100 - y], fmt="none", ecolor="#222",
                    capsize=4, lw=1.2)
        for i, (v, k) in enumerate(zip(y, g.reviews)):
            ax.text(i, 2, f"n={int(k)}", ha="center", fontsize=7.5, color="white")
            ax.text(i + .28, v + 1.5, f"{v:.0f}%", fontsize=8)
        ax.set_xticks(range(len(PERIODS)))
        ax.set_xticklabels([PERIOD_LABEL[x] for x in PERIODS], fontsize=8)
        ax.set_title(title(p, lang), loc="left")
    for ax in axs.flat[n:]:
        ax.axis("off")
    axs[0, 0].set_ylabel("% of reviews with an AI-marker word")
    fig.suptitle("AI-marker words before and after ChatGPT's release (30 Nov 2022), 95% bootstrap intervals",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig_period_comparison.png", dpi=170)
    plt.close(fig)

    # 3. word shift
    fig, axs = plt.subplots(rows_, cols, figsize=(4.2 * cols, 3.9 * rows_), squeeze=False)
    for ax, (p, lang) in zip(axs.flat, series):
        g = ws[(ws.platform == p) & (ws.language == lang) & (ws.group == "evaluative")]
        g = g.sort_values("post_share").tail(10)
        yy = np.arange(len(g))
        ax.hlines(yy, g.pre_share * 100, g.post_share * 100, color="#bbb", lw=2)
        ax.plot(g.pre_share * 100, yy, "o", color="#999", label="Pre-ChatGPT")
        ax.plot(g.post_share * 100, yy, "o", color=COLORS[p], label="Post-ChatGPT")
        labels = g.meaning if lang == "bangla" else g.word
        ax.set_yticks(yy)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_title(title(p, lang), loc="left")
        ax.set_xlabel("% of reviews containing the word")
    for ax in axs.flat[n:]:
        ax.axis("off")
    axs[0, 0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle("Word shift: evaluative marker words before and after ChatGPT (Bangla words shown by meaning)",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig_word_shift.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()

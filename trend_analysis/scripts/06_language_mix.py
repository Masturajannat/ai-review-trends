"""
Language mix of reviews over time, by platform.

AI assistants write standard Bengali script or English by default, not Banglish. If reviewers began
to use them after ChatGPT's release, one possible trace is a shift in the language of reviews, away
from Banglish towards Bengali script or English. This is an indirect indicator: keyboard habits,
app changes and the product mix can shift the language mix as well, so the comparison is also made
for products that have reviews in both periods.

Output (trend_analysis/results/)
  language_mix_by_year.csv      share of kept reviews in each language, by platform and year
  language_mix_changes.csv      post- minus pre-ChatGPT share of each language, with bootstrap 95% CI,
                                for all reviews and for products reviewed in both periods
  fig_language_mix.png

Run from the repository root:  python trend_analysis/scripts/06_language_mix.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TA = ROOT / "trend_analysis"
OUT = TA / "results"
LANGS = ["bangla", "banglish", "english", "mixed"]
LABEL = {"bangla": "Bengali script", "banglish": "Banglish", "english": "English", "mixed": "Mixed script"}
COLORS = {"bangla": "#e8743b", "banglish": "#2a78d6", "english": "#1baf7a", "mixed": "#b9b7b0"}
PLATFORMS = ["Daraz", "Rokomari", "Shajgoj"]
BOOT = 2000
MIN_YEAR_REVIEWS = 15
CHATGPT_RELEASE = pd.Timestamp("2022-11-30")


def main():
    rng = np.random.default_rng(42)
    df = pd.read_csv(TA / "data" / "reviews_all.csv", encoding="utf-8-sig", dtype={"product_id": str})
    df = df[df.keep & df.language.isin(LANGS)].copy()
    df["date"] = pd.to_datetime(df.date)

    by_year = (df.groupby(["platform", "year", "language"]).size().unstack(fill_value=0)
               .reindex(columns=LANGS, fill_value=0))
    by_year["reviews"] = by_year.sum(axis=1)
    for lang in LANGS:
        by_year[f"share_{lang}"] = by_year[lang] / by_year.reviews
    by_year.to_csv(OUT / "language_mix_by_year.csv")

    rows = []
    for p in PLATFORMS:
        s = df[df.platform == p]
        both = set(s[s.period == "pre_chatgpt"].product_id) & set(s[s.period == "post_chatgpt"].product_id)
        for subset, g in [("all reviews", s), ("products reviewed in both periods", s[s.product_id.isin(both)])]:
            pre, post = g[g.period == "pre_chatgpt"], g[g.period == "post_chatgpt"]
            if len(pre) < 10 or len(post) < 10:
                continue
            for lang in LANGS:
                a, b = (post.language == lang).to_numpy(float), (pre.language == lang).to_numpy(float)
                d = np.array([a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean()
                              for _ in range(BOOT)])
                lo, hi = np.percentile(d, [2.5, 97.5])
                rows.append(dict(platform=p, subset=subset, language=lang, pre_reviews=len(pre),
                                 post_reviews=len(post), pre_share=b.mean(), post_share=a.mean(),
                                 change=a.mean() - b.mean(), ci_low=lo, ci_high=hi,
                                 clear="increase" if lo > 0 else "decrease" if hi < 0 else "no clear change"))
    ch = pd.DataFrame(rows)
    ch.to_csv(OUT / "language_mix_changes.csv", index=False)
    show = ch.copy()
    for c in ["pre_share", "post_share", "change", "ci_low", "ci_high"]:
        show[c] = (show[c] * 100).round(1)
    print("Language share before and after ChatGPT (%), change in percentage points")
    print(show.to_string(index=False))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 9})
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    for ax, p in zip(axs, PLATFORMS):
        g = by_year.loc[p]
        g = g[g.reviews >= MIN_YEAR_REVIEWS]
        bottom = np.zeros(len(g))
        x = np.arange(len(g))
        for lang in LANGS:
            ax.bar(x, g[f"share_{lang}"] * 100, 0.75, bottom=bottom, color=COLORS[lang], label=LABEL[lang])
            bottom += g[f"share_{lang}"].to_numpy() * 100
        years = list(g.index)
        if 2023 in years:
            ax.axvline(years.index(2023) - 0.5, color="#222", ls="--", lw=1)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{y}\nn={n}" for y, n in zip(years, g.reviews)], fontsize=7.5)
        ax.set_title(p, loc="left")
        ax.set_ylim(0, 100)
    axs[0].set_ylabel("% of reviews")
    axs[-1].legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(1.0, 0.5))
    fig.suptitle("Language of reviews by year (years with >= 15 reviews; dashed line: first full year after "
                 "ChatGPT's release)", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig_language_mix.png", dpi=170)
    plt.close(fig)
    print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()

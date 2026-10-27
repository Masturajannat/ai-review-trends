"""
Banglish-specific analysis.

Banglish (Bengali written in Latin letters) has no fixed spelling: the same word appears as valo, vlo,
bhalo, balo. Human reviewers use many informal spellings; AI-generated Banglish uses standard
spellings and the standard written register far more consistently. This script

  A. measures, for every Banglish review, the STANDARD-FORM SHARE: of the words that belong to a
     variant family in trend_analysis/banglish_variants.csv, the share written in the canonical form
     (standard Avro Phonetic spelling, or the standard written form for register families such as
     hoyeche vs colloquial hoise). It is checked on AI vs pre-2022 human reviews and compared before
     and after ChatGPT's release for each platform.
  B. repeats the marker-word analysis for Banglish with spelling-normalised words and CROSS-FITTING,
     so that every pre-ChatGPT review is used: markers are chosen on one half of the pre-2022 reviews
     and the baseline is measured on the other half, then the halves are swapped and the two
     estimates averaged. Markers are selected automatically from a fixed list of evaluative words
     (EVALUATIVE below, defined before looking at the data) as those with log-odds z >= Z_MIN for AI.

Outputs (trend_analysis/results/)
  banglish_standard_check.csv     standard-form share: AI vs held-out human pre-2022 reviews
  banglish_standard_periods.csv   standard-form share by platform and period, with bootstrap CI
  banglish_standard_changes.csv   post- minus pre-ChatGPT (and placebo: Jan-Nov 2022 minus pre-2022)
  banglish_markers_crossfit.csv   markers chosen in each fold, held-out check, and change by platform
  fig_banglish.png

Run from the repository root:  python trend_analysis/scripts/05_banglish.py
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
OUT = TA / "results"
REF_SPLIT = ROOT / "archive" / "week5_mixture_translated" / "data" / "human_reference.csv"
PLATFORMS = ["Daraz", "Shajgoj"]           # Rokomari has too few Banglish reviews (14)
MIN_REVIEWS = 30
BOOT = 2000
Z_MIN = 1.0
CHATGPT_RELEASE = pd.Timestamp("2022-11-30")
COLORS = {"Daraz": "#2a78d6", "Shajgoj": "#1baf7a", "AI": "#888"}

# Evaluative Banglish words (canonical spellings), fixed before the analysis. Markers are chosen from
# this list in each fold; topic and product words can therefore never become markers.
EVALUATIVE = """bhalo bhaloi darun osadharon sundor ekdom khub khubi khuboi onek beshi shotti chomotkar joss
mast shera shobcheye prochur onnorokom perfect best highly recommended recommend amazing awesome excellent
nice great good superb fantastic satisfied happy love loved worth gorgeous wonderful outstanding""".split()


# ---------------------------------------------------------------- data
def load():
    rev = pd.read_csv(TA / "data" / "reviews_all.csv", encoding="utf-8-sig", dtype={"review_id": str})
    rev = rev[rev.keep & (rev.language == "banglish")].copy()
    rev["date"] = pd.to_datetime(rev.date)
    ai = pd.read_csv(TA / "data" / "ai_reference_original.csv", encoding="utf-8-sig",
                     dtype={"source_review_id": str})
    ai = ai[ai.keep & (ai.language == "banglish")].copy()
    ref_ids = set(pd.read_csv(REF_SPLIT, dtype={"review_id": str}).review_id)
    # fold for pre-2022 human reviews and for AI reviews (by the review they were made from)
    rev["fold"] = np.where(rev.period_detail != "pre_2022", "none",
                           np.where(rev.review_id.isin(ref_ids), "A", "B"))
    ai["fold"] = np.where(ai.source_review_id.isin(ref_ids), "A", "B")
    return rev, ai


# ---------------------------------------------------------------- A. standard-form share
def standard_counts(text, types):
    """(words belonging to a variant family of the given types, of which in canonical form)"""
    raw = tu.tokens(text, "banglish")
    n = k = 0
    for w in raw:
        canon = w if w in tu.FAMILIES else tu.VARIANT_TO_CANONICAL.get(w)
        if canon is None or tu.FAMILIES[canon]["type"] not in types:
            continue
        n += 1
        k += w == canon
    return n, k


def add_standard(df, types, prefix):
    nk = [standard_counts(t, types) for t in df.text_clean]
    df[f"{prefix}_n"] = [n for n, _ in nk]
    df[f"{prefix}_share"] = [k / n if n else np.nan for n, k in nk]
    return df


def boot(x, rng):
    x = np.asarray(x, float)
    return np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(BOOT)])


def compare(df, col, rng):
    """levels and changes of review-level column col (reviews where it is defined)"""
    levels, changes = [], []
    for p in PLATFORMS:
        s = df[(df.platform == p) & df[col].notna()]
        groups = {"pre_chatgpt": s[s.period == "pre_chatgpt"], "post_chatgpt": s[s.period == "post_chatgpt"],
                  "pre_2022": s[s.period_detail == "pre_2022"], "jan_nov_2022": s[s.period_detail == "jan_nov_2022"]}
        b = {}
        for name, g in groups.items():
            b[name] = boot(g[col], rng) if len(g) >= 5 else None
            lo, hi = np.percentile(b[name], [2.5, 97.5]) if b[name] is not None else (np.nan, np.nan)
            levels.append(dict(platform=p, period=name, reviews=len(g), value=g[col].mean(), ci_low=lo, ci_high=hi))
        for label, a_, b_ in [("post_chatgpt - pre_chatgpt", "post_chatgpt", "pre_chatgpt"),
                              ("placebo: jan_nov_2022 - pre_2022", "jan_nov_2022", "pre_2022")]:
            if b[a_] is None or b[b_] is None:
                continue
            d = b[a_] - b[b_]
            lo, hi = np.percentile(d, [2.5, 97.5])
            changes.append(dict(platform=p, comparison=label, n_a=len(groups[a_]), n_b=len(groups[b_]),
                                change=groups[a_][col].mean() - groups[b_][col].mean(), ci_low=lo, ci_high=hi,
                                clear="increase" if lo > 0 else "decrease" if hi < 0 else "no clear change"))
    return pd.DataFrame(levels), pd.DataFrame(changes)


# ---------------------------------------------------------------- B. cross-fitted markers
def log_odds_z(ai_sets, human_sets, prior_scale=0.01):
    ca = Counter(w for s in ai_sets for w in s)
    ch = Counter(w for s in human_sets for w in s)
    vocab = set(ca) | set(ch)
    total = sum(ca[w] + ch[w] for w in vocab)
    a0 = prior_scale * len(vocab) * 100
    na, nh = sum(ca.values()), sum(ch.values())
    z = {}
    for w in vocab:
        aw = (ca[w] + ch[w]) / total * a0
        la = np.log((ca[w] + aw) / (na + a0 - ca[w] - aw))
        lh = np.log((ch[w] + aw) / (nh + a0 - ch[w] - aw))
        z[w] = (la - lh) / np.sqrt(1 / (ca[w] + aw) + 1 / (ch[w] + aw))
    return z, ca


def crossfit(rev, ai, rng):
    norm = lambda texts: [set(tu.tokens(t, "banglish", normalize=True)) for t in texts]
    rev = rev.copy()
    rev["words"] = norm(rev.text_clean)
    ai = ai.copy()
    ai["words"] = norm(ai.text_clean)
    rows, has = [], {}
    for fold, other in [("A", "B"), ("B", "A")]:
        z, ca = log_odds_z(list(ai[ai.fold == fold].words), list(rev[rev.fold == fold].words))
        markers = sorted(w for w in EVALUATIVE if z.get(w, -9) >= Z_MIN and ca[w] >= 5)
        mset = set(markers)
        # held-out check on the other fold
        h_out, a_out = rev[rev.fold == other], ai[ai.fold == other]
        rows.append(dict(kind="markers", fold=fold, markers=" ".join(markers),
                         heldout_ai_share=np.mean([bool(mset & s) for s in a_out.words]),
                         heldout_human_share=np.mean([bool(mset & s) for s in h_out.words]),
                         heldout_ai_reviews=len(a_out), heldout_human_reviews=len(h_out)))
        # 1 if the review contains a marker chosen in this fold; the fold's own discovery reviews are excluded
        has[fold] = pd.Series([float(bool(mset & s)) if f != fold else np.nan
                               for s, f in zip(rev.words, rev.fold)], index=rev.index)
    rev["marker_A"], rev["marker_B"] = has["A"], has["B"]

    results = []
    for p in PLATFORMS:
        s = rev[rev.platform == p]
        pre, post = s[s.period == "pre_chatgpt"], s[s.period == "post_chatgpt"]
        # cross-fitted estimate: average of the two folds
        est = {}
        for name, g in [("pre", pre), ("post", post)]:
            est[name] = np.nanmean([g.marker_A.mean(), g.marker_B.mean()])
        boots = []
        for _ in range(BOOT):
            gp = pre.iloc[rng.integers(0, len(pre), len(pre))]
            gq = post.iloc[rng.integers(0, len(post), len(post))]
            boots.append(np.nanmean([gq.marker_A.mean(), gq.marker_B.mean()]) -
                         np.nanmean([gp.marker_A.mean(), gp.marker_B.mean()]))
        lo, hi = np.nanpercentile(boots, [2.5, 97.5])
        results.append(dict(kind="change", platform=p, pre_reviews=len(pre), post_reviews=len(post),
                            pre_share=est["pre"], post_share=est["post"], change=est["post"] - est["pre"],
                            ci_low=lo, ci_high=hi,
                            clear="increase" if lo > 0 else "decrease" if hi < 0 else "no clear change"))
    return pd.DataFrame(rows), pd.DataFrame(results)


# ---------------------------------------------------------------- main
def main():
    rng = np.random.default_rng(42)
    rev, ai = load()
    for df in (rev, ai):
        add_standard(df, {"spelling", "register"}, "std")
        add_standard(df, {"spelling"}, "spell")
        add_standard(df, {"register"}, "reg")

    # A. check: AI vs held-out pre-2022 human reviews (fold B) and all pre-2022
    chk = []
    for col, label in [("std_share", "spelling + register"), ("spell_share", "spelling only"),
                       ("reg_share", "register only")]:
        for name, g in [("AI (Gemini)", ai), ("human pre-2022, held-out half", rev[rev.fold == "B"]),
                        ("human pre-2022, all", rev[rev.period_detail == "pre_2022"])]:
            x = g[col].dropna()
            chk.append(dict(measure=label, group=name, reviews_with_family_words=len(x), mean_standard_share=x.mean()))
    chk = pd.DataFrame(chk)
    chk.to_csv(OUT / "banglish_standard_check.csv", index=False)
    print("A. Standard-form share (reviews containing at least one variant-family word)")
    print(chk.assign(mean_standard_share=(chk.mean_standard_share * 100).round(1)).to_string(index=False))

    lev, chg = compare(rev, "std_share", rng)
    lev.to_csv(OUT / "banglish_standard_periods.csv", index=False)
    chg.to_csv(OUT / "banglish_standard_changes.csv", index=False)
    show = chg.copy()
    for c in ["change", "ci_low", "ci_high"]:
        show[c] = (show[c] * 100).round(1)
    print("\nStandard-form share, change in percentage points")
    print(show.to_string(index=False))

    # B. cross-fitted markers
    mk, res = crossfit(rev, ai, rng)
    pd.concat([mk, res]).to_csv(OUT / "banglish_markers_crossfit.csv", index=False)
    print("\nB. Cross-fitted Banglish markers")
    for r in mk.itertuples():
        print(f"  fold {r.fold}: {r.markers}\n     held-out check: AI {r.heldout_ai_share:.1%} vs human "
              f"{r.heldout_human_share:.1%}")
    show = res.copy()
    for c in ["pre_share", "post_share", "change", "ci_low", "ci_high"]:
        show[c] = (show[c] * 100).round(1)
    print(show.drop(columns="kind").to_string(index=False))

    plot(rev, ai, lev, res)
    print(f"\nSaved to {OUT}")


def plot(rev, ai, lev, res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.color": "#e6e5e1", "axes.axisbelow": True, "font.size": 9})
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.9))
    # 1. standard-form share by year
    ax = axs[0]
    ax.axvline(CHATGPT_RELEASE, color="#888", ls="--", lw=1)
    for p in PLATFORMS:
        s = rev[(rev.platform == p) & rev.std_share.notna()]
        g = s.groupby(s.date.dt.year).std_share.agg(["mean", "count"])
        g = g[g["count"] >= 10]
        ax.plot([pd.Timestamp(y, 7, 1) for y in g.index], g["mean"] * 100, "o-", color=COLORS[p], label=p)
    ax.axhline(ai.std_share.mean() * 100, color=COLORS["AI"], ls=":", lw=1.5, label="AI reviews (Gemini)")
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of variant-family words in standard form")
    ax.set_title("Standard spelling/register by year (years with >= 10 reviews)", loc="left", fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    # 2. standard-form share pre/post
    ax = axs[1]
    for i, p in enumerate(PLATFORMS):
        g = lev[(lev.platform == p)].set_index("period").reindex(["pre_chatgpt", "post_chatgpt"])
        x = np.array([0, 1]) + (i - 0.5) * 0.3
        y = g.value * 100
        ax.bar(x, y, 0.28, color=COLORS[p], alpha=.85, label=p)
        ax.errorbar(x, y, yerr=[y - g.ci_low * 100, g.ci_high * 100 - y], fmt="none", ecolor="#222", capsize=3)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Pre-ChatGPT", "Post-ChatGPT"])
    ax.set_ylim(0, 100)
    ax.set_title("Standard-form share before and after ChatGPT", loc="left", fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    # 3. cross-fitted markers pre/post
    ax = axs[2]
    for i, r in enumerate(res.itertuples()):
        x = np.array([0, 1]) + (i - 0.5) * 0.3
        ax.bar(x, [r.pre_share * 100, r.post_share * 100], 0.28, color=COLORS[r.platform], alpha=.85,
               label=f"{r.platform}: {r.change * 100:+.1f} pts [{r.ci_low * 100:+.1f}, {r.ci_high * 100:+.1f}]")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Pre-ChatGPT", "Post-ChatGPT"])
    ax.set_ylim(0, 60)
    ax.set_ylabel("% of reviews with a marker word")
    ax.set_title("Evaluative marker words (normalised spelling, cross-fitted)", loc="left", fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Banglish reviews", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "fig_banglish.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()

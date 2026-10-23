import importlib.util, re
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RES = ROOT / "results" / "full_adjadv_per-platform"
OUT = RES / "graphs"
OUT.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("v", Path(__file__).with_name("05_validate.py"))
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)

PLAT = ["Daraz", "Rokomari", "Shajgoj"]
COL = {"Daraz": "#2a78d6", "Rokomari": "#eb6834", "Shajgoj": "#1baf7a"}
PER = ["pre_2022 (held out)", "2022", "post_2022"]
PERRAW = ["pre_2022", "2022", "post_2022"]
PLAB = ["Before 2022", "2022\n(control)", "After 2022"]
INK, MUTE, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTE,
    "xtick.color": MUTE, "ytick.color": MUTE, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True, "figure.facecolor": "#fcfcfb",
    "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb"})
rd = lambda f: pd.read_csv(f if Path(f).is_absolute() else DATA / f, dtype={"review_id": str, "product_id": str})

# ---------- data
real = rd("source_reviews_clean.csv")
real["text"] = np.where(real.text_source == "translated", real.translated_review_en, real.review_text)
real["text"] = real["text"].fillna("")
real["words"] = real.text.str.findall(r"[A-Za-z']+").str.len()
h_ref, ai_ref = rd("human_reference.csv"), rd("ai_reference.csv")
for d in (h_ref, ai_ref): d["text"] = d.translated_review_en.fillna("")
ai_ref = ai_ref[ai_ref.text.str.strip() != ""]
real["period2"] = real.period.where(real.period != "pre_2022",
                  np.where(real.review_id.isin(set(h_ref.review_id)), "ref", "pre_2022 (held out)"))
real["period2"] = real.period2.replace({"pre_2022": "pre_2022 (held out)"})
heldout = real[real.period2 != "ref"]
pre_products = set(real[real.period == "pre_2022"].product_id)
same = heldout[heldout.product_id.isin(pre_products)]

# ---------- 1 validation
vs = rd(RES / "validation_summary.csv")
fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.8), sharey=True)
for ax, p in zip(axs, PLAT):
    g = vs[vs.platform == p]; x, y = g.true_sentence_share * 100, g.mean_estimate * 100
    ax.plot([0, 45], [0, 45], "--", color="#999", lw=1, label="Perfect")
    ax.errorbar(x, y, yerr=[y - g.p5 * 100, g.p95 * 100 - y], fmt="o", ms=8, color=COL[p],
                mec="#fcfcfb", mew=2, capsize=4, lw=2, label="Method's guess (5th-95th %)")
    for xi, yi in zip(x, y): ax.annotate(f"{yi:.0f}%", (xi, yi), xytext=(8, -3), textcoords="offset points", color=INK, fontsize=9)
    ax.set_title(p, color=INK, loc="left"); ax.set_xlabel("True AI share (%)"); ax.set_xlim(-2, 45); ax.set_ylim(-2, 45)
axs[0].set_ylabel("Estimated AI share (%)"); axs[2].legend(frameon=False, fontsize=8, loc="lower right")
fig.suptitle("1. Does the method work? Dots near the dashed line = yes", color=INK, x=0.01, ha="left")
fig.tight_layout(); fig.savefig(OUT / "graph1_validation.png", dpi=170); plt.close()

# ---------- 2 estimates by period
re_ = rd(RES / "real_data_estimates.csv"); re_ = re_[re_.subset == "same products"]  # README results use same-product reviews
fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.9), sharey=True)
for ax, p in zip(axs, PLAT):
    g = re_[re_.platform == p].set_index("period").loc[PER]
    y = g.ai_share * 100
    ax.bar(range(3), y, width=.55, color=COL[p], alpha=.9)
    ax.errorbar(range(3), y, yerr=[y - g.ci_low * 100, g.ci_high * 100 - y], fmt="none", ecolor=INK, capsize=4, lw=1.3)
    for i, yi in enumerate(y): ax.text(i + .3, yi + 1, f"{yi:.0f}%", color=INK, fontsize=9, ha="left")
    ax.axhline(y.iloc[0], color="#999", ls="--", lw=1)
    ax.set_xticks(range(3)); ax.set_xticklabels(PLAB, fontsize=9); ax.set_title(p, color=INK, loc="left"); ax.set_ylim(0, 105)
axs[0].set_ylabel("Estimated AI share (%)")
fig.suptitle("2. Real reviews. 2022 is pre-ChatGPT, so it should match 'Before' (dashed line). Rokomari doesn't.", color=INK, x=0.01, ha="left", fontsize=10.5)
fig.tight_layout(); fig.savefig(OUT / "graph2_estimates_by_period.png", dpi=170); plt.close()

# ---------- 3 review length
fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.9), sharey=True)
stats = []
for ax, p in zip(axs, PLAT):
    meds = []
    for i, per in enumerate(PER):
        w = real[(real.platform == p) & (real.period == PERRAW[i])].word_count
        q1, m, q3 = w.quantile([.25, .5, .75]); meds.append(m); stats.append((p, per, len(w), q1, m, q3))
        ax.vlines(i, q1, q3, color=COL[p], lw=10, alpha=.45)
        ax.plot(i, m, "o", ms=9, color=COL[p], mec="#fcfcfb", mew=2)
        ax.text(i + .15, m, f"{m:g}", color=INK, fontsize=9, va="center")
    ax.set_xticks(range(3)); ax.set_xticklabels(PLAB, fontsize=9); ax.set_title(p, color=INK, loc="left"); ax.set_xlim(-.5, 2.6)
axs[0].set_ylabel("Words per review"); axs[0].set_ylim(0, None)
fig.suptitle("3. Review length: dot = median, bar = middle 50% of reviews", color=INK, x=0.01, ha="left")
fig.tight_layout(); fig.savefig(OUT / "graph3_review_length.png", dpi=170); plt.close()
pd.DataFrame(stats, columns=["platform", "period", "n", "q1", "median", "q3"]).to_csv(OUT / "graph3_length_stats.csv", index=False)

# ---------- 5 sample size
# counts come from the estimates file, so they match graph 2 (reviews the estimator actually used)
cnt = re_.pivot(index="platform", columns="period", values="reviews").loc[PLAT, PER].astype(int)
fig, ax = plt.subplots(figsize=(7.5, 3.8)); w = .26
for j, per in enumerate(PER):
    xs = np.arange(3) + (j - 1) * (w + .02)
    ax.bar(xs, cnt[per], w, color=["#9ec5f4", "#86b6ef", "#2a78d6"][j], label=PLAB[j].replace("\n", " "))
    for x_, c in zip(xs, cnt[per]): ax.text(x_, c + 8, str(c), ha="center", fontsize=8.5, color=INK)
ax.set_xticks(range(3)); ax.set_xticklabels(PLAT); ax.set_ylabel("Number of reviews"); ax.legend(frameon=False, fontsize=8)
ax.set_title("5. How many reviews each estimate is built on (fewer = wider error bars)", color=INK, loc="left", fontsize=10.5)
fig.tight_layout(); fig.savefig(OUT / "graph5_sample_size.png", dpi=170); plt.close()
cnt.to_csv(OUT / "graph5_counts.csv")

# ---------- 4 length bands
BANDS = [("1-5 words", 0, 5), ("6-15 words", 6, 15), ("16+ words", 16, 10**6)]
sent = v.Sentencizer("adjadv"); sent.prepare(pd.concat([h_ref.text, ai_ref.text, real.text]))
rng = np.random.default_rng(42); rows = []
for p in PLAT:
    est = v.Estimator(sent, h_ref[h_ref.platform == p].text, ai_ref[ai_ref.platform == p].text)
    for bname, lo, hi in BANDS:
        for per in PER:
            g = same[(same.platform == p) & (same.period2 == per) & same.word_count.between(lo, hi)]
            a, b, n, ns = est.bootstrap(g.text, 300, rng)
            cl, ch = np.nanpercentile(b, [2.5, 97.5]) if n else (np.nan, np.nan)
            rows.append(dict(platform=p, band=bname, period=per, reviews=n, sentences=ns, ai_share=a, ci_low=cl, ci_high=ch))
r4 = pd.DataFrame(rows); r4.to_csv(OUT / "graph4_length_band_estimates.csv", index=False); print(r4.round(3).to_string())
fig, axs = plt.subplots(3, 3, figsize=(10.5, 8.5), sharey=True)
for i, p in enumerate(PLAT):
    for j, (bname, _, _) in enumerate(BANDS):
        ax = axs[i, j]; g = r4[(r4.platform == p) & (r4.band == bname)].set_index("period").loc[PER]
        y = g.ai_share.fillna(0) * 100
        ax.bar(range(3), y, .55, color=COL[p], alpha=.9)
        ax.errorbar(range(3), y, yerr=[(y - g.ci_low * 100).fillna(0), (g.ci_high * 100 - y).fillna(0)], fmt="none", ecolor=INK, capsize=3, lw=1.1)
        for k, (yi, n) in enumerate(zip(y, g.reviews)): ax.text(k, 103, f"n={n}", ha="center", fontsize=8, color=MUTE)
        ax.set_xticks(range(3)); ax.set_xticklabels(["Before", "2022", "After"], fontsize=9); ax.set_ylim(0, 112)
        if i == 0: ax.set_title(bname, color=INK)
        if j == 0: ax.set_ylabel(f"{p}\nAI share (%)")
fig.suptitle("4. Same-length comparison: AI share within length bands (n = reviews in bar)", color=INK, x=0.01, ha="left")
fig.tight_layout(); fig.savefig(OUT / "graph4_length_bands.png", dpi=170); plt.close()

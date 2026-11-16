"""Step 1: baseline models that predict the review-quality score from the review text.

Trained on the full + pilot reviews (6,922) and tested once on the 400 main-run reviews.
Nothing here needs a GPU or an API key; it takes a few minutes on a laptop.

Models, from trivial to the baseline we keep:
  mean       always predicts the average training score            (what "no model" gives)
  length     ridge regression on the review's length only          (is the score just length?)
  tfidf      TF-IDF of character n-grams (2-5) -> ridge regression (works for Bangla, Banglish,
             English and mixed text without any tokenizer or word list)
  tfidf+len  the same plus word n-grams and the length features    (the baseline we save)

The ridge strength is chosen by 5-fold cross-validation on the training reviews only.

  python scripts/01_baseline.py        (from quality_model/)

Writes results/baseline_results.txt, results/baseline_predictions.csv,
results/fig_baseline.png and models/baseline.joblib.
"""
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from common import load, gemini_runs, metrics, fmt, RESULTS, MODELS

SEED = 299
ALPHAS = [0.3, 1, 3, 10]


def length_features(texts):
    """log(characters), log(words), sentences, has a digit: the size of the review, nothing else."""
    out = []
    for t in texts:
        words = t.split()
        out.append([np.log1p(len(t)), np.log1p(len(words)),
                    np.log1p(sum(t.count(c) for c in ".!?।\n")), float(any(ch.isdigit() for ch in t))])
    return np.array(out)


LENGTH = Pipeline([("f", FunctionTransformer(length_features)), ("s", StandardScaler())])
CHARS = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True, lowercase=True)
WORDS = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True, lowercase=True,
                        token_pattern=r"(?u)\b\w+\b")


def build(kind):
    if kind == "mean":
        return DummyRegressor(strategy="mean")
    feats = {"length": [("len", LENGTH, "text")],
             "tfidf": [("chars", CHARS, "text")],
             "tfidf+len": [("chars", CHARS, "text"), ("words", WORDS, "text"), ("len", LENGTH, "text")]}[kind]
    return Pipeline([("x", ColumnTransformer(feats)), ("ridge", Ridge(random_state=SEED))])


def clip(p):
    return np.clip(p, 1, 10)


def main():
    os.makedirs(RESULTS, exist_ok=True); os.makedirs(MODELS, exist_ok=True)
    train, test = load()
    # a one-column table: ColumnTransformer hands the "text" column to each feature extractor
    Xtr, ytr = train[["text_original"]].rename(columns={"text_original": "text"}), train["score"]
    Xte, yte = test[["text_original"]].rename(columns={"text_original": "text"}), test["score"]
    cv = KFold(5, shuffle=True, random_state=SEED)

    lines = [f"BASELINE MODELS FOR THE REVIEW-QUALITY SCORE",
             f"train: {len(train)} reviews (full + pilot)   test: {len(test)} reviews (main run, never trained on)",
             f"label: mean of two Gemini runs, 1 to 10", ""]
    fitted, preds, cvrows = {}, {}, []
    for kind in ["mean", "length", "tfidf", "tfidf+len"]:
        model = build(kind)
        if kind != "mean":
            search = GridSearchCV(model, {"ridge__alpha": ALPHAS}, cv=cv, scoring="neg_mean_absolute_error")
            search.fit(Xtr, ytr)
            model, alpha = search.best_estimator_, search.best_params_["ridge__alpha"]
        else:
            model.fit(Xtr, ytr); alpha = None
        cvp = clip(cross_val_predict(build(kind) if alpha is None else model, Xtr, ytr, cv=cv))
        fitted[kind], preds[kind] = model, clip(model.predict(Xte))
        cvrows.append((kind, alpha, metrics(ytr, cvp), metrics(yte, preds[kind])))

    lines.append("CROSS-VALIDATION ON THE TRAINING REVIEWS (5 folds)")
    for kind, alpha, cvm, _ in cvrows:
        lines.append(f"  {kind:10s} {fmt(cvm)}" + (f"   (ridge alpha {alpha})" if alpha else ""))
    lines += ["", "TEST: THE 400 MAIN-RUN REVIEWS"]
    for kind, _, _, tem in cvrows:
        lines.append(f"  {kind:10s} {fmt(tem)}")

    # the yardstick: how well Gemini agrees with itself on the same 400 reviews
    g = test[["review_id", "score"]].merge(gemini_runs(), on="review_id")
    lines += ["", "YARDSTICK ON THE SAME 400 REVIEWS",
              f"  Gemini run 1 vs run 2 (one run against the other)   {fmt(metrics(g['run2'], g['run1']))}",
              "  A model cannot be expected to agree with the labels better than the labeller agrees with itself."]

    best = "tfidf+len"
    out = test[["review_id", "platform", "language", "n_words", "score"]].copy()
    out["predicted"] = preds[best].round(2)
    out["error"] = (out["predicted"] - out["score"]).round(2)
    lines += ["", f"BY LANGUAGE AND PLATFORM ({best}, test set)"]
    for col in ["language", "platform"]:
        for name, part in out.groupby(col):
            lines.append(f"  {name:9s} {fmt(metrics(part['score'], part['predicted']))}   "
                         f"mean error {part['error'].mean():+.2f}")
    band = pd.cut(out["score"], [0, 3, 5, 7, 10], labels=["1-3", "3.5-5", "5.5-7", "7.5-10"])
    lines += ["", f"BY SCORE BAND ({best}, test set): mean error shows where the model is too high (+) or too low (-)"]
    for name, part in out.groupby(band, observed=True):
        lines.append(f"  label {name:7s} {fmt(metrics(part['score'], part['predicted']))}   "
                     f"mean error {part['error'].mean():+.2f}")

    out.to_csv(os.path.join(RESULTS, "baseline_predictions.csv"), index=False, encoding="utf-8-sig")
    joblib.dump({"model": fitted[best], "kind": best, "trained_on": len(train)},
                os.path.join(MODELS, "baseline.joblib"))
    txt = "\n".join(lines)
    open(os.path.join(RESULTS, "baseline_results.txt"), "w", encoding="utf-8").write(txt + "\n")
    print(txt)
    figure(out, cvrows, metrics(g["run2"], g["run1"]))


def figure(out, rows, gem):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, MUTED, GRID, BLUE, GREY = "#1B1D21", "#5A5D64", "#E4E4DE", "#2A6FBB", "#9AA0A8"
    plt.rcParams.update({"font.size": 11, "axes.edgecolor": GRID, "text.color": INK, "axes.labelcolor": MUTED,
                         "xtick.color": INK, "ytick.color": MUTED})
    fig, (a, b) = plt.subplots(1, 2, figsize=(13.5, 5), dpi=200, gridspec_kw={"width_ratios": [1, 1.1], "wspace": 0.6})
    rng = np.random.default_rng(1)
    a.plot([1, 10], [1, 10], color=GREY, lw=1, zorder=1)
    a.fill_between([1, 10], [0, 9], [2, 11], color="#F1F1EC", zorder=0)
    a.scatter(out["score"] + rng.uniform(-.12, .12, len(out)), out["predicted"], s=14, color=BLUE, alpha=.55,
              linewidths=0, zorder=2)
    a.set_xlim(.5, 10); a.set_ylim(.5, 10); a.set_xticks(range(1, 11)); a.set_yticks(range(1, 11))
    a.set_xlabel("Gemini score (mean of two runs)"); a.set_ylabel("Baseline model's score")
    a.set_title("Each dot is one of the 400 test reviews", loc="left", fontsize=12, fontweight="bold", pad=10)
    a.text(9.9, 1.0, "grey band: within 1 point", ha="right", fontsize=9, color=MUTED)
    names = {"mean": "Always the average", "length": "Review length only", "tfidf": "TF-IDF characters",
             "tfidf+len": "TF-IDF + length (baseline)"}
    labels = [names[k] for k, *_ in rows] + ["Gemini run 1 vs run 2"]
    vals = [r[3]["within 1"] * 100 for r in rows] + [gem["within 1"] * 100]
    maes = [r[3]["MAE"] for r in rows] + [gem["MAE"]]
    y = np.arange(len(labels))[::-1]
    b.barh(y, vals, height=.55, color=[BLUE] * len(rows) + [GREY], zorder=2)
    for yy, v, m in zip(y, vals, maes):
        b.text(v + 1.5, yy, f"{v:.0f}%   (MAE {m:.2f})", va="center", fontsize=11)
    b.set_yticks(y); b.set_yticklabels(labels, color=INK); b.set_xlim(0, 125); b.set_xticks([0, 25, 50, 75, 100])
    b.set_xlabel("Test reviews within 1 point of the Gemini score (%)")
    b.set_title("Share of test reviews within 1 point", loc="left", fontsize=12, fontweight="bold", pad=10)
    b.grid(axis="x", color=GRID, zorder=0); b.set_axisbelow(True)
    for ax in (a, b):
        ax.spines[["top", "right"]].set_visible(False); ax.tick_params(length=0)
    fig.savefig(os.path.join(RESULTS, "fig_baseline.png"), bbox_inches="tight", facecolor="white")


if __name__ == "__main__":
    main()

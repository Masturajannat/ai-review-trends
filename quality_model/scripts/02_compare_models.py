"""Step 2: can a classical model do better than the ridge baseline? Compares several.

Same split as step 1: train on full + pilot, test once on the main 400. Every choice (which
model is best) is made on 5-fold cross-validation of the training reviews, not on the test set.

Text features (fitted inside each fold): TF-IDF of character n-grams (2-5) and of word 1-2-grams,
plus size features. Extra "signal" features count things a useful review tends to contain,
in any of the three languages: digits, time words, contrast and reason words, question marks...

Models
  ridge            the step-1 baseline
  svr              linear support-vector regression on the same features
  logistic         classifies into score levels 1-9, predicts the expected level
  gbm              gradient-boosted trees on 200 SVD components + size + signal features
  ridge+signals    ridge with the signal features added
  blend            average of ridge+signals, svr and gbm
  blend+stretch    blend, then a straight-line correction (fitted on out-of-fold predictions)
                   that undoes the pull of the predictions towards the middle

  python scripts/02_compare_models.py        (from quality_model/; about 10 minutes, no GPU)

Writes results/compare_results.txt and results/compare_predictions.csv. No model is saved: none of
them beats the step-1 baseline by a margin that matters, so models/baseline.joblib stays the classical model.
"""
import os, re, time
import numpy as np
import pandas as pd
from scipy.sparse import hstack, csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge, LogisticRegression, LinearRegression
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVR

from common import load, gemini_runs, metrics, fmt, RESULTS

SEED = 299
SIGNALS = {
    "digits": r"\d|[০-৯]",
    "time": r"\b(day|days|week|weeks|month|months|year|years|din|mash|mas|bochor|shoptah|ghonta|hour|hours|minute)\b|দিন|সপ্তাহ|মাস|বছর|ঘণ্টা|ঘন্টা",
    "contrast": r"\b(but|however|though|although|tobe|kintu|jodio)\b|তবে|কিন্তু|যদিও",
    "reason": r"\b(because|since|so that|karon|tai|jonno|karone)\b|কারণ|তাই|জন্য",
    "compare": r"\b(than|compared|better|worse|theke|cheye|like the|unlike)\b|চেয়ে|থেকে|তুলনায়",
    "use": r"\b(use|used|using|tried|read|reading|wear|wore|porlam|porechi|pore|bebohar)\b|ব্যবহার|পড়ে|পড়েছি|পড়লাম",
    "service": r"\b(deliver\w*|packag\w*|packing|seller|courier|original|authentic|sealed|refund|replace\w*)\b|ডেলিভারি|প্যাকেজিং|প্যাকিং|অরিজিনাল",
    "question": r"\?",
    "money": r"\b(tk|taka|price|dam|daam|cost)\b|টাকা|দাম|৳",
}
SIGNALS = {k: re.compile(v) for k, v in SIGNALS.items()}


def size_features(texts):
    out = []
    for t in texts:
        w = t.split()
        out.append([np.log1p(len(t)), np.log1p(len(w)), np.log1p(sum(t.count(c) for c in ".!?।\n")),
                    np.log1p(len(set(x.lower() for x in w))), len(set(x.lower() for x in w)) / max(1, len(w)),
                    np.mean([len(x) for x in w]) if w else 0])
    return np.array(out)


def signal_features(texts):
    out = []
    for t in texts:
        low, letters = t.lower(), [c for c in t if c.isalpha()]
        row = [np.log1p(len(p.findall(low))) for p in SIGNALS.values()]
        row.append(sum("ঀ" <= c <= "৿" for c in letters) / max(1, len(letters)))   # share of Bangla script
        out.append(row)
    return np.array(out)


class Features:
    """Fits the text features on training texts; gives sparse (linear models) and dense (trees) views."""

    def fit(self, texts):
        self.chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True)
        self.words = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True,
                                     token_pattern=r"(?u)\b\w+\b")
        tfidf = hstack([self.chars.fit_transform(texts), self.words.fit_transform(texts)]).tocsr()
        self.s_size, self.s_sig = StandardScaler().fit(size_features(texts)), StandardScaler().fit(signal_features(texts))
        self.svd = TruncatedSVD(200, random_state=SEED).fit(tfidf)
        return self

    def views(self, texts):
        tfidf = hstack([self.chars.transform(texts), self.words.transform(texts)]).tocsr()
        size, sig = self.s_size.transform(size_features(texts)), self.s_sig.transform(signal_features(texts))
        return {"base": hstack([tfidf, csr_matrix(size[:, :3])]).tocsr(),       # what step 1 used
                "plus": hstack([tfidf, csr_matrix(size), csr_matrix(sig)]).tocsr(),
                "dense": np.hstack([self.svd.transform(tfidf), size, sig])}


LEVELS = np.arange(1, 10)


def fit_models(v, y):
    lv = np.clip(np.round(y), 1, 9).astype(int)
    return {"ridge": Ridge(alpha=1.0, random_state=SEED).fit(v["base"], y),
            "ridge+signals": Ridge(alpha=1.0, random_state=SEED).fit(v["plus"], y),
            "svr": LinearSVR(C=0.3, epsilon=0.25, max_iter=5000, random_state=SEED).fit(v["plus"], y),
            "logistic": LogisticRegression(C=10, max_iter=300).fit(v["plus"], lv),
            "gbm": HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=15,
                                                 l2_regularization=1.0, random_state=SEED).fit(v["dense"], y)}


def predict(models, v):
    lg = models["logistic"]
    p = {"ridge": models["ridge"].predict(v["base"]), "ridge+signals": models["ridge+signals"].predict(v["plus"]),
         "svr": models["svr"].predict(v["plus"]), "gbm": models["gbm"].predict(v["dense"]),
         "logistic": lg.predict_proba(v["plus"]) @ lg.classes_}
    p["blend"] = (p["ridge+signals"] + p["svr"] + p["gbm"]) / 3
    return {k: np.clip(x, 1, 10) for k, x in p.items()}


def main():
    os.makedirs(RESULTS, exist_ok=True)
    train, test = load()
    Xtr, ytr, Xte, yte = train["text_original"].tolist(), train["score"].values, test["text_original"].tolist(), test["score"].values
    t0 = time.time()

    oof = {}
    for k, (a, b) in enumerate(KFold(5, shuffle=True, random_state=SEED).split(Xtr), 1):
        f = Features().fit([Xtr[i] for i in a])
        p = predict(fit_models(f.views([Xtr[i] for i in a]), ytr[a]), f.views([Xtr[i] for i in b]))
        for name, x in p.items():
            oof.setdefault(name, np.zeros(len(Xtr)))[b] = x
        print(f"fold {k}/5 done ({time.time() - t0:.0f}s)", flush=True)
    # straight-line correction of the blend, learned from predictions on reviews the models had not seen
    stretch = LinearRegression().fit(oof["blend"].reshape(-1, 1), ytr)
    oof["blend+stretch"] = np.clip(stretch.predict(oof["blend"].reshape(-1, 1)), 1, 10)

    f = Features().fit(Xtr)
    models = fit_models(f.views(Xtr), ytr)
    pte = predict(models, f.views(Xte))
    pte["blend+stretch"] = np.clip(stretch.predict(pte["blend"].reshape(-1, 1)), 1, 10)

    order = ["ridge", "ridge+signals", "svr", "logistic", "gbm", "blend", "blend+stretch"]
    cvm = {n: metrics(ytr, oof[n]) for n in order}
    best = min(order, key=lambda n: cvm[n]["MAE"])
    lines = ["COMPARISON OF CLASSICAL MODELS FOR THE REVIEW-QUALITY SCORE",
             f"train: {len(train)} reviews (full + pilot)   test: {len(test)} reviews (main run)", "",
             "CROSS-VALIDATION ON THE TRAINING REVIEWS (5 folds): used to choose the model"]
    lines += [f"  {n:14s} {fmt(cvm[n])}" + ("   <- best" if n == best else "") for n in order]
    lines += ["", "TEST: THE 400 MAIN-RUN REVIEWS"]
    lines += [f"  {n:14s} {fmt(metrics(yte, pte[n]))}" + ("   <- chosen by cross-validation" if n == best else "")
              for n in order]
    g = test[["review_id"]].merge(gemini_runs(), on="review_id")
    lines += [f"  {'Gemini 1 vs 2':14s} {fmt(metrics(g['run2'], g['run1']))}   (yardstick)", "",
              f"stretch: corrected = {stretch.coef_[0]:.2f} x blend {stretch.intercept_:+.2f}", ""]

    out = test[["review_id", "platform", "language", "n_words", "score"]].copy()
    for n in order:
        out[n] = pte[n].round(2)
    lines.append(f"BY LANGUAGE AND SCORE BAND, TEST SET: step-1 ridge -> {best}")
    band = pd.cut(out["score"], [0, 3, 5, 7, 10], labels=["label 1-3", "label 3.5-5", "label 5.5-7", "label 7.5-10"])
    for col in [out["language"], band]:
        for name, part in out.groupby(col, observed=True):
            a, b = metrics(part["score"], part["ridge"]), metrics(part["score"], part[best])
            lines.append(f"  {str(name):13s} n={len(part):3d}  MAE {a['MAE']:.2f} -> {b['MAE']:.2f}   within 1 point "
                         f"{a['within 1']:.0%} -> {b['within 1']:.0%}   mean error "
                         f"{(part['ridge'] - part['score']).mean():+.2f} -> {(part[best] - part['score']).mean():+.2f}")
    out.to_csv(os.path.join(RESULTS, "compare_predictions.csv"), index=False, encoding="utf-8-sig")
    txt = "\n".join(lines)
    open(os.path.join(RESULTS, "compare_results.txt"), "w", encoding="utf-8").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()

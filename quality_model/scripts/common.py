"""Shared pieces of the review-quality model: where the data is, the split, and the metrics."""
import os
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # quality_model/
QE = os.path.join(os.path.dirname(ROOT), "quality_eval")
DATA = os.path.join(QE, "all_scores_feedback.csv")             # one row per scored review
# a run tag (PowerShell: $env:RUN_TAG="noreadmore") sends results and models to their own folders;
# tags starting with "noreadmore" also strip the Rokomari "Read More" leftover from the text
TAG = os.environ.get("RUN_TAG", "")
RESULTS = os.path.join(ROOT, "results" + ("_" + TAG if TAG else ""))
MODELS = os.path.join(ROOT, "models" + ("_" + TAG if TAG else ""))


def load():
    """(train, test): train = full + pilot reviews, test = the 400 main-run reviews.

    The label is `score`, the mean of two Gemini runs (1 to 10, in steps of 0.5). The main run
    is never used for training or for choosing settings: it is the set the human check and the
    earlier results were made on."""
    d = pd.read_csv(DATA, dtype={"review_id": str})
    d["text_original"] = d["text_original"].fillna("").astype(str)
    if TAG.startswith("noreadmore"):
        # Rokomari previews end with "Read More" (scraping leftover); users never type it
        d["text_original"] = d["text_original"].str.replace(r"(?i)\s*read more\s*$", "", regex=True)
    return (d[d["stage"] != "main"].reset_index(drop=True),
            d[d["stage"] == "main"].reset_index(drop=True))


def gemini_runs():
    """Run 1 and run 2 of Gemini on the main reviews: how much the labeller agrees with itself."""
    w = pd.read_csv(os.path.join(QE, "main", "results", "scores_wide.csv"), dtype={"review_id": str})
    return w[["review_id", "run1", "run2"]]


def metrics(y, pred):
    """Agreement between predictions and labels."""
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    err = np.abs(pred - y)
    return {"n": len(y), "MAE": err.mean(), "RMSE": np.sqrt(((pred - y) ** 2).mean()),
            "within 1": (err <= 1).mean(), "within 0.5": (err <= 0.5).mean(),
            "Spearman": spearmanr(y, pred)[0] if len(set(np.round(pred, 6))) > 1 else float("nan")}


def fmt(m):
    return (f"n={m['n']:4d}  MAE {m['MAE']:.2f}  RMSE {m['RMSE']:.2f}  within 1 point {m['within 1']:.0%}  "
            f"within 0.5 {m['within 0.5']:.0%}  rank corr. {m['Spearman']:.2f}")

"""Step 4: does averaging the saved transformer predictions beat a single model?

No training and no GPU: it only reads the prediction files that step 3 already wrote for the
400 test reviews. Also gives a rough idea of what a straight-line calibration would add.

  python scripts/04_ensemble.py
"""
import os
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

from common import metrics, fmt, ROOT

# the prediction files already in the repo (local = own laptop, colab = teammate's run)
FILES = {
    "xlmr_local":       "results_local/transformer_xlm-roberta-base_predictions.csv",
    "xlmr_colab":       "results_colab/transformer_xlm-roberta-base_predictions.csv",
    "bangla_local":     "results_local/transformer_csebuetnlp_banglabert_predictions.csv",
    "bangla_colab":     "results_colab/transformer_csebuetnlp_banglabert_predictions.csv",
    "muril_local":      "results_local/transformer_google_muril-base-cased_predictions.csv",
    "muril_colab":      "results_colab/transformer_google_muril-base-cased_predictions.csv",
}

# every combination to try: name -> models to average
COMBOS = {
    "xlmr local + colab":             ["xlmr_local", "xlmr_colab"],
    "xlmr + banglabert (local)":      ["xlmr_local", "bangla_local"],
    "xlmr + banglabert (colab)":      ["xlmr_colab", "bangla_colab"],
    "all 3 models (local)":           ["xlmr_local", "bangla_local", "muril_local"],
    "xlmr + banglabert, both runs":   ["xlmr_local", "xlmr_colab", "bangla_local", "bangla_colab"],
}


def read(path):
    return pd.read_csv(os.path.join(ROOT, path), dtype={"review_id": str}, encoding="utf-8-sig")


# one table: review info, true score, and one prediction column per run
first = read(next(iter(FILES.values())))
data = first[["review_id", "platform", "language", "score"]].copy()
for name, path in FILES.items():
    d = read(path)[["review_id", "predicted"]].rename(columns={"predicted": name})
    data = data.merge(d, on="review_id", how="left")
assert data.notna().all().all(), "some reviews are missing in a prediction file"
y = data["score"].values


def show(name, pred):
    print(f"  {name:30s} {fmt(metrics(y, np.clip(pred, 1, 10)))}")


print("SINGLE RUNS")
for n in FILES:
    show(n, data[n].values)

print("\nAVERAGES")
avg = {}
for name, cols in COMBOS.items():
    avg[name] = data[cols].mean(axis=1).values
    show(name, avg[name])

# straight-line calibration, each review corrected by a line fitted on the other reviews
# (estimate only: the real line should be fitted on validation predictions)
print("\nAVERAGE + STRAIGHT-LINE CORRECTION (5-fold estimate on the test set)")
for name in ["xlmr + banglabert, both runs", "xlmr local + colab"]:
    p, fixed = avg[name], np.zeros(len(y))
    for tr, te in KFold(5, shuffle=True, random_state=299).split(p):
        a, b = np.polyfit(p[tr], y[tr], 1)
        fixed[te] = a * p[te] + b
    show(name, fixed)
    a, b = np.polyfit(p, y, 1)
    print(f"    line on all 400: score = {a:.2f} * prediction + {b:.2f}")

# where the best average helps or not, by platform
best = "xlmr + banglabert, both runs"
print(f"\nBY PLATFORM: {best} vs xlmr local")
for plat, part in data.assign(avg=avg[best]).groupby("platform"):
    print(f"  {plat:10s} avg MAE {metrics(part['score'], part['avg'])['MAE']:.3f}   "
          f"xlmr local MAE {metrics(part['score'], part['xlmr_local'])['MAE']:.3f}")

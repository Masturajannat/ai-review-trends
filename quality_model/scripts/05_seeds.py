"""Step 5: how stable is a model across seeds, and does averaging the seeds help?

Reads the test predictions that 03_train_transformer.py wrote for one model trained with several
seeds (seed 299 = transformer_<name>_predictions.csv, others = transformer_<name>_seedN_predictions.csv)
in the results folder of the current RUN_TAG. No training, no GPU.

Reports, on the 400 test reviews:
  - each seed's numbers, and their mean and spread (what to put in the report: "MAE 0.66 +- 0.01")
  - the average of all seeds' predictions (a seed ensemble), overall and by platform and language

  python scripts/05_seeds.py --model xlm-roberta-base
  python scripts/05_seeds.py --model xlm-roberta-base --model xlm-roberta-large      (several models)

Writes results[_<tag>]/seeds_<name>.txt for each model.
"""
import argparse, glob, os, re
import numpy as np
import pandas as pd

from common import metrics, fmt, RESULTS

ap = argparse.ArgumentParser()
ap.add_argument("--model", action="append", required=True)
a = ap.parse_args()


def runs(name):
    """{seed: predictions table} for one model."""
    out = {}
    for f in glob.glob(os.path.join(RESULTS, f"transformer_{name}*_predictions.csv")):
        m = re.fullmatch(rf"transformer_{re.escape(name)}(?:_seed(\d+))?_predictions\.csv", os.path.basename(f))
        if m:
            out[int(m.group(1) or 299)] = pd.read_csv(f, dtype={"review_id": str}, encoding="utf-8-sig")
    return dict(sorted(out.items()))


def summary(model):
    name = model.replace("/", "_")
    rs = runs(name)
    if not rs:
        raise SystemExit(f"no prediction files for {model} in {RESULTS}")
    base = next(iter(rs.values()))[["review_id", "platform", "language", "score"]]
    lines = [f"SEEDS: {model}   ({len(rs)} run{'s' if len(rs) != 1 else ''}, folder {os.path.basename(RESULTS)})", "",
             "EACH SEED (test set, 400 reviews)"]
    per, preds = [], []
    for seed, d in rs.items():
        d = base[["review_id"]].merge(d[["review_id", "predicted"]], on="review_id")
        m = metrics(base["score"], d["predicted"])
        per.append(m); preds.append(d["predicted"].values)
        lines.append(f"  seed {seed:<5d} {fmt(m)}")
    if len(per) > 1:
        lines += ["", "MEAN AND SPREAD OVER SEEDS (report these)"]
        for k, f in [("MAE", ".3f"), ("RMSE", ".3f"), ("within 1", ".1%"), ("within 0.5", ".1%"), ("Spearman", ".3f")]:
            v = np.array([p[k] for p in per])
            lines.append(f"  {k:10s} {v.mean():{f}} +- {v.std(ddof=1):{f}}   (min {v.min():{f}}, max {v.max():{f}})")
        avg = np.mean(preds, axis=0)
        ens = base.assign(predicted=avg)
        lines += ["", f"AVERAGE OF THE {len(per)} SEEDS' PREDICTIONS (seed ensemble)", f"  all          {fmt(metrics(ens['score'], avg))}"]
        for col in ["platform", "language"]:
            for g, part in ens.groupby(col):
                lines.append(f"  {g:12s} {fmt(metrics(part['score'], part['predicted']))}")
        band = pd.cut(ens["score"], [0, 3, 5, 7, 10], labels=["label 1-3", "label 3.5-5", "label 5.5-7", "label 7.5-10"])
        for g, part in ens.groupby(band, observed=True):
            lines.append(f"  {g:12s} {fmt(metrics(part['score'], part['predicted']))}   "
                         f"mean error {(part['predicted'] - part['score']).mean():+.2f}")
        ens.round(3).to_csv(os.path.join(RESULTS, f"seeds_{name}_ensemble_predictions.csv"), index=False,
                            encoding="utf-8-sig")
    txt = "\n".join(lines)
    open(os.path.join(RESULTS, f"seeds_{name}.txt"), "w", encoding="utf-8").write(txt + "\n")
    print(txt + "\n")


for m in a.model:
    summary(m)

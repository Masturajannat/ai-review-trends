"""Rokomari check: are long reviews cut at 256 tokens, and are those the ones the model misses?

Run from quality_model/:  python rokomari_check\01_token_lengths.py
Needs the xlm-roberta-base tokenizer (downloaded on first run) and results_local / results_colab.
Only the xlm-roberta tokenizer is used, so BanglaBERT and MuRIL may cut slightly differently.
"""
import os
import sys
import pandas as pd
from transformers import AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                        # quality_model/
sys.path.insert(0, os.path.join(ROOT, "scripts"))   # to reuse load() from common.py
from common import load

MAX_LEN = 256                                       # same limit as 03_train_transformer.py
OUT = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)

tok = AutoTokenizer.from_pretrained("xlm-roberta-base")
train, test = load()


def add_tokens(d):
    # token count per review, special tokens included like in training
    ids = tok(d["text_original"].tolist(), truncation=False)["input_ids"]
    d["tokens"] = [len(x) for x in ids]
    d["cut"] = d["tokens"] > MAX_LEN
    return d


train, test = add_tokens(train), add_tokens(test)

lines = []


def say(s=""):
    print(s)
    lines.append(s)


# how many reviews lose their ending, per platform
for name, d in (("TRAIN", train), ("TEST (400 main-run reviews)", test)):
    say(f"{name}: share of reviews longer than {MAX_LEN} tokens")
    for plat, g in d.groupby("platform"):
        say(f"  {plat:9s} n={len(g):5d}  cut {g['cut'].mean():5.1%}  median tokens {g['tokens'].median():.0f}")
    say()

# test error of xlm-roberta, reviews kept whole vs cut
for run in ("results_local", "results_colab"):
    f = os.path.join(ROOT, run, "transformer_xlm-roberta-base_predictions.csv")
    if not os.path.exists(f):
        continue
    pred = pd.read_csv(f, dtype={"review_id": str}, encoding="utf-8-sig")[["review_id", "predicted"]]
    d = test.merge(pred, on="review_id")
    d["err"] = (d["predicted"] - d["score"]).abs()
    say(f"{run}: xlm-roberta test MAE, reviews kept whole vs cut")
    for plat in ("Rokomari", "Daraz", "Shajgoj"):
        g = d[d["platform"] == plat]
        parts = [f"{'cut  ' if c else 'whole'} n={len(h):3d} MAE {h['err'].mean():.2f}" for c, h in g.groupby("cut")]
        say(f"  {plat:9s} " + "   |   ".join(parts))
    say()
    if run == "results_local":
        # the 15 worst Rokomari misses, to read by hand
        worst = d[d["platform"] == "Rokomari"].sort_values("err", ascending=False).head(15)
        cols = ["review_id", "language", "n_words", "tokens", "cut", "score", "predicted", "text_original"]
        worst[cols].to_csv(os.path.join(OUT, "rokomari_worst_local.csv"), index=False, encoding="utf-8-sig")

open(os.path.join(OUT, "token_lengths.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("saved to", OUT)

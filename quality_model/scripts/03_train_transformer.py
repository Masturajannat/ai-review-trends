"""Step 3: fine-tune a multilingual transformer to predict the review-quality score.

Same data and test set as steps 1 and 2. The 6,922 training reviews are split 90/10 into
train and validation (stratified by score); after every epoch the model is checked on the
validation reviews and the best epoch is kept. The 400 main-run reviews are used once, at the end.

Needs a GPU (Google Colab's free T4 is enough: about 10 minutes per model). It also runs on a
laptop GPU; with little GPU memory use a smaller batch, e.g. --batch 8.

  python scripts/03_train_transformer.py --model xlm-roberta-base
  python scripts/03_train_transformer.py --model google/muril-base-cased
  python scripts/03_train_transformer.py --model csebuetnlp/banglabert
  python scripts/03_train_transformer.py --model distilbert-base-multilingual-cased --batch 8   (small GPU)

Models worth comparing
  xlm-roberta-base                      100 languages; the standard multilingual model
  google/muril-base-cased               Indian languages incl. Bangla AND their romanised forms (Banglish)
  csebuetnlp/banglabert                 Bangla-only pre-training (BUET)
  distilbert-base-multilingual-cased    half the size, for small GPUs and fast scoring on a laptop

Writes, with <name> = the model name without slashes:
  results/transformer_<name>_results.txt        numbers, in the same form as the baseline
  results/transformer_<name>_predictions.csv    the score for each of the 400 test reviews
  results/model_comparison.csv                  one row per model trained so far (plus the baseline)
  models/<name>/                                the fine-tuned model (large; not committed to git)

  --test-run   trains a tiny untrained model for one epoch to check that everything works
               (no download, no GPU; the numbers mean nothing)
"""
import argparse, json, os, time
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

from common import load, gemini_runs, metrics, fmt, RESULTS, MODELS

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="xlm-roberta-base")
ap.add_argument("--epochs", type=int, default=5)
ap.add_argument("--lr", type=float, default=2e-5)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--max-len", type=int, default=256, help="tokens kept per review; longer reviews are cut")
ap.add_argument("--seed", type=int, default=299)
ap.add_argument("--no-save", action="store_true", help="do not save the fine-tuned model")
ap.add_argument("--test-run", action="store_true")
a = ap.parse_args()

NAME = "test_run" if a.test_run else a.model.replace("/", "_")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def split_train_val(train, seed, share=0.1):
    """90/10 split of the training reviews, keeping the mix of scores the same in both parts."""
    rng = np.random.default_rng(seed)
    level = train["score"].round().clip(1, 9)
    val = np.concatenate([rng.choice(idx, max(1, round(len(idx) * share)), replace=False)
                          for idx in [np.where(level == l)[0] for l in sorted(level.unique())]])
    mask = np.zeros(len(train), bool); mask[val] = True
    return train[~mask].reset_index(drop=True), train[mask].reset_index(drop=True)


def tiny_model(texts):
    """An untrained toy model and tokenizer built on the spot, only for --test-run."""
    from tokenizers import Tokenizer, models, trainers, pre_tokenizers
    from transformers import PreTrainedTokenizerFast, BertConfig, BertForSequenceClassification
    tok = Tokenizer(models.WordPiece(unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    tok.train_from_iterator(texts, trainers.WordPieceTrainer(
        vocab_size=2000, special_tokens=["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"]))
    fast = PreTrainedTokenizerFast(tokenizer_object=tok, pad_token="[PAD]", unk_token="[UNK]",
                                   cls_token="[CLS]", sep_token="[SEP]", mask_token="[MASK]")
    cfg = BertConfig(vocab_size=fast.vocab_size, hidden_size=64, num_hidden_layers=2, num_attention_heads=2,
                     intermediate_size=128, max_position_embeddings=128, num_labels=1)
    return fast, BertForSequenceClassification(cfg)


def batches(tok, texts, labels, batch, shuffle, max_len):
    def collate(rows):
        enc = tok([r[0] for r in rows], truncation=True, max_length=max_len, padding=True, return_tensors="pt")
        enc.pop("token_type_ids", None)
        enc["labels"] = torch.tensor([r[1] for r in rows], dtype=torch.float)
        return enc
    return DataLoader(list(zip(texts, labels)), batch_size=batch, shuffle=shuffle, collate_fn=collate)


@torch.no_grad()
def predict(model, loader, mean, std):
    model.eval()
    out = []
    for b in loader:
        b.pop("labels")
        b = {k: v.to(DEVICE) for k, v in b.items()}
        with torch.autocast(DEVICE, enabled=DEVICE == "cuda"):
            out.append(model(**b).logits.float().squeeze(-1).cpu())
    return np.clip(torch.cat(out).numpy() * std + mean, 1, 10)


def main():
    torch.manual_seed(a.seed); np.random.seed(a.seed)
    os.makedirs(RESULTS, exist_ok=True); os.makedirs(MODELS, exist_ok=True)
    train_all, test = load()
    if a.test_run:
        train_all, a.epochs, a.max_len = train_all.sample(600, random_state=a.seed).reset_index(drop=True), 1, 64
    train, val = split_train_val(train_all, a.seed)
    print(f"{NAME} on {DEVICE}" + (f" ({torch.cuda.get_device_name(0)})" if DEVICE == "cuda" else "")
          + f": train {len(train)}, validation {len(val)}, test {len(test)}", flush=True)
    if DEVICE == "cpu" and not a.test_run:
        print("WARNING: no GPU found. Training on a CPU takes hours. In Colab: Runtime > Change runtime type > T4 GPU.")

    if a.test_run:
        tok, model = tiny_model(train["text_original"].tolist())
    else:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        tok = AutoTokenizer.from_pretrained(a.model)
        model = AutoModelForSequenceClassification.from_pretrained(a.model, num_labels=1)
    model.to(DEVICE)

    # the model learns the score in standard units (mean 0, spread 1); predictions are converted back
    mean, std = float(train["score"].mean()), float(train["score"].std())
    z = lambda s: ((s - mean) / std).tolist()
    tr = batches(tok, train["text_original"].tolist(), z(train["score"]), a.batch, True, a.max_len)
    va = batches(tok, val["text_original"].tolist(), z(val["score"]), a.batch * 2, False, a.max_len)
    te = batches(tok, test["text_original"].tolist(), z(test["score"]), a.batch * 2, False, a.max_len)

    from transformers import get_linear_schedule_with_warmup
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = len(tr) * a.epochs
    sched = get_linear_schedule_with_warmup(opt, int(0.06 * steps), steps)
    scaler = torch.amp.GradScaler(enabled=DEVICE == "cuda")
    loss_fn = torch.nn.MSELoss()

    best, best_state, log, t0 = None, None, [], time.time()
    for epoch in range(1, a.epochs + 1):
        model.train()
        total = 0.0
        for i, b in enumerate(tr, 1):
            b = {k: v.to(DEVICE) for k, v in b.items()}
            labels = b.pop("labels")
            with torch.autocast(DEVICE, enabled=DEVICE == "cuda"):
                loss = loss_fn(model(**b).logits.float().squeeze(-1), labels)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt); scaler.update(); sched.step()
            total += loss.item()
            if i % 100 == 0:
                print(f"  epoch {epoch} step {i}/{len(tr)}  loss {total / i:.3f}", flush=True)
        m = metrics(val["score"], predict(model, va, mean, std))
        log.append(f"  epoch {epoch}: train loss {total / len(tr):.3f}   validation {fmt(m)}")
        print(log[-1] + f"   ({time.time() - t0:.0f}s)", flush=True)
        if best is None or m["MAE"] < best[1]["MAE"]:
            best = (epoch, m)
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)

    pred = predict(model, te, mean, std)
    tm = metrics(test["score"], pred)
    g = test[["review_id"]].merge(gemini_runs(), on="review_id")
    gm = metrics(g["run2"], g["run1"])
    lines = [f"TRANSFORMER FOR THE REVIEW-QUALITY SCORE: {a.model if not a.test_run else 'TEST RUN (numbers mean nothing)'}",
             f"train {len(train)}, validation {len(val)} (from full + pilot), test {len(test)} (main run, never trained on)",
             f"epochs {a.epochs}, learning rate {a.lr}, batch {a.batch}, max {a.max_len} tokens, seed {a.seed}, "
             f"device {DEVICE}, {time.time() - t0:.0f}s", "", "TRAINING"] + log + [
             f"  kept: epoch {best[0]} (lowest validation MAE)", "",
             "TEST: THE 400 MAIN-RUN REVIEWS", f"  {NAME[:24]:24s} {fmt(tm)}"]
    base_file = os.path.join(RESULTS, "baseline_predictions.csv")
    out = test[["review_id", "platform", "language", "n_words", "score"]].copy()
    out["predicted"] = pred.round(2)
    if os.path.exists(base_file):
        base = pd.read_csv(base_file, dtype={"review_id": str})[["review_id", "predicted"]]
        out = out.merge(base.rename(columns={"predicted": "baseline"}), on="review_id", how="left")
        lines.append(f"  {'baseline (TF-IDF + ridge)':24s} {fmt(metrics(out['score'], out['baseline']))}")
    lines += [f"  {'Gemini run 1 vs run 2':24s} {fmt(gm)}   (yardstick)", "", "BY LANGUAGE, PLATFORM AND SCORE BAND (test set)"]
    band = pd.cut(out["score"], [0, 3, 5, 7, 10], labels=["label 1-3", "label 3.5-5", "label 5.5-7", "label 7.5-10"])
    for col in [out["language"], out["platform"], band]:
        for name, part in out.groupby(col, observed=True):
            lines.append(f"  {str(name):13s} {fmt(metrics(part['score'], part['predicted']))}   "
                         f"mean error {(part['predicted'] - part['score']).mean():+.2f}")
    txt = "\n".join(lines)
    print("\n" + txt)
    open(os.path.join(RESULTS, f"transformer_{NAME}_results.txt"), "w", encoding="utf-8").write(txt + "\n")
    out.to_csv(os.path.join(RESULTS, f"transformer_{NAME}_predictions.csv"), index=False, encoding="utf-8-sig")

    if not a.test_run:
        # one table of all models trained so far
        table = os.path.join(RESULTS, "model_comparison.csv")
        rows = pd.read_csv(table) if os.path.exists(table) else pd.DataFrame()
        add = [dict(model=a.model, **{k: round(v, 3) for k, v in tm.items()}, best_epoch=best[0], seed=a.seed)]
        if "baseline" in out and not (len(rows) and (rows["model"] == "baseline (TF-IDF + ridge)").any()):
            add.append(dict(model="baseline (TF-IDF + ridge)",
                            **{k: round(v, 3) for k, v in metrics(out["score"], out["baseline"]).items()}))
            add.append(dict(model="Gemini run 1 vs run 2", **{k: round(v, 3) for k, v in gm.items()}))
        rows = pd.concat([rows[rows["model"] != a.model] if len(rows) else rows, pd.DataFrame(add)], ignore_index=True)
        rows.to_csv(table, index=False)
        print("\nALL MODELS SO FAR\n" + rows[["model", "MAE", "within 1", "Spearman"]].to_string(index=False))
        if not a.no_save:
            dst = os.path.join(MODELS, NAME)
            model.save_pretrained(dst); tok.save_pretrained(dst)
            json.dump({"mean": mean, "std": std, "max_len": a.max_len, "base_model": a.model,
                       "test": {k: float(v) for k, v in tm.items()}}, open(os.path.join(dst, "score_scale.json"), "w"))
            print(f"model saved to {dst}")


if __name__ == "__main__":
    main()

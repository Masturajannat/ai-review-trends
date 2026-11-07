"""Main stage: compare the human judgments with the LLM scores.

Reads every pairs_filled*.csv in main/results (one file per rater, from the
page made by 05b; columns pair_id, better_AorB). A file without pair_id is read
in the order of pairs_key.csv. If single_filled.csv exists (the old single-score
sheet), its rank correlation is reported too. Writes check_summary.txt.
"""
import glob, math, os
import pandas as pd
from common import folder

res = os.path.join(folder("main"), "results")
out = []
def say(s=""):
    print(s); out.append(s)

def wilson(k, n, z=1.96):
    # 95% interval for a proportion
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - w, c + w

key = pd.read_csv(os.path.join(res, "pairs_key.csv"))
key["llm_pick"] = (key["_score_a"] > key["_score_b"]).map({True: "A", False: "B"})
key["hw"] = key.apply(lambda r: r["_words_a"] if r["llm_pick"] == "A" else r["_words_b"], axis=1)
key["lw"] = key.apply(lambda r: r["_words_b"] if r["llm_pick"] == "A" else r["_words_a"], axis=1)
key["higher_is_longer"] = key["hw"] > key["lw"]

files = sorted(glob.glob(os.path.join(res, "pairs_filled*.csv")))
if not files:
    raise SystemExit("no pairs_filled*.csv found in " + res)

picks = {}      # rater -> Series indexed by pair_id (A / B / ? / blank)
for f in files:
    d = pd.read_csv(f)
    nm = os.path.splitext(os.path.basename(f))[0].replace("pairs_filled", "").strip("_") or "rater"
    if "pair_id" in d.columns:
        s = d.set_index("pair_id")["better_AorB"]
    else:
        s = pd.Series(d["better_AorB"].values, index=key["pair_id"].values[:len(d)])
    picks[nm] = s.astype(str).str.strip().str.upper().reindex(key["pair_id"]).fillna("")

say(f"pairs in key: {len(key)}; raters: {', '.join(picks)}")
say(f"(LLM scored the pair's high review {key[['_score_a','_score_b']].max(axis=1).min():.1f}+ "
    f"against a middle review)")
say()

def agree_line(label, mask, pick):
    k = key[mask]
    n = len(k)
    if n == 0:
        return
    hit = int((pick[mask] == k["llm_pick"]).sum())
    lo, hi = wilson(hit, n)
    say(f"{label}: {hit}/{n} = {hit/n:.0%} (95% CI {lo:.0%}-{hi:.0%})")

say("HUMANS vs LLM (did the rater pick the review the LLM scored higher?)")
pooled = []
for nm, pk in picks.items():
    ok = pk.isin(["A", "B"]).values
    say(f"[{nm}] answered A/B: {int(ok.sum())}, can't decide or blank: {int((~ok).sum())}")
    agree_line("  all pairs", ok, pk.reset_index(drop=True))
    agree_line("  higher-scored is longer", ok & key["higher_is_longer"].values, pk.reset_index(drop=True))
    agree_line("  higher-scored is shorter/equal", ok & ~key["higher_is_longer"].values, pk.reset_index(drop=True))
    pooled.append(pk.reset_index(drop=True))

if len(picks) > 1:
    say()
    say("ALL RATERS TOGETHER (each answer counted; raters see the same pairs, so the interval is optimistic)")
    hit = n = hl = nl = hs = ns = 0
    for pk in pooled:
        ok = pk.isin(["A", "B"]).values
        m = (pk == key["llm_pick"]).values
        hit += int((m & ok).sum()); n += int(ok.sum())
        lm = key["higher_is_longer"].values
        hl += int((m & ok & lm).sum()); nl += int((ok & lm).sum())
        hs += int((m & ok & ~lm).sum()); ns += int((ok & ~lm).sum())
    lo, hi = wilson(hit, n)
    say(f"  all: {hit}/{n} = {hit/n:.0%} (95% CI {lo:.0%}-{hi:.0%})")
    if nl: say(f"  higher-scored is longer: {hl}/{nl} = {hl/nl:.0%}")
    if ns: say(f"  higher-scored is shorter/equal: {hs}/{ns} = {hs/ns:.0%}")

    say()
    say("RATER vs RATER (same pair, both answered A/B)")
    names = list(picks)
    for x in range(len(names)):
        for y in range(x + 1, len(names)):
            a, b = pooled[x], pooled[y]
            ok = a.isin(["A", "B"]) & b.isin(["A", "B"])
            n2 = int(ok.sum())
            if not n2:
                continue
            same = int((a[ok] == b[ok]).sum())
            po = same / n2
            pa_ = (a[ok] == "A").mean(); pb_ = (b[ok] == "A").mean()
            pe = pa_ * pb_ + (1 - pa_) * (1 - pb_)
            kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")
            say(f"  {names[x]} vs {names[y]}: agree on {same}/{n2} = {po:.0%}, Cohen's kappa = {kappa:.2f}")
    # consensus pairs
    allok = pd.concat(pooled, axis=1).apply(lambda r: all(v in ("A", "B") for v in r), axis=1)
    cons = allok & pd.concat(pooled, axis=1).apply(lambda r: len(set(r)) == 1, axis=1)
    if int(cons.sum()):
        hit = int((pooled[0][cons] == key["llm_pick"][cons]).sum())
        say(f"  pairs where all raters chose the same review: {int(cons.sum())}; "
            f"LLM agrees on {hit}/{int(cons.sum())} = {hit/int(cons.sum()):.0%}")

sf = os.path.join(res, "single_filled.csv")
if os.path.exists(sf):
    sc = pd.read_csv(os.path.join(res, "scores_raw.csv"))
    sc = sc[sc["prompt_version"] == sc["prompt_version"].iloc[-1]]
    sc = sc.groupby("review_id")["overall"].mean().rename("llm")
    one = pd.read_csv(sf).merge(sc, on="review_id").dropna(subset=["my_score"])
    say()
    say(f"single: Spearman rho = {one['my_score'].rank().corr(one['llm'].rank()):.2f} on {len(one)} reviews")

with open(os.path.join(res, "check_summary.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")

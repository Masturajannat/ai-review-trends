"""
STEP 2b - Quality check of the labeled set BEFORE you score it.  (No internet, no key.)

Reads  : analysis/labeled_set.csv
Writes : analysis/labeled_set_flags.csv      pairs with a problem + the reason
         (with --drop) analysis/labeled_set.csv is rewritten WITHOUT the flagged pairs;
                       the original is first saved as analysis/labeled_set_unfiltered.csv

Run:   python 02b_check_labeled_set.py            # look first
       python 02b_check_labeled_set.py --drop     # then remove flagged pairs (say so in your report)

What it looks for (each breaks the "fair human vs AI pair" idea):
  ai_wrong_language       ORIGINAL-ENGLISH path only: the AI text is Bengali/Banglish but the human text is English.
                          (Those texts are not translated afterwards, so detector would see two different languages.
                          On the Bengali/Banglish path both texts are translated to English, so a language
                          or script difference there is harmless and is NOT flagged.)
  not_translated          a text on the Bengali/Banglish path still contains Bengali script after translation
  near_identical          the AI text is almost the same as the human text (the model barely rewrote it)

With --reset-flagged: deletes the saved AI rewrites of the ai_wrong_language pairs from the cache, so that running
  python 02_build_labeled_set.py <same numbers as before>
regenerates ONLY those rewrites (with a stricter English-only prompt).
"""
import argparse
import difflib
import re
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
F = BASE / "analysis" / "labeled_set.csv"
FLAGS = BASE / "analysis" / "labeled_set_flags.csv"
BACKUP = BASE / "analysis" / "labeled_set_unfiltered.csv"

ap = argparse.ArgumentParser()
ap.add_argument("--drop", action="store_true", help="remove flagged pairs from labeled_set.csv")
ap.add_argument("--reset-flagged", action="store_true", help="forget the bad English-path rewrites so step 2 redoes them")
args = ap.parse_args()

BENGALI = re.compile(r"[ঀ-৿]")
BANGLISH = re.compile(r"(?i)\b(valo|bhalo|khub|onek|onk|kore|korar|moto|darun|lagse|lagche|jinish|ekta|ei|eta|"
                      r"amar|amr|jonno|kintu|ektu|thakle|hoyeche|hoise|chilo|silo|nai|theke|diye|dise|"
                      r"pelam|peyechi|kinlam|dam|dami|sundor|shundor)\b")


def lang(text):
    t = str(text)
    if BENGALI.search(t):
        return "bengali_script"
    if len(BANGLISH.findall(t)) >= 2:
        return "banglish"
    return "english"


df = pd.read_csv(F, encoding="utf-8-sig")
h = df[df.label == 0].set_index("pair_id")
a = df[df.label == 1].set_index("pair_id")
pairs = h.join(a, lsuffix="_h", rsuffix="_a", how="inner")

rows = []
for pid, r in pairs.iterrows():
    reasons = []
    lh, la = lang(r.text_original_h), lang(r.text_original_a)
    if r.path_h == "english" and la != "english":
        reasons.append(f"ai_wrong_language (human={lh}, ai={la})")
    if r.path_h == "translated":
        if BENGALI.search(str(r.text_for_detector_h)) or BENGALI.search(str(r.text_for_detector_a)):
            reasons.append("not_translated")
    sim = difflib.SequenceMatcher(None, str(r.text_for_detector_h).lower(), str(r.text_for_detector_a).lower()).ratio()
    if sim > 0.85:
        reasons.append(f"near_identical ({sim:.2f})")
    if reasons:
        rows.append(dict(pair_id=pid, path=r.path_h, reasons="; ".join(reasons),
                         human_original=str(r.text_original_h)[:120], ai_original=str(r.text_original_a)[:120]))

flags = pd.DataFrame(rows)
flags.to_csv(FLAGS, index=False, encoding="utf-8-sig")

print(f"{len(pairs)} pairs checked")
print(pairs.groupby("path_h").size().rename("pairs").to_string())
print("\nAverage words (text sent to detector):")
print(pd.DataFrame({"human": h.groupby("path").word_count.mean(), "ai": a.groupby("path").word_count.mean()}).round(1).to_string())
print(f"\nFlagged pairs: {len(flags)}")
if len(flags):
    print(flags.groupby(["path", flags.reasons.str.split(" ").str[0]]).size().to_string())
    print(f"(details in {FLAGS.name} - open it and read the rows)")

print("\nRANDOM PAIRS - read these yourself (text the detector will see):")
for path in pairs.path_h.unique():
    sub = pairs[pairs.path_h == path].sample(min(3, (pairs.path_h == path).sum()), random_state=1)
    for pid, r in sub.iterrows():
        print(f"\n[{path} {pid}]\n  HUMAN: {str(r.text_for_detector_h)[:200]!r}\n  AI   : {str(r.text_for_detector_a)[:200]!r}")

if args.reset_flagged:
    import json
    cache_f = BASE / "analysis" / "labeled_cache.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8"))
    bad = flags[flags.reasons.str.startswith("ai_wrong_language")] if len(flags) else flags
    n = 0
    for pid in bad.pair_id:
        rid = str(pairs.loc[pid, "source_review_id_h"])
        if cache["ai"].pop(pid + "|" + rid, None) is not None:
            n += 1
    cache_f.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"\nForgot {n} bad AI rewrites. Now run step 2 again with the SAME numbers as before, then re-run this check.")

if args.drop and len(flags):
    df.to_csv(BACKUP, index=False, encoding="utf-8-sig")
    keep = df[~df.pair_id.isin(flags.pair_id)]
    keep.to_csv(F, index=False, encoding="utf-8-sig")
    print(f"\nDropped {len(flags)} pairs. Original saved as {BACKUP.name}. {keep.pair_id.nunique()} pairs remain.")
    print(keep.groupby(["path", "label_name"]).size().unstack().to_string())
elif args.drop:
    print("\nNothing to drop.")
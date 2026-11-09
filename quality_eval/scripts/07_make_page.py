import argparse
import html
import os

import pandas as pd
from common import folder, FOLDERS

ap = argparse.ArgumentParser()
ap.add_argument("--folder", default="pilot", choices=FOLDERS)
a = ap.parse_args()

results = os.path.join(folder(a.folder), "results")
df = pd.read_csv(os.path.join(results, "scores_wide.csv"))

# lowest score first
df = df.sort_values("mean")

style = """
body { font-family: Arial, sans-serif; max-width: 800px; margin: 20px auto; background: #f4f4f4; }
.card { background: white; padding: 12px 16px; margin: 10px 0; border-radius: 6px; }
.score { font-size: 20px; font-weight: bold; }
.info { color: #666; font-size: 13px; }
.text { margin: 8px 0; white-space: pre-wrap; }
.reason { background: #eef3ff; padding: 6px 10px; font-size: 14px; }
"""

parts = []
parts.append("<!DOCTYPE html>")
parts.append("<html><head><meta charset='utf-8'>")
parts.append("<title>Reviews</title>")
parts.append("<style>" + style + "</style></head><body>")
parts.append("<h1>" + a.folder + " reviews (" + str(len(df)) + ")</h1>")

for _, r in df.iterrows():
    parts.append("<div class='card'>")
    runs = ", ".join(f"{c} {r[c]:g}" for c in df.columns if c.startswith("run") and c[3:].isdigit() and pd.notna(r[c]))
    parts.append("<div class='score'>Score " + str(r["mean"]) + " (" + runs + ")</div>")
    info = [r["platform"], r["language"], str(r["n_words"]) + " words", r["product_name"], "id " + str(r["review_id"])]
    parts.append("<div class='info'>" + html.escape(" | ".join(str(x) for x in info)) + "</div>")
    parts.append("<div class='text'>" + html.escape(str(r["text_original"])) + "</div>")
    parts.append("<div class='reason'>" + html.escape(str(r["reason_run1"])) + "</div>")
    parts.append("</div>")

parts.append("</body></html>")

out = os.path.join(results, "review_page.html")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(parts))

print("saved", out)

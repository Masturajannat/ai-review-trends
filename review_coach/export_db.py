"""Write the Review Coach database to CSV files for the report, and print the headline numbers.

    cd review_coach
    python export_db.py                 # writes db_export/<table>.csv
    python export_db.py --out my_folder

Files: sessions, drafts, scores, suggestion_sets, suggestion_items, feedback, session_summary.
"""
import argparse, os
import db

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_export"))
a = ap.parse_args()

con = db.connect()
for p in db.export_csv(con, a.out):
    print("wrote", p)
s = db.summary(con)
pct = lambda v: "-" if v is None else f"{v:.0%}"
num = lambda v, f="{:.2f}": "-" if v is None else f.format(v)
print(f"""
sessions {s['sessions']}, drafts {s['drafts']}, scores {s['scores']}, suggestion sets {s['suggestion_sets']}
suggestions marked helpful:              {pct(s['helpful_share'])}
mean score change, first to last draft:  {num(s['mean_change'], '{:+.2f}')}
time to score: our model {num(s['model_ms'], '{:.0f}')} ms, Gemini {num(s['gemini_ms'], '{:.0f}')} ms""")

"""Main stage: a click-through page for the blind pair check.

Reads main/results/pairs_for_raters.csv and writes main/results/pair_page.html,
one self-contained file. Send that file to each rater. They open it in a browser,
type their name, click A or B for each pair, and download their answers as
pairs_filled_<name>.csv. Gemini's scores are not in the page.
Save the downloaded files in main/results/ and run 06_check_results.py.
"""
import json, os
import pandas as pd
from common import folder

res = os.path.join(folder("main"), "results")
p = pd.read_csv(os.path.join(res, "pairs_for_raters.csv"))
data = [dict(id=int(r.pair_id), pa=str(r.product_a), ra=str(r.review_a),
             pb=str(r.product_b), rb=str(r.review_b)) for r in p.itertuples()]
blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("\u2028", " ").replace("\u2029", " ")

PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Which review is more useful?</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:1000px;margin:0 auto;padding:16px;line-height:1.5;color:#1a1a1a;background:#fafafa}
 h1{font-size:1.25rem;margin:.2rem 0}
 .box{background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px;margin:12px 0}
 .cols{display:flex;gap:12px;flex-wrap:wrap}
 .col{flex:1 1 400px;background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px}
 .col h2{margin:0 0 4px;font-size:1.05rem}
 .prod{color:#666;font-size:.85rem;margin-bottom:8px;word-break:break-word}
 .txt{white-space:pre-wrap;word-break:break-word;font-size:1rem}
 button{font:inherit;padding:10px 18px;border-radius:8px;border:1px solid #888;background:#fff;cursor:pointer}
 button.pick{background:#1f5fbf;color:#fff;border-color:#1f5fbf;font-weight:600;width:100%;margin-top:12px;padding:14px}
 button.sel{outline:3px solid #f0a500}
 .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}
 .bar{height:8px;background:#e3e3e3;border-radius:4px;overflow:hidden}
 .bar>div{height:100%;background:#1f5fbf;width:0}
 input[type=text]{font:inherit;padding:8px;border:1px solid #888;border-radius:6px;min-width:220px}
 .small{color:#666;font-size:.85rem}
 .hide{display:none}
</style></head><body>
<h1>Which review is more useful to a buyer?</h1>

<div id="start" class="box">
 <p>For each pair, pick the review that would help a person decide whether to buy the product <b>from this shop</b> more.
 Judge the information in the review: specific, checkable detail, real use or a real purchase, a reason.
 Do not judge whether it is positive or negative, the language, spelling, or how long it is.
 If you really cannot decide, use "Can't decide".</p>
 <p><label>Your name (used in the file name): <input type="text" id="name" placeholder="e.g. rafi"></label></p>
 <button class="pick" id="go" style="width:auto">Start</button>
</div>

<div id="main" class="hide">
 <div class="row small"><span id="prog"></span></div>
 <div class="bar"><div id="barfill"></div></div>
 <div class="cols">
  <div class="col"><h2>Review A</h2><div class="prod" id="pa"></div><div class="txt" id="ra"></div>
   <button class="pick" id="btnA">A is more useful</button></div>
  <div class="col"><h2>Review B</h2><div class="prod" id="pb"></div><div class="txt" id="rb"></div>
   <button class="pick" id="btnB">B is more useful</button></div>
 </div>
 <div class="row">
  <button id="back">&larr; Back</button>
  <button id="unsure">Can't decide</button>
  <span class="small" id="cur"></span>
 </div>
</div>

<div id="done" class="box hide">
 <p><b>All pairs answered.</b> Download your answers and send the file back.</p>
 <button class="pick" id="dl" style="width:auto">Download my answers (CSV)</button>
 <div class="row"><button id="review">&larr; Go back and change an answer</button></div>
</div>

<script>
const PAIRS = __DATA__;
let name = "", i = 0, ans = {};
const $ = id => document.getElementById(id);
const KEY = "pairpage_" + PAIRS.length;

function save(){ try{ localStorage.setItem(KEY, JSON.stringify({name, i, ans})); }catch(e){} }
function load(){ try{ const s = JSON.parse(localStorage.getItem(KEY)||"null"); if(s){ name=s.name||""; i=s.i||0; ans=s.ans||{}; $("name").value=name; } }catch(e){} }

function show(){
  if(i >= PAIRS.length){ $("main").classList.add("hide"); $("done").classList.remove("hide"); save(); return; }
  $("done").classList.add("hide"); $("main").classList.remove("hide");
  const p = PAIRS[i];
  $("pa").textContent = p.pa; $("ra").textContent = p.ra;
  $("pb").textContent = p.pb; $("rb").textContent = p.rb;
  const n = Object.keys(ans).length;
  $("prog").textContent = "Pair " + (i+1) + " of " + PAIRS.length + "  (" + n + " answered)";
  $("barfill").style.width = (100*n/PAIRS.length) + "%";
  const c = ans[p.id];
  $("btnA").classList.toggle("sel", c === "A");
  $("btnB").classList.toggle("sel", c === "B");
  $("unsure").classList.toggle("sel", c === "?");
  $("cur").textContent = c ? ("Your current answer: " + (c==="?" ? "can't decide" : c)) : "";
  window.scrollTo(0,0);
}
function answer(v){ ans[PAIRS[i].id] = v; i++; save(); show(); }

$("go").onclick = () => {
  const v = $("name").value.trim().replace(/[^A-Za-z0-9_-]+/g, "_");
  if(!v){ alert("Please type your name first."); return; }
  name = v; $("start").classList.add("hide"); save(); show();
};
$("btnA").onclick = () => answer("A");
$("btnB").onclick = () => answer("B");
$("unsure").onclick = () => answer("?");
$("back").onclick = () => { if(i>0){ i--; save(); show(); } };
$("review").onclick = () => { i = PAIRS.length - 1; save(); show(); };
$("dl").onclick = () => {
  let csv = "pair_id,better_AorB,rater\r\n";
  for(const p of PAIRS){ csv += p.id + "," + (ans[p.id] || "") + "," + name + "\r\n"; }
  const url = URL.createObjectURL(new Blob([csv], {type:"text/csv"}));
  const a = document.createElement("a"); a.href = url; a.download = "pairs_filled_" + name + ".csv";
  document.body.appendChild(a); a.click(); a.remove();
};

load();
if(name && Object.keys(ans).length){ $("start").classList.add("hide"); show(); }
</script></body></html>
"""
out = os.path.join(res, "pair_page.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(PAGE.replace("__DATA__", blob))
print(len(data), "pairs ->", out)
print("send pair_page.html to each rater; they send back pairs_filled_<name>.csv; save those in", res)

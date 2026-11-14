"""Review Coach: write a product review, check it, see what to improve, check again.

    cd review_coach
    $env:GEMINI_API_KEY = "<your key>"      # optional; without it, use the mock judge
    python -m streamlit run app.py --server.headless true
"""
import html, os
import streamlit as st

import db
from evaluator import evaluate, CHECK_LABELS, CHECK_GROUPS, CRITERIA

st.set_page_config(page_title="Review Coach", layout="wide")

TEAL, ORANGE, AMBER, INK, MUTED, LINE = "#0F766E", "#C2410C", "#A16207", "#1B1D21", "#55585F", "#E2E2DC"
CRITERION_TEXT = {
    "specific": "Concrete details, not just “good” or “nice”",
    "personal": "Real use: how long, in what situation, what happened",
    "reasoned": "A reason, a good and a bad point, or a comparison",
    "relevant": "About this product, useful to the next buyer",
}
EXAMPLES = {
    "Banglish": ("Foaming Facial Cleanser 236 ml", "skincare",
                 "Product ta valo, delivery fast chilo. Original mone hocche. Recommended."),
    "বাংলা": ("দেয়াল (হার্ডকভার)", "book",
                 "বইটা ভালো লেগেছে। সবাই পড়তে পারেন।"),
    "English": ("Wireless Earbuds Pro", "product", "Good sound and nice design. Battery is ok."),
}

CSS = f"""
<style>
.rc-card {{ background:#FFFFFF; border:1px solid {LINE}; border-radius:14px; padding:20px 22px; margin-bottom:14px; color:{INK}; }}
.rc-title {{ font-weight:600; margin-bottom:10px; }}
.rc-score {{ display:flex; flex-wrap:wrap; gap:22px; align-items:center; }}
.rc-big {{ font-size:60px; font-weight:700; line-height:1; }}
.rc-bar {{ display:grid; grid-template-columns:repeat(10,minmax(0,1fr)); gap:4px; margin-bottom:8px; }}
.rc-bar span {{ height:8px; border-radius:4px; background:{LINE}; }}
.rc-four {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:16px; }}
@media (max-width: 640px) {{ .rc-four {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
.rc-mini {{ background:#F6F6F3; border-radius:10px; padding:10px 12px; }}
.rc-mini small {{ display:block; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:{MUTED}; }}
.rc-mini b {{ font-size:20px; }}
.rc-mini i {{ display:block; height:5px; border-radius:3px; background:{LINE}; margin-top:6px; overflow:hidden; }}
.rc-mini i u {{ display:block; height:5px; border-radius:3px; }}
.rc-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px 24px; }}
@media (max-width: 640px) {{ .rc-grid {{ grid-template-columns:1fr; }} }}
.rc-group h4 {{ margin:0 0 6px; font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:{MUTED}; }}
.rc-check {{ display:flex; gap:8px; align-items:center; margin:4px 0; }}
.rc-dot {{ width:16px; height:16px; border-radius:50%; flex:none; box-sizing:border-box; }}
.rc-tip {{ background:#FFF4EC; border-radius:10px; padding:12px 14px; margin:8px 0; }}
.rc-tip b {{ color:#9A3412; font-size:13px; text-transform:capitalize; }}
.rc-hist {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
.rc-pill {{ white-space:nowrap; flex:none; padding:6px 12px; border-radius:999px; background:#F1F1EC; font-size:14px; }}
.rc-muted {{ color:{MUTED}; font-size:13px; }}
.rc-crit {{ margin:8px 0; }} .rc-crit b {{ text-transform:capitalize; }}
.rc-step {{ display:flex; gap:12px; align-items:flex-start; margin:10px 0; }}
.rc-step span {{ flex:none; width:26px; height:26px; border-radius:50%; background:{TEAL}; color:#FFFFFF;
                 display:flex; align-items:center; justify-content:center; font-weight:700; font-size:13px; }}
</style>"""
# blank lines would end the HTML block and show the CSS as text
st.markdown("\n".join(line for line in CSS.splitlines() if line.strip()), unsafe_allow_html=True)


@st.cache_resource
def get_db():
    return db.connect()


con = get_db()
ss = st.session_state
for k, v in dict(sid=None, result=None, eval_id=None, rated=set(), product="", category="product",
                 review_text="").items():
    ss.setdefault(k, v)
esc = html.escape


def colour(share):
    return TEAL if share >= 0.7 else AMBER if share >= 0.5 else ORANGE


def use_example(name):
    ss.product, ss.category, ss.review_text = EXAMPLES[name]


def new_review():
    ss.sid = ss.result = ss.eval_id = None
    ss.review_text = ss.product = ""


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    judge = st.radio("Judge", ["gemini", "mock"], index=0 if has_key else 1,
                     format_func=lambda j: {"gemini": "Gemini (real score)",
                                            "mock": "Mock (no API, for testing)"}[j])
    if judge == "gemini" and not has_key:
        st.warning("GEMINI_API_KEY is not set in the terminal that started the app.")
    st.button("Start a new review", on_click=new_review)
    st.caption("Your review text is sent to Google's Gemini model to be checked when the Gemini judge is "
               "on. Nothing is posted anywhere. No names or emails are stored.")

st.markdown("<h1 style='margin-bottom:0'>Review Coach</h1>"
            "<p class='rc-muted'>Write in Bangla, Banglish or English. Check your review, follow the tips, "
            "and check again.</p>", unsafe_allow_html=True)

left, right = st.columns([5, 6], gap="large")

# ---------------------------------------------------------------- input
with left:
    st.subheader("Write your review")
    st.text_input("Product", key="product", placeholder="e.g. Foaming Facial Cleanser 236 ml")
    st.radio("Type", ["book", "skincare", "product"], key="category", horizontal=True,
             format_func=lambda c: {"book": "Book", "skincare": "Skincare", "product": "Other product"}[c])
    st.text_area("Your review", key="review_text", height=220,
                 placeholder="What did you buy, how long have you used it, what was good or bad?")
    st.caption(f"{len(ss.review_text.split())} words")
    go = st.button("Check my review", type="primary")

    st.caption("Or try an example:")
    for col, name in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(name, on_click=use_example, args=(name,), use_container_width=True)

    if go:
        product, category, review = ss.product, ss.category, ss.review_text
        if not review.strip():
            st.error("Write a review first.")
        else:
            if ss.sid is None:
                ss.sid = db.new_session(con, product, category)
            else:
                db.update_session(con, ss.sid, product, category)
            key = db.cache_key(judge, product, review)
            hit = db.cached(con, key)
            try:
                with st.spinner("Checking your review..."):
                    r = hit or evaluate(product, review, judge=judge)
                ss.eval_id, _ = db.save(con, ss.sid, review, r, key, from_cache=hit is not None)
                ss.result = r
            except Exception as e:
                st.error(str(e))

    # under the form: the drafts so far, with the score of each
    hist = db.history(con, ss.sid) if ss.sid else []
    if hist:
        rows = "".join(
            f"<div class='rc-check'><span class='rc-pill'>Draft {h['draft_no']}: <b>{h['score']}</b>/10</span>"
            f"<span class='rc-muted'>{esc(h['review_text'][:70])}{'…' if len(h['review_text']) > 70 else ''}</span></div>"
            for h in hist)
        change = hist[-1]["score"] - hist[0]["score"]
        note = f" ({'+' if change >= 0 else ''}{change} since the first)" if len(hist) > 1 else ""
        st.markdown(f"<div class='rc-card' style='margin-top:14px'><div class='rc-title'>Your drafts{note}</div>"
                    f"{rows}</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- results
with right:
    r = ss.result
    if r is None:
        steps = ["Write your review, the way you would on the shop's page.",
                 "Get a score out of 10, a score for each of the four criteria, and a checklist.",
                 "Add what the tips ask for and check again. Your score goes up."]
        st.markdown("<div class='rc-card'><div class='rc-title'>How it works</div>"
                    + "".join(f"<div class='rc-step'><span>{i}</span><div>{s}</div></div>"
                              for i, s in enumerate(steps, 1)) + "</div>", unsafe_allow_html=True)
        st.markdown("<div class='rc-card'><div class='rc-title'>What you will be scored on</div>"
                    + "".join(f"<div class='rc-crit'><b>{c}</b><br><span class='rc-muted'>{CRITERION_TEXT[c]}"
                              f"</span></div>" for c in CRITERIA) + "</div>", unsafe_allow_html=True)
    else:
        color = colour(r["score"] / 10)
        bar = "".join(f"<span style='background:{color if i < r['score'] else LINE}'></span>" for i in range(10))
        nxt = f"Next level ({esc(r['next_level'])})" if r["next_level"] else "Top level reached."
        minis = []
        for c in CRITERIA:
            got, of = sum(r["checks"][k] for k in CHECK_GROUPS[c]), len(CHECK_GROUPS[c])
            cc = colour(got / of)
            minis.append(f"<div class='rc-mini'><small>{c}</small><b style='color:{cc}'>{got}</b>"
                         f"<span class='rc-muted'> / {of}</span><i><u style='width:{100 * got // of}%; "
                         f"background:{cc}'></u></i></div>")
        st.markdown(f"""
<div class='rc-card'>
  <div class='rc-score'>
    <div><span class='rc-big' style='color:{color}'>{r['score']}</span><span class='rc-muted'> /10</span></div>
    <div style='flex:1 1 260px; min-width:0'>
      <div class='rc-bar'>{bar}</div>
      <div style='font-weight:600'>{esc(r['level_meaning'][:1].upper() + r['level_meaning'][1:])}</div>
      <div class='rc-muted'>{nxt}</div>
    </div>
  </div>
  <div class='rc-four'>{''.join(minis)}</div>
</div>""", unsafe_allow_html=True)

        groups = []
        for c in CRITERIA:
            rows = []
            for k in CHECK_GROUPS[c]:
                ok = r["checks"][k] == 1
                dot = (f"<span class='rc-dot' style='background:{TEAL}'></span>" if ok else
                       f"<span class='rc-dot' style='border:2px solid {ORANGE}'></span>")
                miss = "" if ok else " <span class='rc-muted'>(missing)</span>"
                rows.append(f"<div class='rc-check'>{dot}<span>{CHECK_LABELS[k]}{miss}</span></div>")
            groups.append(f"<div class='rc-group'><h4>{c}</h4>{''.join(rows)}</div>")
        st.markdown(f"<div class='rc-card'><div class='rc-title'>Checklist — {r['checks_met']} of 10</div>"
                    f"<div class='rc-grid'>{''.join(groups)}</div></div>", unsafe_allow_html=True)

        if r["how_to_improve"]:
            tips = "".join(f"<div class='rc-tip'><b>{esc(c)}</b><br>{esc(t)}</div>"
                           for c, t in r["how_to_improve"].items())
            st.markdown(f"<div class='rc-card'><div class='rc-title'>How to improve</div>{tips}</div>",
                        unsafe_allow_html=True)
        else:
            st.success("Nothing important is missing. This review is very useful to a buyer.")

        st.markdown(f"<div class='rc-muted'>Why this score: {esc(r['reason'])} "
                    f"· judge: {esc(r['judge'])} · {esc(r['language'])} · {r['latency_ms']} ms</div>",
                    unsafe_allow_html=True)

        if ss.eval_id not in ss.rated:
            a, b, _ = st.columns([2, 2, 1])
            if a.button("Tips helped"):
                db.rate(con, ss.eval_id, 1); ss.rated.add(ss.eval_id); st.rerun()
            if b.button("Not helpful"):
                db.rate(con, ss.eval_id, 0); ss.rated.add(ss.eval_id); st.rerun()
        else:
            st.caption("Thanks for the feedback.")

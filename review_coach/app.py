"""Review Coach: write a product review, check it, see what to improve, check again.

    cd review_coach
    $env:GEMINI_API_KEY = "<your key>"      # optional; without it, use the mock judge
    streamlit run app.py
"""
import html, os
import streamlit as st

import db
from evaluator import evaluate, CHECK_LABELS, CHECK_GROUPS, CRITERIA

st.set_page_config(page_title="Review Coach", layout="wide")

TEAL, ORANGE, INK, MUTED, LINE = "#0F766E", "#C2410C", "#1B1D21", "#55585F", "#E2E2DC"
st.markdown(f"""
<style>
.rc-card {{ background:#FFFFFF; border:1px solid {LINE}; border-radius:14px; padding:20px 22px; margin-bottom:14px; color:{INK}; }}
.rc-score {{ display:flex; flex-wrap:wrap; gap:22px; align-items:center; }}
.rc-big {{ font-size:60px; font-weight:700; line-height:1; }}
.rc-bar {{ display:grid; grid-template-columns:repeat(10,minmax(0,1fr)); gap:4px; margin-bottom:8px; }}
.rc-bar span {{ height:8px; border-radius:4px; background:{LINE}; }}
.rc-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px 24px; }}
@media (max-width: 640px) {{ .rc-grid {{ grid-template-columns:1fr; }} }}
.rc-group h4 {{ margin:0 0 6px; font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:{MUTED}; }}
.rc-check {{ display:flex; gap:8px; align-items:center; margin:4px 0; }}
.rc-dot {{ width:16px; height:16px; border-radius:50%; flex:none; box-sizing:border-box; }}
.rc-tip {{ background:#FFF4EC; border-radius:10px; padding:12px 14px; margin:8px 0; }}
.rc-tip b {{ color:#9A3412; font-size:13px; text-transform:capitalize; }}
.rc-hist {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
.rc-pill {{ padding:6px 12px; border-radius:999px; background:#F1F1EC; font-size:14px; }}
.rc-muted {{ color:{MUTED}; font-size:13px; }}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    return db.connect()


con = get_db()
ss = st.session_state
ss.setdefault("sid", None)
ss.setdefault("result", None)
ss.setdefault("eval_id", None)
ss.setdefault("rated", set())
esc = html.escape

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    judge = st.radio("Judge", ["gemini", "mock"], index=0 if has_key else 1,
                     format_func=lambda j: {"gemini": "Gemini (real score)",
                                            "mock": "Mock (no API, for testing)"}[j])
    if judge == "gemini" and not has_key:
        st.warning("GEMINI_API_KEY is not set in the terminal that started the app.")
    if st.button("Start a new review"):
        ss.sid, ss.result, ss.eval_id = None, None, None
        st.rerun()
    st.caption("Your review text is sent to Google's Gemini model to be checked when the Gemini judge is "
               "on. Nothing is posted anywhere. No names or emails are stored.")

st.markdown(f"<h1 style='margin-bottom:0'>Review Coach</h1>"
            f"<p class='rc-muted'>Write in Bangla, Banglish or English. Check your review, follow the tips, "
            f"and check again.</p>", unsafe_allow_html=True)

left, right = st.columns([5, 6], gap="large")

# ---------------------------------------------------------------- input
with left:
    st.subheader("Write your review")
    product = st.text_input("Product", placeholder="e.g. Foaming Facial Cleanser 236 ml")
    category = st.radio("Type", ["book", "skincare", "product"], index=2, horizontal=True,
                        format_func=lambda c: {"book": "Book", "skincare": "Skincare",
                                               "product": "Other product"}[c])
    review = st.text_area("Your review", height=220,
                          placeholder="What did you buy, how long have you used it, what was good or bad?")
    st.caption(f"{len(review.split())} words")
    go = st.button("Check my review", type="primary")

    if go:
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

# ---------------------------------------------------------------- results
with right:
    r = ss.result
    if r is None:
        st.markdown(f"<div class='rc-card rc-muted'>Your score, a checklist of what a useful review contains, "
                    f"and tips for this review will appear here.</div>", unsafe_allow_html=True)
    else:
        color = TEAL if r["score"] >= 7 else ORANGE
        bar = "".join(f"<span style='background:{color if i < r['score'] else LINE}'></span>" for i in range(10))
        nxt = f"Next level ({esc(r['next_level'])})" if r["next_level"] else "Top level reached."
        st.markdown(f"""
<div class='rc-card rc-score'>
  <div><span class='rc-big' style='color:{color}'>{r['score']}</span><span class='rc-muted'> /10</span></div>
  <div style='flex:1 1 260px; min-width:0'>
    <div class='rc-bar'>{bar}</div>
    <div style='font-weight:600'>{esc(r['level_meaning'].capitalize())}</div>
    <div class='rc-muted'>{nxt}</div>
  </div>
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
        st.markdown(f"<div class='rc-card'><div style='font-weight:600; margin-bottom:10px'>"
                    f"Checklist — {r['checks_met']} of 10</div><div class='rc-grid'>{''.join(groups)}</div></div>",
                    unsafe_allow_html=True)

        if r["how_to_improve"]:
            tips = "".join(f"<div class='rc-tip'><b>{esc(c)}</b><br>{esc(t)}</div>"
                           for c, t in r["how_to_improve"].items())
            st.markdown(f"<div class='rc-card'><div style='font-weight:600'>How to improve</div>{tips}</div>",
                        unsafe_allow_html=True)
        else:
            st.success("Nothing important is missing. This review is very useful to a buyer.")

        st.markdown(f"<div class='rc-muted'>Why this score: {esc(r['reason'])} "
                    f"· judge: {esc(r['judge'])} · {r['language']} · {r['latency_ms']} ms</div>",
                    unsafe_allow_html=True)

        if ss.eval_id not in ss.rated:
            a, b, _ = st.columns([2, 2, 1])
            if a.button("Tips helped"):
                db.rate(con, ss.eval_id, 1); ss.rated.add(ss.eval_id); st.rerun()
            if b.button("Not helpful"):
                db.rate(con, ss.eval_id, 0); ss.rated.add(ss.eval_id); st.rerun()
        else:
            st.caption("Thanks for the feedback.")

        hist = db.history(con, ss.sid)
        if len(hist) > 1:
            pills = " <span class='rc-muted'>→</span> ".join(
                f"<span class='rc-pill'>Draft {h['draft_no']}: <b>{h['score']}</b></span>" for h in hist)
            change = hist[-1]["score"] - hist[0]["score"]
            st.markdown(f"<div class='rc-card'><div style='font-weight:600; margin-bottom:8px'>Your drafts "
                        f"({'+' if change >= 0 else ''}{change} since the first)</div>"
                        f"<div class='rc-hist'>{pills}</div></div>", unsafe_allow_html=True)

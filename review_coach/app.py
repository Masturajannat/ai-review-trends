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

# colours: navy for what is present, coral for what is missing; a light and a dark version
THEMES = {
    "light": dict(ok="#1E3A8A", miss="#E11D48", miss_text="#BE123C", tip="#FFF0F3", bg="#F3F6FB", card="#FFFFFF",
                  ink="#0F172A", muted="#52607A", line="#DCE3EE", pill="#E9EEF7", on_ok="#FFFFFF"),
    "dark": dict(ok="#8FB0FF", miss="#FB7185", miss_text="#FDA4AF", tip="#2C1A24", bg="#0D1220", card="#161D2E",
                 ink="#EEF2F8", muted="#A3AEC4", line="#2B354B", pill="#222C42", on_ok="#0B1220"),
}

ss = st.session_state
for k, v in dict(sid=None, result=None, eval_id=None, rated=set(), dark=False).items():
    ss.setdefault(k, v)
T = THEMES["dark" if ss.dark else "light"]

CSS = f"""
<style>
.rc-card {{ background:{T['card']}; border:1px solid {T['line']}; border-radius:14px; padding:20px 22px; margin-bottom:14px; color:{T['ink']}; }}
.rc-score {{ display:flex; flex-wrap:wrap; gap:22px; align-items:center; }}
.rc-big {{ font-size:60px; font-weight:700; line-height:1; }}
.rc-bar {{ display:grid; grid-template-columns:repeat(10,minmax(0,1fr)); gap:4px; margin-bottom:8px; }}
.rc-bar span {{ height:8px; border-radius:4px; background:{T['line']}; }}
.rc-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px 24px; }}
@media (max-width: 640px) {{ .rc-grid {{ grid-template-columns:1fr; }} }}
.rc-group h4 {{ margin:0 0 6px; font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:{T['muted']}; }}
.rc-check {{ display:flex; gap:8px; align-items:center; margin:4px 0; }}
.rc-dot {{ width:16px; height:16px; border-radius:50%; flex:none; box-sizing:border-box; }}
.rc-tip {{ background:{T['tip']}; border-radius:10px; padding:12px 14px; margin:8px 0; }}
.rc-tip b {{ color:{T['miss_text']}; font-size:13px; text-transform:capitalize; }}
.rc-hist {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
.rc-pill {{ padding:6px 12px; border-radius:999px; background:{T['pill']}; font-size:14px; }}
.rc-muted {{ color:{T['muted']}; font-size:13px; }}
</style>"""
DARK_CSS = f"""
<style>
.stApp, [data-testid="stAppViewContainer"] {{ background:{T['bg']}; color:{T['ink']}; }}
[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {{ background:{T['card']}; }}
.stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp label, .stApp span, .stApp li,
[data-testid="stWidgetLabel"] *, [data-testid="stMarkdownContainer"] {{ color:{T['ink']}; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{ color:{T['muted']}; }}
.stApp input, .stApp textarea {{ background:{T['card']}; color:{T['ink']}; caret-color:{T['ink']}; }}
.stApp input::placeholder, .stApp textarea::placeholder {{ color:{T['muted']}; opacity:1; }}
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"] {{
  background:{T['card']} !important; border-color:{T['line']} !important; }}
.stButton > button {{ background:{T['card']}; color:{T['ink']}; border:1px solid {T['line']}; }}
.stButton > button:hover {{ border-color:{T['ok']}; color:{T['ok']}; }}
.stButton > button[kind="primary"], .stButton > button[kind="primary"] * {{
  background:{T['ok']}; color:{T['on_ok']}; border-color:{T['ok']}; }}
.stApp .rc-muted, .stApp .rc-muted * {{ color:{T['muted']}; }}
.stApp .rc-tip b {{ color:{T['miss_text']}; }}
[data-testid="stAlert"] {{ background:{T['pill']}; }}
</style>"""
# blank lines would end the HTML block and show the CSS as text
st.markdown("\n".join(line for line in (CSS + (DARK_CSS if ss.dark else "")).splitlines() if line.strip()),
            unsafe_allow_html=True)


@st.cache_resource
def get_db():
    return db.connect()


con = get_db()
esc = html.escape


def new_review():
    ss.sid = ss.result = ss.eval_id = None


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    st.toggle("Dark theme", key="dark")
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
        st.markdown("<div class='rc-card rc-muted'>Your score, a checklist of what a useful review contains, "
                    "and tips for this review will appear here.</div>", unsafe_allow_html=True)
    else:
        color = T["ok"] if r["score"] >= 7 else T["miss"]
        bar = "".join(f"<span style='background:{color if i < r['score'] else T['line']}'></span>"
                      for i in range(10))
        nxt = f"Next level ({esc(r['next_level'])})" if r["next_level"] else "Top level reached."
        st.markdown(f"""
<div class='rc-card rc-score'>
  <div><span class='rc-big' style='color:{color}'>{r['score']}</span><span class='rc-muted'> /10</span></div>
  <div style='flex:1 1 260px; min-width:0'>
    <div class='rc-bar'>{bar}</div>
    <div style='font-weight:600'>{esc(r['level_meaning'][:1].upper() + r['level_meaning'][1:])}</div>
    <div class='rc-muted'>{nxt}</div>
  </div>
</div>""", unsafe_allow_html=True)

        groups = []
        for c in CRITERIA:
            rows = []
            for k in CHECK_GROUPS[c]:
                ok = r["checks"][k] == 1
                dot = (f"<span class='rc-dot' style='background:{T['ok']}'></span>" if ok else
                       f"<span class='rc-dot' style='border:2px solid {T['miss']}'></span>")
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

        hist = db.history(con, ss.sid)
        if len(hist) > 1:
            pills = " <span class='rc-muted'>→</span> ".join(
                f"<span class='rc-pill'>Draft {h['draft_no']}: <b>{h['score']}</b></span>" for h in hist)
            change = hist[-1]["score"] - hist[0]["score"]
            st.markdown(f"<div class='rc-card'><div style='font-weight:600; margin-bottom:8px'>Your drafts "
                        f"({'+' if change >= 0 else ''}{change} since the first)</div>"
                        f"<div class='rc-hist'>{pills}</div></div>", unsafe_allow_html=True)

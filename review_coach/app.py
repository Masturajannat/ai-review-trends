"""Review Coach: write a product review, get it rated, and ask for suggestions if you want them.

    cd review_coach
    $env:GEMINI_API_KEY = "<your key>"      # optional; without it, use the mock judge
    python -m streamlit run app.py --server.headless true
"""
import html, io, os, tempfile, zipfile
import streamlit as st

import db
from evaluator import evaluate, suggest, model_available, load_model, SUGGEST_VERSION

st.set_page_config(page_title="Review Coach", layout="wide")

# colours: navy and coral; a light and a dark version
THEMES = {
    "light": dict(ok="#1E3A8A", miss="#E11D48", miss_text="#BE123C", tip="#FFF0F3", bg="#F3F6FB", card="#FFFFFF",
                  ink="#0F172A", muted="#52607A", line="#DCE3EE", pill="#E9EEF7", on_ok="#FFFFFF",
                  mark="#FFE1E7", soft="#F3F6FB"),
    "dark": dict(ok="#8FB0FF", miss="#FB7185", miss_text="#FDA4AF", tip="#2C1A24", bg="#0D1220", card="#161D2E",
                 ink="#EEF2F8", muted="#A3AEC4", line="#2B354B", pill="#222C42", on_ok="#0B1220",
                 mark="#5A2233", soft="#1D2538"),
}

ss = st.session_state
for k, v in dict(sid=None, result=None, sug=None, sug_id=None, sug_draft=None, attempt=1, sug_text="", product_text="",
                 sug_seen=[], rated=set(),
                 dark=False).items():
    ss.setdefault(k, v)
T = THEMES["dark" if ss.dark else "light"]

CSS = f"""
<style>
.rc-card {{ background:{T['card']}; border:1px solid {T['line']}; border-radius:14px; padding:20px 22px; margin-bottom:14px; color:{T['ink']}; }}
.rc-title {{ font-weight:600; margin-bottom:10px; }}
.rc-score {{ text-align:center; }}
.rc-ring {{ width:150px; height:150px; border-radius:50%; margin:6px auto 10px; display:flex; align-items:center; justify-content:center; }}
.rc-ring > div {{ width:116px; height:116px; border-radius:50%; background:{T['card']}; display:flex; align-items:center;
                 justify-content:center; font-size:42px; font-weight:800; }}
.rc-muted {{ color:{T['muted']}; font-size:13px; }}
.rc-dot {{ width:14px; height:14px; border-radius:50%; flex:none; box-sizing:border-box; margin-top:5px; }}
.rc-why {{ display:flex; gap:10px; align-items:flex-start; margin:8px 0; line-height:1.5; }}
.rc-draft {{ background:{T['soft']}; border-radius:10px; padding:12px 14px; line-height:1.7; white-space:pre-wrap; margin-bottom:6px; }}
.rc-draft mark {{ background:{T['mark']}; color:{T['ink']}; border-bottom:2px solid {T['miss']}; border-radius:3px; padding:1px 2px; }}
.rc-draft sup {{ color:{T['miss_text']}; font-weight:700; margin-left:1px; }}
.rc-sug {{ display:flex; gap:12px; background:{T['tip']}; border-radius:10px; padding:12px 14px; margin:10px 0 0; }}
.rc-num {{ flex:none; width:24px; height:24px; border-radius:50%; background:{T['miss']}; color:{T['on_ok']};
           display:flex; align-items:center; justify-content:center; font-weight:700; font-size:13px; }}
.rc-sug q {{ color:{T['miss_text']}; font-size:13px; font-weight:600; }}
.rc-sug p {{ margin:2px 0 0 !important; line-height:1.5; }}
.rc-eg {{ display:inline-block; margin-top:8px; padding:4px 10px; border-radius:8px; background:{T['card']};
          border:1px dashed {T['line']}; font-size:14px; }}
.rc-hist {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
.rc-pill {{ padding:6px 12px; border-radius:999px; background:{T['pill']}; font-size:14px; }}
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
.stApp .rc-sug q, .stApp .rc-draft sup {{ color:{T['miss_text']}; }}
.stApp .rc-num {{ color:{T['on_ok']}; }}
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
    ss.sid = ss.result = ss.sug = ss.sug_id = ss.sug_draft = None
    ss.attempt = 1
    ss.sug_seen = []
    ss.sug_text = ""


def session(product):
    if ss.sid is None:
        ss.sid = db.new_session(con, product)
    else:
        db.update_session(con, ss.sid, product)
    return ss.sid


def export_zip():
    with tempfile.TemporaryDirectory() as d:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in db.export_csv(con, d):
                z.write(p, os.path.basename(p))
    return buf.getvalue()


def highlight(text, quotes):
    """The draft with each quoted phrase marked and numbered, safely escaped."""
    spans = []
    for n, q in enumerate(quotes, 1):
        i = text.find(q) if q else -1
        if i >= 0 and all(i >= e or i + len(q) <= s for s, e, _ in spans):
            spans.append((i, i + len(q), n))
    out, pos = [], 0
    for s, e, n in sorted(spans):
        out.append(esc(text[pos:s]) + f"<mark>{esc(text[s:e])}</mark><sup>{n}</sup>")
        pos = e
    return "".join(out) + esc(text[pos:])


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    st.toggle("Dark theme", key="dark")
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    has_model = model_available()
    scorers = ["model", "gemini", "mock"]
    judge = st.radio("Score from", scorers, index=0 if has_model else (1 if has_key else 2),
                     format_func=lambda j: {"model": "Our trained model (on this computer)",
                                            "gemini": "Gemini (API)", "mock": "Mock (for testing)"}[j])
    if judge == "model" and not has_model:
        st.warning("The trained model is not in quality_model/models_noreadmore/xlm-roberta-large. "
                   "Download it from Google Drive into that folder.")
    if judge == "gemini" and not has_key:
        st.warning("GEMINI_API_KEY is not set in the terminal that started the app.")
    helper = st.radio("Suggestions from", ["gemini", "mock"], index=0 if has_key else 1,
                      format_func=lambda j: {"gemini": "Gemini (API)", "mock": "Mock (for testing)"}[j])
    st.button("Start a new review", on_click=new_review)
    st.download_button("Download the database (CSV)", data=export_zip(), file_name="review_coach_data.zip",
                       mime="application/zip", help="Every table as a CSV file, for the report")
    st.caption("With our trained model, rating stays on this computer. Suggestions (and the Gemini score) "
               "send the review text to Google's Gemini model. Nothing is posted anywhere. No names or emails "
               "are stored.")

st.markdown("<h1 style='margin-bottom:0'>Review Coach</h1>"
            "<p class='rc-muted'>Write your review your own way, in Bangla, Banglish or English. "
            "Rate it, and ask for suggestions to make it better if you want them.</p>",
            unsafe_allow_html=True)

left, right = st.columns([5, 6], gap="large")

# ---------------------------------------------------------------- input
with left:
    st.subheader("Write your review")
    product = st.text_input("Product (optional)", placeholder="e.g. Foaming Facial Cleanser 236 ml")
    review = st.text_area("Your review", height=240, placeholder="Share your experience with what you bought.")
    st.caption(f"{len(review.split())} words")
    c1, c2 = st.columns(2)
    go = c1.button("Rate my review", type="primary", use_container_width=True)
    ask = c2.button("Suggest improvements", use_container_width=True)

    if (go or ask) and not review.strip():
        st.error("Write a review first.")
    elif go:
        did, _ = db.draft(con, session(product), product, review)
        hit = db.cached_score(con, product, review, judge)
        try:
            if judge == "model" and model_available():
                with st.spinner("Loading the trained model (first time only, up to a minute)..."):
                    load_model()
            with st.spinner("Rating your review..."):
                r = hit or evaluate(product, review, judge=judge, explain=False)
            db.save_score(con, did, r, from_cache=hit is not None)
            ss.result = r
            if ss.sug_text != review:          # suggestions for an older draft: hide them
                ss.sug = ss.sug_id = None
        except Exception as e:
            st.error(str(e))
    elif ask:
        did, _ = db.draft(con, session(product), product, review)
        hit = db.cached_suggestions(con, product, review, helper, SUGGEST_VERSION if helper == "gemini" else "mock")
        try:
            with st.spinner("Looking for ways to improve your review..."):
                s = hit or suggest(product, review, judge=helper)
            ss.sug_id = db.save_suggestions(con, did, s, attempt=1, from_cache=hit is not None)
            ss.sug, ss.sug_text, ss.product_text, ss.sug_draft, ss.attempt = s, review, product, did, 1
            ss.sug_seen = [i["suggestion"] for i in s["suggestions"]]
        except Exception as e:
            st.error(str(e))

# ---------------------------------------------------------------- results
with right:
    r, s = ss.result, ss.sug
    if r is None and s is None:
        st.markdown("<div class='rc-card'><div class='rc-title'>How it works</div>"
                    "<p><b>Rate my review</b> gives your review a score from 1 to 10 for how informative and "
                    "helpful it is, from our own trained model.</p>"
                    "<p style='margin-bottom:0'><b>Suggest improvements</b> reads your review and points at "
                    "places that could say a little more. It never changes your opinion and "
                    "never writes the review for you.</p></div>", unsafe_allow_html=True)

    if r is not None:
        color = T["ok"] if r["score"] >= 7 else T["miss"]
        pct = max(0.0, min(1.0, r["score"] / 10)) * 100
        hist = db.history(con, ss.sid) if ss.sid else []
        change = round(hist[-1]["score"] - hist[0]["score"], 1) if len(hist) > 1 else None
        note = ("out of 10" if change is None else
                "out of 10 · same as your first draft" if change == 0 else
                f"out of 10 · {'up' if change > 0 else 'down'} {abs(change):g} from your first draft")
        hint = ("" if s is not None or r["explanation"] else
                "<div class='rc-muted' style='margin-top:8px'>Want to know what would raise it? Press "
                "<b>Suggest improvements</b>.</div>")
        st.markdown(f"""
<div class='rc-card rc-score'>
  <div class='rc-title' style='text-align:left'>Your score</div>
  <div class='rc-ring' style='background:conic-gradient({color} 0 {pct:.1f}%, {T['line']} {pct:.1f}% 100%)'>
    <div style='color:{color}'>{r['score']:g}</div></div>
  <div class='rc-muted'>{note}</div>
  {hint}
</div>""", unsafe_allow_html=True)
        if r["explanation"]:                       # only the Gemini judge writes one
            st.markdown(f"<div class='rc-card'><div class='rc-title'>Why this score</div>"
                        f"<p style='margin:0; line-height:1.6'>{esc(r['explanation'])}</p></div>",
                        unsafe_allow_html=True)

    if s is not None:
        items = s["suggestions"]
        body = f"<div class='rc-title'>Suggestions for your review</div>"
        if s["summary"]:
            body += f"<p>{esc(s['summary'])}</p>"
        if items:
            body += f"<div class='rc-draft'>{highlight(ss.sug_text, [i['quote'] for i in items])}</div>"
            for n, i in enumerate(items, 1):
                quote = f"<q>{esc(i['quote'])}</q>" if i["quote"] else ""
                eg = f"<span class='rc-eg'>{esc(i['example'])}</span>" if i["example"] else ""
                body += (f"<div class='rc-sug'><div class='rc-num'>{n}</div><div>{quote}"
                         f"<p>{esc(i['suggestion'])}</p>{eg}</div></div>")
            body += ("<p class='rc-muted' style='margin:12px 0 0'>These are only ideas. Use the ones that fit "
                     "your experience, then rate your review again.</p>")
        else:
            body += "<p class='rc-muted'>Nothing to add. Your review is already detailed and clear.</p>"
        st.markdown(f"<div class='rc-card'>{body}</div>", unsafe_allow_html=True)

        if ss.sug_id not in ss.rated:
            a, b = st.columns(2)
            if a.button("Suggestions helped", use_container_width=True):
                db.feedback(con, ss.sug_id, 1); ss.rated.add(ss.sug_id); st.rerun()
            if b.button("Not helpful: show different ones", use_container_width=True):
                db.feedback(con, ss.sug_id, 0); ss.rated.add(ss.sug_id)
                # ask again, telling Gemini which suggestions were not helpful so the new ones differ
                try:
                    with st.spinner("Finding different suggestions..."):
                        new = suggest(ss.product_text, ss.sug_text, judge=helper, avoid=ss.sug_seen)
                    ss.attempt += 1
                    ss.sug_id = db.save_suggestions(con, ss.sug_draft, new, attempt=ss.attempt)
                    ss.sug = new
                    ss.sug_seen = ss.sug_seen + [i["suggestion"] for i in new["suggestions"]]
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        else:
            st.caption("Thanks for the feedback.")

    hist = db.history(con, ss.sid) if ss.sid else []
    if len(hist) > 1:
        pills = " <span class='rc-muted'>→</span> ".join(
            f"<span class='rc-pill'>Draft {h['draft_no']}: <b>{h['score']:g}</b></span>" for h in hist)
        change = round(hist[-1]["score"] - hist[0]["score"], 1)
        st.markdown(f"<div class='rc-card'><div class='rc-title'>Your drafts "
                    f"({'+' if change >= 0 else ''}{change:g} since the first)</div>"
                    f"<div class='rc-hist'>{pills}</div></div>", unsafe_allow_html=True)

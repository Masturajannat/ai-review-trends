"""Review Coach: write a product review, get it rated, and ask for suggestions if you want them.

    cd review_coach
    $env:GEMINI_API_KEY = "<your key>"      # optional; without it, use the mock judge
    python -m streamlit run app.py --server.headless true
"""
import html, io, os, sys, tempfile, zipfile
import streamlit as st

import db
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shop"))
import shop_db       # the dummy shop's products and reviews
from evaluator import evaluate, suggest, model_available, load_model, SUGGEST_VERSION

st.set_page_config(page_title="Review Coach", page_icon="📝", layout="wide", initial_sidebar_state="collapsed")

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
                 sug_seen=[], rated=set(), my_sessions=[], product="", review="",
                 dark=False, result_text="", submitted=False).items():
    ss.setdefault(k, v)
T = THEMES["dark" if ss.dark else "light"]

CSS = f"""
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
[data-testid="stToolbar"], [data-testid="stDecoration"] {{ display:none !important; }}
[data-testid="stHeader"] {{ background:transparent; height:0; pointer-events:none; }}
.block-container {{ padding-top:1.2rem !important; padding-bottom:0.5rem !important; }}
[data-testid="stVerticalBlock"] {{ gap:0.6rem; }}
.st-key-topbar {{ background:{T['card']}; border:1px solid {T['line']}; border-radius:14px; padding:10px 16px; margin-bottom:10px; }}
.st-key-topbar [data-testid="stHorizontalBlock"] {{ align-items:center; }}
[data-testid="stPopoverBody"] {{ min-width:360px; }}
.rc-logo {{ position:relative; top:-7px; display:flex; align-items:center; gap:10px; font-weight:800; font-size:21px; color:{T['ink']}; }}
.rc-logo i {{ width:34px; height:34px; border-radius:9px; background:{T['ok']}; color:{T['on_ok']}; font-style:normal;
              display:inline-flex; align-items:center; justify-content:center; font-size:17px; }}
.stApp .st-key-new_review button {{ background:{T['miss']} !important; border-color:{T['miss']} !important; }}
.stApp .st-key-new_review button, .stApp .st-key-new_review button * {{ color:#FFFFFF !important; }}
.st-key-gearbox [data-testid="stIconMaterial"], .st-key-gearbox button svg {{ display:none !important; }}
.st-key-gearbox button p {{ font-size:18px; }}
.st-key-topbar [data-testid="stMarkdownContainer"] > div {{ margin:0; }}
.st-key-topbar .stMarkdown, .st-key-topbar [data-testid="stElementContainer"] {{ margin-bottom:0 !important; }}
.st-key-inputcard {{ background:{T['card']}; border:1px solid {T['line']}; border-radius:14px; padding:20px 22px; }}
.rc-rev {{ display:flex; justify-content:space-between; gap:10px; }}
.rc-chip {{ font-size:12px; font-weight:700; padding:2px 8px; border-radius:20px; background:{T['pill']}; color:{T['ok']}; }}
.rc-card {{ background:{T['card']}; border:1px solid {T['line']}; border-radius:14px; padding:14px 18px; margin-bottom:10px; color:{T['ink']}; }}
.rc-title {{ font-weight:600; margin-bottom:10px; }}
.rc-scorehead {{ display:flex; align-items:center; gap:14px; }}
.rc-big {{ font-size:28px; font-weight:800; line-height:1; }}
.rc-bar {{ flex:1; height:14px; border-radius:999px; background:{T['line']}; overflow:hidden; }}
.rc-bar > div {{ height:100%; border-radius:999px; }}
.rc-muted {{ color:{T['muted']}; font-size:13px; }}
.rc-dot {{ width:14px; height:14px; border-radius:50%; flex:none; box-sizing:border-box; margin-top:5px; }}
.rc-why {{ display:flex; gap:10px; align-items:flex-start; margin:8px 0; line-height:1.5; }}
.rc-draft {{ background:{T['soft']}; border-radius:10px; padding:8px 12px; line-height:1.7; white-space:pre-wrap; margin-bottom:6px; }}
.rc-draft mark {{ background:{T['mark']}; color:{T['ink']}; border-bottom:2px solid {T['miss']}; border-radius:3px; padding:1px 2px; }}
.rc-draft sup {{ color:{T['miss_text']}; font-weight:700; margin-left:1px; }}
.rc-sug {{ display:flex; gap:12px; background:{T['tip']}; border-radius:10px; padding:8px 12px; margin:6px 0 0; }}
.rc-num {{ flex:none; width:24px; height:24px; border-radius:50%; background:{T['miss']}; color:{T['on_ok']};
           display:flex; align-items:center; justify-content:center; font-weight:700; font-size:13px; }}
.rc-sug q {{ color:{T['miss_text']}; font-size:13px; font-weight:600; }}
.rc-sug p {{ margin:2px 0 0 !important; line-height:1.5; }}
.rc-eg {{ display:inline-block; margin-top:4px; padding:4px 10px; border-radius:8px; background:{T['card']};
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
.stButton > button, [data-testid="stPopover"] button, .stDownloadButton > button {{
  background:{T['card']} !important; color:{T['ink']} !important; border:1px solid {T['line']} !important; }}
[data-testid="stPopover"] button *, .stDownloadButton > button * {{ color:{T['ink']} !important; }}
[data-testid="stPopoverBody"] {{ background:{T['card']} !important; border:1px solid {T['line']}; }}
.stButton > button:hover {{ border-color:{T['ok']}; color:{T['ok']}; }}
.stButton > button[kind="primary"] {{ background:{T['ok']} !important; color:{T['on_ok']} !important;
  border-color:{T['ok']} !important; }}
.stButton > button[kind="primary"] * {{ background:transparent !important; color:{T['on_ok']} !important; }}
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

# the product comes from the shop link (?product=<id>); without it there is nothing to review
SHOP_URL = os.environ.get("SHOP_URL", "http://localhost:8502")
try:
    prod, shop_error = shop_db.product(st.query_params.get("product", "")), ""
except Exception as e:                       # for example shop.db was not made yet
    prod, shop_error = None, str(e)
if prod is None:
    st.markdown("<div class='rc-card' style='max-width:520px;margin:12vh auto 10px'>"
                "<div class='rc-title' style='font-size:18px'>Pick a product in the shop first</div>"
                "<p style='margin:0'>Review Coach opens from a product page: choose a product, then press "
                "<b>Write a review</b>.</p></div>", unsafe_allow_html=True)
    if shop_error:
        st.error(shop_error)
    st.link_button("Go to the shop", SHOP_URL)
    st.stop()
ss.product = prod["name"]                    # fixed: the text box below only shows it


def new_review():
    ss.sid = ss.result = ss.sug = ss.sug_id = ss.sug_draft = None
    ss.attempt = 1
    ss.product = ss.review = ""
    ss.sug_seen = []
    ss.sug_text = ""
    ss.result_text, ss.submitted = "", False


def session(product):
    if ss.sid is None:
        ss.sid = db.new_session(con, product)
        ss.my_sessions = [ss.sid] + ss.my_sessions
        ss.fresh = True                         # redraw so "My reviews" counts the new one
    else:
        db.update_session(con, ss.sid, product)
    return ss.sid


def open_review(sid):
    """Show an earlier review again: its last draft, and its score if this judge rated it."""
    last = db.last_drafts(con, [sid])
    new_review()
    ss.sid = sid
    if last:
        ss.product, ss.review = last[0]["product_name"] or "", last[0]["review_text"]
        ss.result = db.cached_score(con, ss.product, ss.review, ss.get("judge", "model"))
        ss.result_text = ss.review.strip() if ss.result else ""


def toggle_dark():
    ss.dark = not ss.dark


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


# ---------------------------------------------------------------- top bar
has_key = bool(os.environ.get("GEMINI_API_KEY"))
has_model = model_available()
with st.container(key="topbar"):
    logo, gap, mine, new, dark, gear = st.columns([4, 3, 1.5, 1.4, 0.5, 0.5], gap="small",
                                                  vertical_alignment="center")
    logo.markdown("<div class='rc-logo'><i>R</i>Review Coach</div>", unsafe_allow_html=True)
    submit_slot = gap.empty()                # the Submit button appears here once the review has a score
    rows = [r_ for r_ in db.last_drafts(con, ss.my_sessions) if (r_["product_name"] or "") == prod["name"]]
    with mine.popover(f"My reviews ({len(rows)})", use_container_width=True):
        if not rows:
            st.caption("Reviews you rate or improve here appear in this list.")
        for r_ in rows:
            name = r_["product_name"] or " ".join(r_["review_text"].split()[:5]) + "..."
            score = f"<span class='rc-chip'>{r_['score']:g}</span>" if r_["score"] is not None else ""
            c_a, c_b = st.columns([3, 1.2], vertical_alignment="center")
            c_a.markdown(f"<div class='rc-rev'><span>{esc(name)}</span>{score}</div>", unsafe_allow_html=True)
            c_b.button("Open", key=f"open_{r_['session_id']}", on_click=open_review, args=(r_["session_id"],))
    new.button("+ New review", key="new_review", on_click=new_review, use_container_width=True)
    dark.button("☀" if ss.dark else "☾", key="dark_btn", on_click=toggle_dark,
                use_container_width=True)
    with gear.container(key="gearbox"), st.popover("⚙", use_container_width=True):
        st.markdown("**Settings** · for the project team")
        judge = st.radio("Score from", ["model", "gemini", "mock"], key="judge",
                         index=0 if has_model else (1 if has_key else 2),
                         format_func=lambda j: {"model": "Our trained model (on this computer)",
                                                "gemini": "Gemini (API)", "mock": "Mock (for testing)"}[j])
        if judge == "model" and not has_model:
            st.warning("The trained model is not in quality_model/models_noreadmore/xlm-roberta-large.")
        if judge == "gemini" and not has_key:
            st.warning("GEMINI_API_KEY is not set in the terminal that started the app.")
        helper = st.radio("Suggestions from", ["gemini", "mock"], key="helper", index=0 if has_key else 1,
                          format_func=lambda j: {"gemini": "Gemini (API)", "mock": "Mock (for testing)"}[j])
        if helper == "gemini" and not has_key:
            st.warning("GEMINI_API_KEY is not set, so suggestions will fail. Choose Mock to test.")
        st.download_button("Download data (CSV)", data=export_zip(), file_name="review_coach_data.zip",
                           mime="application/zip", use_container_width=True)

if ss.submitted:
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown(f"<div class='rc-card' style='margin-top:12vh'>"
                    f"<div class='rc-title' style='font-size:18px'>Your review was added</div>"
                    f"<p style='margin:0'>It is now on the product page of <b>{esc(prod['name'])}</b>.</p></div>",
                    unsafe_allow_html=True)
        back, again = st.columns(2)
        back.link_button("Back to the product", f"{SHOP_URL}/?p={prod['product_id']}", use_container_width=True)
        again.button("Write another review", on_click=new_review, use_container_width=True)
    st.stop()

left, right = st.columns([5, 6], gap="large")

# ---------------------------------------------------------------- input
with left, st.container(key="inputcard"):
    st.markdown("<div class='rc-title' style='font-size:18px;margin-bottom:2px'>Write your review</div>"
                "<div class='rc-muted'>Your own way, in Bangla, Banglish or English.</div>", unsafe_allow_html=True)
    product = st.text_input("Product", key="product", disabled=True)
    review = st.text_area("Your review", key="review", height=260,
                          placeholder="Share your experience with what you bought.")
    st.caption(f"{len(review.split())} words")
    c1, c2 = st.columns(2)
    ask = c1.button("Suggest improvements", use_container_width=True)
    go = c2.button("Rate my review", type="primary", use_container_width=True)

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
            ss.result, ss.result_text = r, review.strip()
            if ss.sug_text != review:          # suggestions for an older draft: hide them
                ss.sug = ss.sug_id = None
        except Exception as e:
            st.error(str(e))
    elif ask:
        did, _ = db.draft(con, session(product), product, review)
        hit = db.cached_suggestions(con, product, review, helper, SUGGEST_VERSION if helper == "gemini" else "mock")
        try:
            with st.spinner("Looking for ways to improve your review..."):
                s = hit or suggest(product, review, judge=helper, product_type=prod["type"])
            ss.sug_id = db.save_suggestions(con, did, s, attempt=1, from_cache=hit is not None)
            ss.sug, ss.sug_text, ss.product_text, ss.sug_draft, ss.attempt = s, review, product, did, 1
            ss.sug_seen = [i["suggestion"] for i in s["suggestions"]]
        except Exception as e:
            st.error(str(e))

if ss.pop("fresh", False):
    st.rerun()

# Submit shows only for a review that has been rated, and only while the text is the one that was rated
if ss.result is not None and ss.result_text == (ss.review or "").strip():
    if submit_slot.button("Submit review", key="submit_btn", type="primary", use_container_width=True):
        try:
            shop_db.add_review(prod["product_id"], ss.result_text, ss.result["score"], ss.result.get("language"))
            ss.submitted = True
            st.rerun()
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
<div class='rc-card'>
  <div class='rc-scorehead'><span class='rc-title' style='margin:0'>Your score</span>
    <div class='rc-bar'><div style='width:{pct:.1f}%; background:{color}'></div></div>
    <span class='rc-big' style='color:{color}'>{r['score']:g}</span></div>
  <div class='rc-muted' style='margin-top:6px'>{note}</div>
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
                eg = f"<span class='rc-eg'>e.g. {esc(i['example'])}</span>" if i["example"] else ""
                body += (f"<div class='rc-sug'><div class='rc-num'>{n}</div><div>{quote}"
                         f"<p>{esc(i['suggestion'])}</p>{eg}</div></div>")
            body += ("<p class='rc-muted' style='margin:8px 0 0'>These are only ideas. Use the ones that fit "
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
                        new = suggest(ss.product_text, ss.sug_text, judge=helper, avoid=ss.sug_seen, product_type=prod["type"])
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

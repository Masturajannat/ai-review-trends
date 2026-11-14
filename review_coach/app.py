"""Review Coach: write a product review, check it, see what to improve, check again.

    cd review_coach
    $env:GEMINI_API_KEY = "<your key>"      # optional; without it, use the mock judge
    python -m streamlit run app.py --server.headless true
"""
import html, os
import streamlit as st

import db
from evaluator import evaluate, CHECK_LABELS, CHECK_GROUPS, CRITERIA

st.set_page_config(page_title="Review Coach", layout="wide", initial_sidebar_state="collapsed")

TEAL, TEAL_D, TEAL_L = "#0F766E", "#115E59", "#E6F2F0"
ORANGE, ORANGE_D, ORANGE_L = "#C2410C", "#9A3412", "#FFF1E7"
AMBER, AMBER_L = "#A16207", "#FEF6DC"
INK, MUTED, LINE, BG = "#1B1D21", "#5A5D64", "#E4E4DE", "#F6F6F3"

CRITERION_TEXT = {
    "specific": "Concrete details, not just “good” or “nice”",
    "personal": "Shows real use: how long, in what situation, what happened",
    "reasoned": "Gives a reason, a good and a bad point, or a comparison",
    "relevant": "Useful to someone deciding whether to buy this",
}
EXAMPLES = {
    "Banglish": ("Foaming Facial Cleanser 236 ml", "skincare",
                            "Product ta valo, delivery fast chilo. Original mone hocche. Recommended."),
    "বাংলা": ("দেয়াল (হার্ডকভার)", "book", "বইটা ভালো লেগেছে। সবাই পড়তে পারেন।"),
    "English": ("Wireless Earbuds Pro", "product",
                          "Good sound and nice design. Battery is ok."),
}

CSS = (f"""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&family=Hind+Siliguri:wght@400;500;600&display=swap" rel="stylesheet">
<style>
html, body, [class*="st-"], .stMarkdown, textarea, input, button {{
  font-family: Inter, 'Hind Siliguri', system-ui, sans-serif; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], footer {{ display: none; }}
.block-container {{ padding-top: 1.2rem; max-width: 1240px; }}
[data-testid="stVerticalBlockBorderWrapper"] > div {{ background: #FFFFFF; border-radius: 16px; }}
div[data-testid="stTextArea"] textarea {{ font-size: 16px; line-height: 1.6; }}
.stButton > button[kind="primary"] {{ height: 48px; border-radius: 12px; font-weight: 600; font-size: 16px; }}
.stButton > button[kind="secondary"] {{ border-radius: 999px; }}

.rc-top {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px;
          padding: 4px 0 18px; border-bottom: 1px solid {LINE}; margin-bottom: 20px; }}
.rc-brand {{ display:flex; align-items:center; gap:12px; }}
.rc-brand b {{ font-family:'Space Grotesk', Inter, sans-serif; font-size:26px; color:{INK}; }}
.rc-tag {{ color:{MUTED}; font-size:14px; }}
.rc-langs span {{ display:inline-block; padding:5px 12px; border-radius:999px; background:#FFFFFF;
                  border:1px solid {LINE}; font-size:13px; color:{INK}; margin-left:6px; }}
.rc-h {{ font-family:'Space Grotesk', Inter, sans-serif; font-size:20px; font-weight:700; color:{INK}; margin:0 0 4px; }}
.rc-sub {{ color:{MUTED}; font-size:14px; margin:0 0 6px; }}

.rc-card {{ background:#FFFFFF; border:1px solid {LINE}; border-radius:16px; padding:22px 24px; margin-bottom:14px; color:{INK}; }}
.rc-score {{ display:flex; flex-wrap:wrap; gap:24px; align-items:center; }}
.rc-ringwrap {{ position:relative; width:118px; height:118px; flex:none; }}
.rc-ringnum {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.rc-ringnum b {{ font-family:'Space Grotesk', Inter, sans-serif; font-size:42px; line-height:1; }}
.rc-ringnum span {{ font-size:12px; color:{MUTED}; }}
.rc-badge {{ display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:600; margin-bottom:8px; }}
.rc-level {{ font-size:18px; font-weight:600; margin:0 0 6px; }}
.rc-next {{ display:flex; gap:8px; align-items:flex-start; color:{MUTED}; font-size:14px; }}

.rc-ctitle {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:14px; }}
.rc-ctitle b {{ font-size:16px; }}
.rc-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px 22px; }}
@media (max-width: 700px) {{ .rc-grid {{ grid-template-columns:1fr; }} }}
.rc-group h4 {{ margin:0 0 8px; font-size:12px; letter-spacing:.07em; text-transform:uppercase; color:{MUTED}; font-weight:600; }}
.rc-check {{ display:flex; gap:10px; align-items:center; padding:7px 10px; border-radius:10px; margin:4px 0; font-size:14px; }}
.rc-check.ok {{ background:{TEAL_L}; color:{TEAL_D}; }}
.rc-check.no {{ background:#FAFAF7; color:{INK}; border:1px dashed #D3D3CB; }}
.rc-check svg {{ flex:none; }}

.rc-tip {{ display:flex; gap:14px; padding:14px 16px; border-radius:12px; background:{ORANGE_L}; margin:10px 0 0; }}
.rc-tipnum {{ flex:none; width:28px; height:28px; border-radius:50%; background:{ORANGE}; color:#FFFFFF;
              display:flex; align-items:center; justify-content:center; font-weight:700; font-size:14px; }}
.rc-tip b {{ display:block; color:{ORANGE_D}; font-size:13px; text-transform:capitalize; margin-bottom:2px; }}
.rc-tip p {{ margin:0; line-height:1.5; }}
.rc-tip small {{ color:{MUTED}; }}
.rc-good {{ padding:14px 16px; border-radius:12px; background:{TEAL_L}; color:{TEAL_D}; font-weight:500; }}

.rc-why {{ color:{MUTED}; font-size:13px; margin: 2px 0 10px; }}
.rc-why b {{ color:{INK}; font-weight:600; }}
.rc-empty {{ text-align:left; }}
.rc-steps {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:16px; }}
@media (max-width: 700px) {{ .rc-steps {{ grid-template-columns:1fr; }} }}
.rc-step {{ background:{BG}; border-radius:12px; padding:14px; }}
.rc-step span {{ display:inline-flex; width:26px; height:26px; border-radius:50%; background:{INK}; color:#FFFFFF;
                 align-items:center; justify-content:center; font-weight:700; font-size:13px; margin-bottom:8px; }}
.rc-step p {{ margin:0; font-size:14px; line-height:1.45; }}
.rc-crit {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:14px; }}
.rc-crit div {{ font-size:13px; color:{MUTED}; }} .rc-crit b {{ color:{INK}; text-transform:capitalize; }}
</style>""")
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


def icon_check(color):
    return (f"<svg width='18' height='18' viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='11' "
            f"fill='{color}'/><path d='M7 12.5l3.2 3.2L17 9' stroke='#fff' stroke-width='2.4' fill='none' "
            f"stroke-linecap='round' stroke-linejoin='round'/></svg>")


def icon_open(color):
    return (f"<svg width='18' height='18' viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='10' "
            f"fill='none' stroke='{color}' stroke-width='2'/><path d='M12 8v8M8 12h8' stroke='{color}' "
            f"stroke-width='2' stroke-linecap='round'/></svg>")


def band(score):
    if score >= 7:
        return TEAL, TEAL_L, "Useful review"
    if score >= 5:
        return AMBER, AMBER_L, "Getting there"
    return ORANGE, ORANGE_L, "Needs more detail"


def ring(score, color):
    r, c = 50, 2 * 3.14159 * 50
    filled = c * score / 10
    return (f"<div class='rc-ringwrap'><svg width='118' height='118' viewBox='0 0 118 118' role='img' "
            f"aria-label='Score {score} of 10'><circle cx='59' cy='59' r='{r}' fill='none' stroke='{LINE}' "
            f"stroke-width='10'/><circle cx='59' cy='59' r='{r}' fill='none' stroke='{color}' stroke-width='10' "
            f"stroke-linecap='round' stroke-dasharray='{filled:.1f} {c:.1f}' transform='rotate(-90 59 59)'/></svg>"
            f"<div class='rc-ringnum'><b style='color:{color}'>{score}</b><span>out of 10</span></div></div>")


def sparkline(scores):
    w, h, pad = 520, 120, 26
    n = len(scores)
    xs = [pad + i * (w - 2 * pad) / max(1, n - 1) for i in range(n)]
    ys = [h - pad - (s - 1) * (h - 2 * pad) / 9 for s in scores]
    pts = " ".join(f"{x:.0f},{y:.0f}" for x, y in zip(xs, ys))
    dots = "".join(f"<circle cx='{x:.0f}' cy='{y:.0f}' r='6' fill='{band(s)[0]}'/>"
                   f"<text x='{x:.0f}' y='{y - 12:.0f}' text-anchor='middle' font-size='13' font-weight='700' "
                   f"fill='{INK}'>{s}</text><text x='{x:.0f}' y='{h - 4}' text-anchor='middle' font-size='11' "
                   f"fill='{MUTED}'>Draft {i + 1}</text>" for i, (x, y, s) in enumerate(zip(xs, ys, scores)))
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='Scores of your drafts: "
            f"{', '.join(map(str, scores))}'><polyline points='{pts}' fill='none' stroke='#C9C9C1' "
            f"stroke-width='2'/>{dots}</svg>")


def use_example(name):
    ss.product, ss.category, ss.review_text = EXAMPLES[name]


def new_review():
    ss.sid = ss.result = ss.eval_id = None
    ss.review_text = ss.product = ""


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("<p class='rc-h'>Settings</p>", unsafe_allow_html=True)
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    judge = st.radio("Judge", ["gemini", "mock"], index=0 if has_key else 1,
                     format_func=lambda j: {"gemini": "Gemini (real score)",
                                            "mock": "Mock (no API, for testing)"}[j])
    if judge == "gemini" and not has_key:
        st.warning("GEMINI_API_KEY is not set in the terminal that started the app.")
    st.caption("With the Gemini judge, your review text is sent to Google's Gemini model to be checked. "
               "Nothing is posted anywhere, and no names or emails are stored.")

# ---------------------------------------------------------------- header
st.markdown(f"""
<div class='rc-top'>
  <div class='rc-brand'>
    <svg width='36' height='36' viewBox='0 0 24 24' fill='none' stroke='{TEAL}' stroke-width='2' stroke-linecap='round'
         stroke-linejoin='round' aria-hidden='true'><path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'/>
         <path d='M8 10l2.5 2.5L16 7'/></svg>
    <div><b>Review Coach</b><div class='rc-tag'>Write a review that actually helps the next buyer</div></div>
  </div>
  <div class='rc-langs'><span>বাংলা</span><span>Banglish</span><span>English</span></div>
</div>""", unsafe_allow_html=True)

left, right = st.columns([5, 6], gap="large")

# ---------------------------------------------------------------- input
with left:
    with st.container(border=True):
        st.markdown("<p class='rc-h'>Your review</p><p class='rc-sub'>Write it the way you would on the shop's "
                    "page, then check it.</p>", unsafe_allow_html=True)
        st.text_input("Product", key="product", placeholder="e.g. Foaming Facial Cleanser 236 ml")
        st.segmented_control("Type", ["book", "skincare", "product"], key="category",
                             format_func=lambda c: {"book": "Book", "skincare": "Skincare",
                                                    "product": "Other product"}[c])
        st.text_area("Review", key="review_text", height=210,
                     placeholder="What did you buy, how long have you used it, what was good or bad?")
        words = len(ss.review_text.split())
        st.caption(f"{words} word{'s' if words != 1 else ''}"
                   + ("" if words >= 15 or not words else " · more detail usually helps"))
        go = st.button("Check my review", type="primary", use_container_width=True)
        if ss.sid is not None:
            st.button("Start a new review", on_click=new_review, use_container_width=True)

    st.markdown("<p class='rc-sub' style='margin-top:6px'>Or try an example:</p>", unsafe_allow_html=True)
    ex = st.columns(len(EXAMPLES))
    for col, name in zip(ex, EXAMPLES):
        col.button(name, on_click=use_example, args=(name,), use_container_width=True)

    if go:
        product, category, review = ss.product, ss.category or "product", ss.review_text
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
                with right:
                    with st.spinner("Reading your review..."):
                        r = hit or evaluate(product, review, judge=judge)
                ss.eval_id, _ = db.save(con, ss.sid, review, r, key, from_cache=hit is not None)
                ss.result = r
            except Exception as e:
                st.error(str(e))

# ---------------------------------------------------------------- results
with right:
    r = ss.result
    if r is None:
        crit = "".join(f"<div><b>{c}</b><br>{CRITERION_TEXT[c]}</div>" for c in CRITERIA)
        st.markdown(f"""
<div class='rc-card rc-empty'>
  <p class='rc-h'>How it works</p>
  <p class='rc-sub'>A useful review helps another buyer decide. Review Coach checks yours against four points.</p>
  <div class='rc-steps'>
    <div class='rc-step'><span>1</span><p>Write your review in Bangla, Banglish or English.</p></div>
    <div class='rc-step'><span>2</span><p>Get a score, a checklist and tips made for your review.</p></div>
    <div class='rc-step'><span>3</span><p>Add what is missing and check again. Watch the score rise.</p></div>
  </div>
  <div class='rc-crit'>{crit}</div>
</div>""", unsafe_allow_html=True)
    else:
        color, light, label = band(r["score"])
        nxt = (f"<div class='rc-next'><svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='{MUTED}' "
               f"stroke-width='2' stroke-linecap='round' aria-hidden='true' style='margin-top:2px; flex:none'>"
               f"<path d='M5 12h14M13 6l6 6-6 6'/></svg><span><b>To reach {esc(r['next_level'].split(':')[0])}:</b> "
               f"{esc(r['next_level'].split(': ', 1)[1])}</span></div>") if r["next_level"] else \
              "<div class='rc-next'>Top level reached.</div>"
        st.markdown(f"""
<div class='rc-card rc-score'>
  {ring(r['score'], color)}
  <div style='flex:1 1 240px; min-width:0'>
    <span class='rc-badge' style='background:{light}; color:{color}'>{label}</span>
    <p class='rc-level'>{esc(r['level_meaning'][:1].upper() + r['level_meaning'][1:])}</p>
    {nxt}
  </div>
</div>""", unsafe_allow_html=True)

        if r["how_to_improve"]:
            tips = "".join(
                f"<div class='rc-tip'><div class='rc-tipnum'>{i}</div><div><b>{esc(c)}</b>"
                f"<p>{esc(t)}</p><small>{esc(CRITERION_TEXT.get(c, ''))}</small></div></div>"
                for i, (c, t) in enumerate(r["how_to_improve"].items(), 1))
            st.markdown(f"<div class='rc-card'><div class='rc-ctitle'><b>What to add next</b>"
                        f"<span class='rc-sub'>{len(r['how_to_improve'])} tip"
                        f"{'s' if len(r['how_to_improve']) != 1 else ''}</span></div>{tips}</div>",
                        unsafe_allow_html=True)
        else:
            st.markdown("<div class='rc-card'><div class='rc-good'>Nothing important is missing. "
                        "This review is very useful to a buyer.</div></div>", unsafe_allow_html=True)

        groups = []
        for c in CRITERIA:
            rows = "".join(
                f"<div class='rc-check {'ok' if r['checks'][k] else 'no'}'>"
                f"{icon_check(TEAL) if r['checks'][k] else icon_open('#8A8D93')}<span>{CHECK_LABELS[k]}</span></div>"
                for k in CHECK_GROUPS[c])
            groups.append(f"<div class='rc-group'><h4>{c}</h4>{rows}</div>")
        st.markdown(f"<div class='rc-card'><div class='rc-ctitle'><b>Checklist</b><span class='rc-sub'>"
                    f"{r['checks_met']} of 10 present</span></div><div class='rc-grid'>{''.join(groups)}</div></div>",
                    unsafe_allow_html=True)

        st.markdown(f"<div class='rc-why'><b>Why this score:</b> {esc(r['reason'])}<br>"
                    f"Judge: {esc(r['judge'])} · detected language: {esc(r['language'])} · "
                    f"{r['latency_ms']} ms</div>", unsafe_allow_html=True)

        if ss.eval_id not in ss.rated:
            a, b, _ = st.columns([2, 2, 2])
            if a.button("Tips helped", use_container_width=True):
                db.rate(con, ss.eval_id, 1); ss.rated.add(ss.eval_id); st.rerun()
            if b.button("Not helpful", use_container_width=True):
                db.rate(con, ss.eval_id, 0); ss.rated.add(ss.eval_id); st.rerun()
        else:
            st.caption("Thanks for the feedback.")

        hist = db.history(con, ss.sid)
        if len(hist) > 1:
            scores = [h["score"] for h in hist]
            change = scores[-1] - scores[0]
            st.markdown(f"<div class='rc-card'><div class='rc-ctitle'><b>Your drafts</b><span class='rc-sub'>"
                        f"{'+' if change >= 0 else ''}{change} since your first draft</span></div>"
                        f"{sparkline(scores)}</div>", unsafe_allow_html=True)

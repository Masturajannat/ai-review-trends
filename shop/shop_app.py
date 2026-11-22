"""ShopLite: a very small dummy shop. Pick a product, read its reviews, press "Write a review"
to open Review Coach for that product. A review submitted there shows up here.

    cd shop
    python build_shop_db.py            # once
    python -m streamlit run shop_app.py --server.port 8502
"""
import html, os
import streamlit as st

import shop_db

COACH_URL = os.environ.get("COACH_URL", "http://localhost:8501")       # where Review Coach runs
PAGE = 20                                                                # reviews shown at a time
LANGS = {"All": None, "English": "english", "Bangla": "bangla", "Banglish": "banglish"}

st.set_page_config(page_title="ShopLite", page_icon="🛍", layout="wide")
esc = html.escape
ss = st.session_state

st.markdown("""
<style>
[data-testid="stHeader"] { background:transparent; }
.block-container { max-width:1150px; padding-top:1.5rem; }
.sl-bar { background:#1E3A8A; color:#fff; border-radius:12px; padding:14px 20px; font-size:22px; font-weight:800; margin-bottom:18px; }
.sl-tile { height:90px; border-radius:10px; display:flex; align-items:center; justify-content:center;
           font-size:34px; font-weight:800; color:#fff; margin-bottom:8px; }
.sl-name { font-weight:600; line-height:1.3; height:2.6em; overflow:hidden; }
.sl-chip { display:inline-block; font-size:12px; font-weight:700; padding:2px 9px; border-radius:20px; background:#E9EEF7; color:#1E3A8A; }
.sl-muted { color:#64748B; font-size:13px; }
.sl-rev { border:1px solid #DCE3EE; border-radius:10px; padding:12px 16px; margin-bottom:8px; background:#fff; color:#0F172A; }
.sl-rev p { margin:0 0 6px; line-height:1.55; white-space:pre-wrap; }
</style>""", unsafe_allow_html=True)
st.markdown("<div class='sl-bar'>🛍 ShopLite</div>", unsafe_allow_html=True)


def open_product(pid):
    st.query_params["p"] = pid
    ss.shown = PAGE


def go_home():
    st.query_params.clear()


def colour(pid):
    return f"hsl({int(pid) * 47 % 360}, 45%, 42%)"           # a steady colour per product, in place of a photo


def nice_date(iso):
    try:
        y, m, d = iso[:10].split("-")
        return f"{int(d)} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(m) - 1]} {y}"
    except (ValueError, TypeError, IndexError):
        return ""


try:
    pid = st.query_params.get("p")
    prod = shop_db.product(pid) if pid else None
    items = None if pid else shop_db.products()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

# ---------------------------------------------------------------- home: all products
if not pid:
    st.subheader("Products")
    cols = st.columns(4)
    for i, p in enumerate(items):
        with cols[i % 4].container(border=True):
            st.markdown(f"<div class='sl-tile' style='background:{colour(p['product_id'])}'>{esc(p['name'][0].upper())}</div>"
                        f"<div class='sl-name'>{esc(p['name'])}</div>"
                        f"<div style='margin:6px 0'><span class='sl-chip'>{esc(p['type'])}</span></div>"
                        f"<div class='sl-muted' style='margin-bottom:8px'>{p['n']:,} reviews</div>", unsafe_allow_html=True)
            st.button("View", key=f"v{p['product_id']}", on_click=open_product, args=(p["product_id"],),
                      use_container_width=True)
    st.stop()

# ---------------------------------------------------------------- one product
if prod is None:
    st.warning("We could not find that product.")
    st.button("← All products", on_click=go_home)
    st.stop()

ss.setdefault("shown", PAGE)
st.button("← All products", on_click=go_home)
left, right = st.columns([1, 2], gap="large")
with left:
    st.markdown(f"<div class='sl-tile' style='height:200px;font-size:70px;background:{colour(prod['product_id'])}'>"
                f"{esc(prod['name'][0].upper())}</div>", unsafe_allow_html=True)
with right:
    st.markdown(f"<h2 style='margin:0 0 8px'>{esc(prod['name'])}</h2>"
                f"<span class='sl-chip'>{esc(prod['type'])}</span> "
                f"<span class='sl-muted'>&nbsp;{prod['n']:,} reviews</span>", unsafe_allow_html=True)
    st.write("")
    st.link_button("✏️ Write a review", f"{COACH_URL}/?product={prod['product_id']}", type="primary")

st.subheader("Customer reviews")
lang = st.radio("Language", list(LANGS), horizontal=True, label_visibility="collapsed", key="lang",
                on_change=lambda: ss.update(shown=PAGE))
rows, total = shop_db.reviews(prod["product_id"], LANGS[lang], ss.shown)
if not rows:
    st.caption("No reviews in this language yet.")
for r in rows:
    new = "<span class='sl-chip' style='background:#FFE1E7;color:#BE123C'>New</span> " if r["source"] == "coach" else ""
    st.markdown(f"<div class='sl-rev'><p>{esc(r['review_text'])}</p>"
                f"<div class='sl-muted'>{new}{esc(nice_date(r['written_at']))}</div></div>", unsafe_allow_html=True)
if total > len(rows):
    st.button(f"Show more ({total - len(rows):,} more)", on_click=lambda: ss.update(shown=ss.shown + PAGE))

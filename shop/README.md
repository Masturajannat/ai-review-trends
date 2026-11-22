# ShopLite (dummy shop for Review Coach)

A tiny shop with the 20 most reviewed products of the dataset. Open a product, read its reviews,
press **Write a review** to go to Review Coach for that product. After **Submit review** in the
coach, the review is at the top of the product's list here.

    python run_demo.py                       # from the folder above: starts both and opens the shop

or by hand, in two terminals:

    cd shop && python build_shop_db.py       # once: makes shop.db (running it again resets the reviews)
    cd shop && python -m streamlit run shop_app.py --server.port 8502
    cd review_coach && python -m streamlit run app.py --server.port 8501

`build_shop_db.py` holds the name and type of each product (the type, e.g. "body wash", is sent to
Gemini so a review of another kind of product can be noticed). Edit them there, then rebuild.

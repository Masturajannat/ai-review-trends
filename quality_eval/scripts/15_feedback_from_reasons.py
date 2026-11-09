"""Step 15: improvement feedback from Gemini's existing reasons, with no API calls.

Every scored review already has a one-sentence reason from Gemini, e.g.
  "The review praises the book's emotional impact, but lacks specific details about the plot."
This step reads that reason, together with the score, and turns it into feedback in the same
form as the scoring prompt's criteria (the four points of A GOOD REVIEW):

  weak_criteria    the criteria the review falls short on: specific | personal | reasoned | relevant
  how_to_improve   one suggestion per weak criterion, as a JSON object {"criterion": "suggestion"}

How a criterion is chosen (rules, not a model):
  relevant  the reason calls the review off-topic: a question or request to the seller, spam,
            advertising, or a copied description
  specific  the part of the reason after "but / lacks / without / only ..." asks for details,
            information, features, performance, plot or content, or calls the review generic
  personal  that part asks for personal use, experience, context, usage or results over time
  reasoned  that part asks for depth, explanation, analysis, evaluation, comparison or pros/cons
If the reason names nothing, the score decides: up to 4 -> specific; 5-6 -> specific; 7-8 ->
reasoned (more depth or balance); 9-10 -> nothing to improve.

Suggestions use the product type (books on Rokomari, skincare on Shajgoj, other products on
Daraz). When the reason says what is missing ("lacks details about the plot"), the specific
suggestion names it ("Add specific details about the plot.").

This is an approximation built from the score's reason; it is not a new judgement by Gemini.

  python scripts/12_combine_scores.py          # first: one row per scored review
  python scripts/15_feedback_from_reasons.py   # writes all_scores_feedback.csv and .json
"""
import json, os, re
import pandas as pd
from common import ROOT, save_table

CRITERIA = ["specific", "personal", "reasoned", "relevant"]

OFF_TOPIC = re.compile(r"off-topic|question (?:to|for|directed)|directed (?:to|at) the seller|request|restock|"
                       r"spam|advertis|promotional|rather than (?:a |an )?(?:review|evaluat|information|describ|shar)|"
                       r"not (?:a |an )?(?:review|evaluation)|unrelated|product description|blurb|copied|copies|"
                       r"discount group|coupon|referral|promo code|exclusively about")
NEG_START = re.compile(r"\b(but|though|although|however|yet|lacks?|lacking|without|missing|no|only|rather than|"
                       r"does not|doesn't|fails?|limited|minimal|generic|vague)\b")
CUES = {
    "specific": re.compile(r"specific|detail|concrete|information|generic|vague|feature|performance|plot|"
                           r"content|quality|stories|characters|ingredient|substance"),
    "personal": re.compile(r"personal|own use|own experience|reading experience|experience with|usage|use over|"
                           r"long-term|how long|first impression|not yet|context|hands-on|over time|duration|"
                           r"results|situation"),
    "reasoned": re.compile(r"depth|deeper|explain|explanation|reason|analysis|evaluat|critique|compar|pros|cons|"
                           r"balanced|drawback|downside|insight|elaborat|why"),
}
ABOUT = re.compile(r"(?:details?|information|specifics)\s+(?:about|on|of|regarding)\s+([^.;]+?)(?:[.;]|,? but |$)")

TIPS = {
    "book": {
        "specific": "Mention what you liked or disliked in the story, characters or writing style.",
        "personal": "Say how the book affected you, when you read it, or who you would recommend it to.",
        "reasoned": "Explain why you liked or disliked it, or compare it with another book by the same author.",
        "relevant": "Write about your own reading of the book instead of a question, request or summary.",
    },
    "skincare": {
        "specific": "Describe the effect on your skin (oiliness, acne, dryness, glow) and its texture or smell.",
        "personal": "Mention your skin type and how long and how often you used it.",
        "reasoned": "Say what worked and what did not, or compare it with a product you used before.",
        "relevant": "Share your experience with the product instead of a question or request to the shop.",
    },
    "product": {
        "specific": "Mention concrete details: quality, size, performance, or the condition it arrived in.",
        "personal": "Say how long you have used it and in what situation.",
        "reasoned": "Give a reason for your opinion: a pro and a con, or a comparison with a similar product.",
        "relevant": "Share your experience with the product instead of a question or request to the seller.",
    },
}
CATEGORY = {"Rokomari": "book", "Shajgoj": "skincare", "Daraz": "product"}
GENERIC_OBJECTS = {"the product", "the product itself", "the book", "the book itself", "it", "the item"}


def negative_part(reason):
    m = NEG_START.search(reason)
    return reason[m.start():] if m else ""


def missing_object(neg):
    """'lacks specific details about the plot or characters' -> 'the plot or characters'."""
    m = ABOUT.search(neg)
    if not m:
        return None
    obj = m.group(1).strip().rstrip(",")
    obj = re.split(r",? (?:and|or) (?:lacks|no|without)\b", obj)[0].strip()
    obj = re.sub(r"\s+itself$", "", obj)
    # "the product or the buying experience", "the book or buying experience": too vague, use the template
    vague = re.match(r"(?:the )?(?:product|book|item|purchase|buying experience)\b", obj) and \
        re.search(r"\bor\b|^(?:the )?(?:product|book|item)$", obj)
    if not obj or obj in GENERIC_OBJECTS or vague or len(obj) > 70:
        return None
    return obj


def feedback(score, reason, platform):
    r = str(reason).lower()
    cat = CATEGORY.get(platform, "product")
    weak = []
    if score >= 9:
        return [], {}
    if OFF_TOPIC.search(r):
        weak.append("relevant")
    neg = negative_part(r)
    for c in ["specific", "personal", "reasoned"]:
        if neg and CUES[c].search(neg):
            weak.append(c)
    if score <= 4 and "specific" not in weak:
        weak.append("specific")
    if not weak:
        weak.append("specific" if score <= 6 else "reasoned")
    weak = [c for c in CRITERIA if c in weak]
    tips = {c: TIPS[cat][c] for c in weak}
    obj = missing_object(neg)
    if "specific" in weak and obj:
        tips["specific"] = f"Add specific details about {obj}."
    return weak, tips


def main():
    src = os.path.join(ROOT, "all_scores.csv")
    if not os.path.exists(src):
        raise SystemExit("all_scores.csv not found: run scripts/12_combine_scores.py first")
    d = pd.read_csv(src, dtype={"review_id": str})
    for c in ["weak_criteria", "how_to_improve", "feedback_from"]:
        d[c] = d[c].astype("object") if c in d else pd.Series([pd.NA] * len(d), dtype="object")
    todo = d["how_to_improve"].isna()          # keep any feedback Gemini already gave
    out = [feedback(s, r, p) for s, r, p in zip(d.loc[todo, "score"], d.loc[todo, "reason"], d.loc[todo, "platform"])]
    d.loc[todo, "weak_criteria"] = ["|".join(w) for w, _ in out]
    d.loc[todo, "how_to_improve"] = [json.dumps(t, ensure_ascii=False) for _, t in out]
    d.loc[todo, "feedback_from"] = "reason_rules"
    dst = os.path.join(ROOT, "all_scores_feedback.csv")
    js = save_table(d, dst)

    w = d["weak_criteria"].fillna("")
    print(f"{len(d)} reviews -> {dst}\n  and {js}")
    print("feedback source:", d["feedback_from"].value_counts().to_dict())
    print("criteria to improve (share of reviews):")
    for c in CRITERIA:
        print(f"  {c:9s} {w.str.contains(c).mean():.0%}")
    print(f"  nothing   {(w == '').mean():.0%}")
    band = pd.cut(d["score"], [0, 4, 6, 8, 10], labels=["1-4", "5-6", "7-8", "9-10"])
    print("\naverage number of criteria to improve, by score:")
    print(w.str.split("|").map(lambda x: len([y for y in x if y])).groupby(band, observed=True).mean().round(1).to_string())


if __name__ == "__main__":
    main()

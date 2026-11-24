"""Console log for Review Coach: what came in, how the score was made, and why.

Printed in the terminal that runs the app. It never changes the page or the score.

    1. the request (product, review, language, words)
    2. how the score was made (tokens read, model output, rounding, level)
    3. what the model reacted to: how many points each sentence added (our model)
    4. the response sent to the page
    5. a short note from Gemini: it is given the review, the score and the sentence
       points, and only explains them. It does not score and is not used for the score.
"""
import os, threading, time

import evaluator as ev

NOTE_PROMPT = os.path.join(ev.HERE, "prompts", "console_note_v1.txt")
NOTE_IN_BACKGROUND = True          # True: the page does not wait for Gemini; the note prints when it arrives
_lock, _count = threading.Lock(), [0]


def say(text):
    """Print in one piece; a console that cannot show Bangla falls back to plain characters."""
    with _lock:
        try:
            print(text, flush=True)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode(), flush=True)


def short(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 3] + "..."


# ---------------------------------------------------------------- the model's side
def model_trace(review):
    """The steps from the model's raw output to the score (one more pass of the model)."""
    tok, model, scale, torch = ev.load_model()
    text = ev.strip_read_more(review)
    max_len = int(scale.get("max_len", 256))
    n_tokens = len(tok(text)["input_ids"])
    enc = tok(text, truncation=True, max_length=max_len, return_tensors="pt")
    enc.pop("token_type_ids", None)
    with torch.no_grad():
        z = model(**enc).logits.float().squeeze().item()
    value = z * scale["std"] + scale["mean"]
    return {"n_tokens": n_tokens, "max_len": max_len, "z": z, "std": scale["std"], "mean": scale["mean"],
            "value": value, "kept": min(10.0, max(1.0, value))}


def evidence(review):
    """Points each sentence added to the score: whole review minus the review without that sentence."""
    imp = ev.part_importance(review)
    return [{"text": imp["text"][p["start"]:p["end"]], "value": p["value"], "read": p["read"]}
            for p in imp["parts"]]


# ---------------------------------------------------------------- Gemini's note
def evidence_lines(parts):
    lines = [f'{p["value"]:+.1f} | "{short(p["text"], 120)}"' for p in parts if p["value"] is not None]
    return "\n".join(lines) or "(only one sentence, nothing to compare)"


def note_prompt(product, ptype, review, score, meaning, parts):
    t = open(NOTE_PROMPT, encoding="utf-8").read()
    for key, val in {"{product_name}": product or "(not given)", "{product_type}": ptype or "(not given)",
                     "{score}": f"{score:g}", "{level_meaning}": meaning or "", "{evidence}": evidence_lines(parts),
                     "{review_text}": review}.items():
        t = t.replace(key, val)
    return t


def parse_note(j):
    def items(key, n):
        return [" ".join(str(x).split()) for x in (j.get(key) or []) if str(x).strip()][:n]
    why = " ".join(str(j.get("why") or "").split())
    if not why:
        raise ValueError("no reasoning in the answer")
    return {"why": why, "found": items("found", 3), "not_mentioned": items("not_mentioned", 2)}


def print_note(n, note=None, error=None):
    out = [f"---- NOTE for request #{n}: Gemini's reading of the model's score. Explanation only, "
           "not used for the score ----"]
    if error:
        out.append(f"note unavailable: {short(error, 160)}")
    else:
        out.append(f"why           : {note['why']}")
        out += [f"found         : {x}" for x in note["found"]]
        out += [f"not mentioned : {x}" for x in note["not_mentioned"]]
    say("\n".join(out))


def write_note(n, args):
    try:
        note = ev._ask_gemini(note_prompt(*args), parse_note, retries=2)
        print_note(n, note=note)
    except Exception as e:
        print_note(n, error=str(e))


# ---------------------------------------------------------------- the log
def log_rating(product, ptype, review, r, cached=False, judge="model", note=True):
    """Print the log of one rating. `r` is the score result the page uses. Any problem here is printed and never reaches the page."""
    try:
        _log(product, ptype, review.strip(), r, cached, judge, note)
    except Exception as e:
        say(f"[console log failed: {e}]")


def _log(product, ptype, review, r, cached, judge, note):
    with _lock:
        _count[0] += 1
        n = _count[0]
    own = judge == "model"
    out = [f"==== REQUEST #{n} | {time.strftime('%H:%M:%S')} ====",
           f"product : {product}" + (f" ({ptype})" if ptype else ""),
           f'review  : "{short(review, 300)}"',
           f"          {r.get('word_count', len(review.split()))} words | {r.get('language', '?')} | "
           f"score from: {'our trained model' if own else judge} | score reused from cache: {'yes' if cached else 'no'}",
           "---- HOW THE SCORE WAS MADE ----"]
    parts = []
    if own:
        t = model_trace(review)
        cut = t["n_tokens"] > t["max_len"]
        out.append(f"tokens  : {min(t['n_tokens'], t['max_len'])} of {t['max_len']} read"
                   + (f" ({t['n_tokens'] - t['max_len']} at the end were cut)" if cut else " (nothing cut)"))
        out.append(f"model   : output {t['z']:.3f} x {t['std']:.2f} + {t['mean']:.2f} = {t['value']:.2f}"
                   f" -> kept between 1 and 10: {t['kept']:.2f} -> rounded to half points: {r['score']:g}")
    else:
        out.append(f"the {judge} judge gave this score directly; the steps and sentence points below are for our "
                   "trained model only")
    out.append(f"level   : {r.get('level')} = {r.get('level_meaning')}")
    if own:
        parts = evidence(review)
        out.append("---- WHY: WHAT OUR MODEL REACTED TO ----")
        out.append("points = score of the whole review minus the score without that sentence")
        if all(p["value"] is None for p in parts):
            out.append("only one sentence, so there is nothing to compare")
        else:
            for p in parts:
                pts = f"{p['value']:+.1f}" if p["value"] is not None else " n/a"
                out.append(f'  {pts:>5}  "{short(p["text"], 90)}"' + ("" if p["read"] else "   (not read: past the token limit)"))
    out.append(f"==== RESPONSE #{n}: score {r['score']:g} sent to the page ({r.get('latency_ms', 0)} ms) ====")
    say("\n".join(out))

    if not note:
        return
    if not os.environ.get("GEMINI_API_KEY"):
        print_note(n, error="GEMINI_API_KEY is not set")
        return
    args = (product, ptype, review, r["score"], r.get("level_meaning"), parts)
    if NOTE_IN_BACKGROUND:
        threading.Thread(target=write_note, args=(n, args), daemon=True).start()
    else:
        write_note(n, args)

"""Shared text helpers for the original-language pipeline: cleaning, word counts, language tags."""
import html
import re
import unicodedata

BENGALI = re.compile(r"[ঀ-৿]")
LATIN = re.compile(r"[A-Za-z]")
# text emoticons, only when they stand alone (so "experience" or "x-ray" are never touched)
EMOTICON = re.compile(r"(?<![A-Za-z0-9])(?:[:;=][\-^']?[)(\]\[dDpPoO/\\|*3]+|<3+|\^_*\^|[xX][dD]+)(?![A-Za-z0-9])")
KEEP_FORMAT = {"‌", "‍"}  # ZWNJ/ZWJ are used inside Bengali words; removed only next to emoji

ENGLISH_WORDS = set("""
a about above after again against all am an and any are as at be because been before being below between
both but by can could did do does doing down during each few for from further had has have having he her
here hers him his how i if in into is it its itself just me more most my no nor not now of off on once only
or other our out over own same she should so some such than that the their them then there these they this
those through to too under until up very was we were what when where which while who whom why will with would
you your good nice great best excellent quality product products delivery seller fast price recommended
received really love loved awesome amazing well worth packaging original thanks thank buy bought using used
use works working perfect fine bad poor book books skin face sound battery money value
""".split())

BANGLISH_WORDS = set("""
ami amar amr amra amader tumi tomar apni apnar apnara apnader se tar tara ora ke ki kি
valo vlo bhalo balo bhlo valoi bhaloi khub khubi onek onk beshi besi kom ekdom ekta ekti eta eti eita oita ota
oi ei ta ti tai er e o r ar abar kintu tobe jodi karon jonno jnno moto mto sathe shathe theke thke
kore kre korsi korchi korechi korlam korbo korben koren korte korle korbe kori korar kora
kinlam kinsi kinechi kinbo kinben kine kinte nilam nisi niyechi nibo niben nen nite nile nao
pelam paisi peyechi pabo paben pai pay pete pawa paoa dise disi diyeche dilo diye dio den deya dewa
hoise hoyeche hoye hoy hobe hoini hoyni hocche hosse chilo silo cilo ache ase achhe nai nei na nah
lagse lagche laglo lage lagbe laglam lagsilo dam daam dame taka tk vai bhai apu bhaiya
kichu kicu kono keu sob shob sobai sobar shobai onno arekta arekti ekhon ajke kal kalke din por pore age
diyese disen dise disilo saisi chaisi paise paisen nici nisi nichi cilo hoice hoyse hoise valona valoi vaalo
valo lage ni nai nay paren paben parenn kachr kache kase moddhe modde mddhe mdhe sabai shobai anok onak onek
rokom kono derite deri aktu ektu basi beshi lagce lagse jinis jinish jinishta jinista mutamuti motamuti
kemon kivabe keno kobe kothay jeta jemon temon emon emni
sundor shundor darun dorun mast joss osadharon oshadharon chomotkar valobasha poriman matro sotti shotti
bujhlam bujhte dekhlam dekhte dekhen dekhe chai chaile chacchi parben parbo pari parlam parsi
bole boli bollo bolte bolben thik thakle thake thakbe dorkar lagbe hoilo hoiche gese geche gelo jay jabe
""".split())


def clean_text(text):
    """Original text without emojis, emoticons and other symbols; spacing normalised."""
    if text is None or (isinstance(text, float) and text != text):
        return ""
    t = html.unescape(str(text))
    t = EMOTICON.sub(" ", t)
    out = []
    for ch in t:
        cat = unicodedata.category(ch)
        if ch in KEEP_FORMAT:
            out.append(ch)
        elif cat in ("So", "Sk", "Cs", "Co", "Cn") or ch == "️":
            out.append(" ")
        else:
            out.append(ch)
    t = "".join(out)
    t = re.sub(r"\s*[‌‍]\s*(?=\s|$)", " ", t)       # stray joiners left by removed emoji
    return re.sub(r"\s+", " ", t).strip()


def words(text):
    """Whitespace tokens that contain at least one letter (Bengali or Latin)."""
    return [w for w in text.split() if any(unicodedata.category(c).startswith("L") for c in w)]


def language_of(text):
    """bangla (Bengali script), english, banglish (Bengali in Latin letters) or mixed (both scripts)."""
    b, l = len(BENGALI.findall(text)), len(LATIN.findall(text))
    if b + l == 0:
        return "none"
    share_b = b / (b + l)
    if share_b >= 0.8:
        return "bangla"
    if share_b > 0.2:
        return "mixed"
    toks = re.findall(r"[a-z]+", text.lower())
    n_bl = sum(len(w) > 1 and w in BANGLISH_WORDS and w not in ENGLISH_WORDS for w in toks)
    n_en = sum(w in ENGLISH_WORDS for w in toks)
    # Banglish reviews mix in many English words, so two Banglish words are enough;
    # a single one counts only when the review has little English in it
    if n_bl >= 2 or (n_bl == 1 and n_en <= 2):
        return "banglish"
    return "english"

"""Deterministic checks. No model involved: these are cheap, repeatable, and cannot be talked into anything."""
import re
from .textutil import body, has_image, linear, split_options

RAW_LATEX = re.compile(r"\\(?:frac|sqrt|times|alpha|beta|theta|pi|mu|lambda|Delta|AA|vec|hat|left|right|begin|text)\b|\$\$?")
EXAM_TAG = re.compile(r"\(\s*(?:NEET|AIPMT|AIEEE|JEE(?:\s+(?:Main|Mains|Advanced))?|MHT[- ]?CET|KCET|BITSAT)[^)]{0,20}?\d{4}\s*\)", re.I)
FIGURE_REF = re.compile(r"\b(?:as shown|shown in (?:the )?(?:figure|fig|diagram)|in the figure|given figure|following figure)\b", re.I)
INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts)|you are (?:now )?(?:the )?(?:admin|system|developer)|"
    r"system prompt|mark this (?:report )?as (?:corrected|fixed|resolved)|as an ai|override|change the answer to [A-D]\b.*\bmark",
    re.I | re.S,
)


def question_flags(q):
    """Static problems visible in the stored record, whether or not anyone reported them."""
    b = body(q)
    qtype = q["questionType"]
    flags = []
    stem, opts = split_options(b.get("question") or "")
    q_text, s_text = linear(b.get("question")), linear(b.get("solution"))
    ans = b.get("answer")

    if qtype in ("scq", "mcq"):
        missing = [l for l in "ABCD" if l not in opts]
        if missing:
            flags.append({"flag": "option_missing", "detail": "no option " + ", ".join(missing)})
        blank = [l for l, t in opts.items() if not t]
        if blank:
            flags.append({"flag": "option_blank", "detail": "option " + ", ".join(blank) + " is empty"})
        seen = {}
        for l, t in opts.items():
            key = re.sub(r"\s+", "", t).lower()
            if key and key in seen:
                flags.append({"flag": "options_identical", "detail": f"options {seen[key]} and {l} are both '{t}'"})
            seen.setdefault(key, l)

    if qtype == "scq":
        if not (isinstance(ans, str) and re.fullmatch(r"[A-D]", ans)):
            flags.append({"flag": "answer_malformed", "detail": f"scq answer is {ans!r}"})
        elif ans not in opts:
            flags.append({"flag": "answer_points_nowhere", "detail": f"key {ans} has no option"})
        elif not opts[ans]:
            flags.append({"flag": "answer_points_to_blank", "detail": f"key {ans} is an empty option"})
    elif qtype == "mcq":
        ok = isinstance(ans, list) and ans and all(isinstance(a, str) and re.fullmatch(r"[A-D]", a) for a in ans)
        if not ok:
            flags.append({"flag": "answer_malformed", "detail": f"mcq answer is {ans!r}; expected a list of single letters"})
        letters = re.findall(r"[A-D]", " ".join(ans) if isinstance(ans, list) else str(ans))
        if len(letters) == 1 and not re.search(r"\(s\)|one or more|correct statements|which of the following are", q_text, re.I):
            flags.append({"flag": "type_suspect", "detail": "stored as mcq but only one letter keyed and the stem asks for one answer"})
    elif qtype == "integerQuestion":
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", str(ans).strip()):
            flags.append({"flag": "answer_malformed", "detail": f"integer answer is {ans!r}"})

    for name, text in (("question", q_text), ("solution", s_text)):
        m = RAW_LATEX.search(text)
        if m:
            flags.append({"flag": "raw_markup", "field": name, "detail": f"'{m.group(0)}' is visible as text"})
        m = EXAM_TAG.search(text)
        if m:
            flags.append({"flag": "exam_tag", "field": name, "detail": m.group(0)})
    if FIGURE_REF.search(q_text) and not has_image(q):
        flags.append({"flag": "figure_missing", "detail": "stem refers to a figure; no image is attached"})
    if len(s_text) < 15:
        flags.append({"flag": "solution_thin", "detail": "solution is empty or a stub"})
    return flags


def comment_flags(comment):
    """What we can say about a comment before any model reads it."""
    c = (comment or "").strip()
    flags = []
    if INJECTION.search(c):
        flags.append("injection")
    letters = re.sub(r"[^a-z]", "", c.lower())
    no_vowels = bool(letters) and not re.search(r"[aeiou]", letters)
    if len(c) < 3 or no_vowels or re.fullmatch(r"(?:asdf\w*|qwer\w*|zxcv\w*|[.?!\-_ ]+)", c.lower()):
        flags.append("gibberish")
    return flags


def fixed_since(q, reported_at):
    """errorHistory entries made by a human after this report was filed."""
    return [h for h in (q.get("errorHistory") or []) if h.get("at", "") > reported_at]

"""Turn Acadza's production HTML + inline MathML into text a model (and a guard) can reason over.

The HTML is messy on purpose (unclosed spans, options inline in the stem), so this is a
tolerant tree builder, not a strict parser.
"""
import html
import re
from html.parser import HTMLParser

VOID = {"br", "img", "hr", "mspace"}


class _Node:
    def __init__(self, tag, attrs=None):
        self.tag, self.attrs, self.kids = tag, dict(attrs or []), []


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self.stack[-1].kids.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].kids.append(_Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].kids.append(data)


def _kids(node):
    return [k for k in node.kids if not (isinstance(k, str) and not k.strip())]


def _wrap(s):
    s = s.strip()
    return s if re.fullmatch(r"[\w.]+", s) else "(" + s + ")"


def _math(node):
    if isinstance(node, str):
        return node.strip()
    k = _kids(node)
    t = node.tag
    if t == "mfrac" and len(k) == 2:
        return _wrap(_math(k[0])) + "/" + _wrap(_math(k[1]))
    if t == "msup" and len(k) == 2:
        return _math(k[0]) + "^" + _wrap(_math(k[1]))
    if t == "msub" and len(k) == 2:
        return _math(k[0]) + "_" + _wrap(_math(k[1]))
    if t == "msubsup" and len(k) == 3:
        return _math(k[0]) + "_" + _wrap(_math(k[1])) + "^" + _wrap(_math(k[2]))
    if t == "msqrt":
        return "sqrt(" + "".join(_math(c) for c in k) + ")"
    if t == "mover" and len(k) == 2:
        return _math(k[0]) + _math(k[1])
    if t in ("mo",):
        return " " + "".join(_math(c) for c in k) + " "
    return "".join(_math(c) for c in k)


def _text(node, out):
    if isinstance(node, str):
        out.append(node)
        return
    if node.tag == "math":
        out.append(" " + re.sub(r"\s+", " ", _math(node)).strip() + " ")
        return
    if node.tag == "br":
        out.append("\n")
        return
    if node.tag == "img":
        out.append(" [image] ")
        return
    if node.tag == "sup":
        inner = []
        for c in node.kids:
            _text(c, inner)
        out.append("^" + "".join(inner))
        return
    for c in node.kids:
        _text(c, out)
    if node.tag in ("h3", "p", "div", "li"):
        out.append("\n")


def linear(markup):
    """HTML/MathML -> readable single-string text. Fractions become (a)/(b), powers a^b."""
    if not markup:
        return ""
    p = _Tree()
    p.feed(markup)
    out = []
    _text(p.root, out)
    s = "".join(out).replace("\u00a0", " ").replace("\u200b", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n\s*", "\n", s)
    return s.strip()


OPTION_MARK = re.compile(r"\(\s*([A-D])\s*\)")


def split_options(question_markup):
    """Return (stem_text, {letter: option_text}) from a question whose options live in its HTML."""
    text = linear(question_markup)
    marks = list(OPTION_MARK.finditer(text))
    # keep only the last run of markers that starts at (A): the stem can legitimately contain "(A)"
    start = None
    for i in range(len(marks) - 1, -1, -1):
        if marks[i].group(1) == "A":
            start = i
            break
    if start is None:
        return text, {}
    marks = marks[start:]
    opts = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        opts[m.group(1)] = text[m.end():end].strip()
    return text[: marks[0].start()].strip(), opts


def numbers(text):
    """Every numeric token, in order. Used by guards to prove a wording-only edit moved no value."""
    return re.findall(r"\d+(?:\.\d+)?", text)


def body(question):
    """The type-specific block that holds question / solution / answer."""
    return question[question["questionType"]]


def has_image(question):
    b = body(question)
    return bool(b.get("quesImages")) or "<img" in (b.get("question") or "")

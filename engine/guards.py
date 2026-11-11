"""Guards: code that stands between a model's proposal and the question bank.

A proposed repair is auto-applied only if every guard passes. Any failure sends it to faculty with the
reason attached. Guards never "fix" a proposal; they only accept or refuse it.
"""
import copy
import re
from collections import Counter

from .checks import EXAM_TAG, question_flags
from .textutil import body, linear, numbers, split_options

WORDING_ONLY = {"spelling", "noise", "exam_reference", "markup_leak"}
THRESHOLD = {"answer_key": 0.9, "type_mismatch": 0.9, "stem_data": 0.8, "option_repair": 0.8,
             "solution_fix": 0.8, "solution_missing": 0.8, "notation": 0.8, "answer_form": 0.75}
DEFAULT_THRESHOLD = 0.7


def norm_answer(a):
    """'A, B, D' / ['A','B','D'] / ['', 'B'] / '2' -> a comparable form."""
    if isinstance(a, list):
        a = ",".join(str(x) for x in a)
    a = str(a).strip()
    letters = re.findall(r"\b[A-D]\b", a)
    if letters and not re.search(r"\d", a):
        return ",".join(sorted(set(letters)))
    try:
        return str(float(a)).rstrip("0").rstrip(".")
    except ValueError:
        return a.lower()


def is_insertion(find, replace):
    """True if `replace` is `find` with text inserted at one point and nothing removed."""
    i = 0
    while i < len(find) and i < len(replace) and find[i] == replace[i]:
        i += 1
    rest = find[i:]
    return replace.endswith(rest) and len(replace) >= len(find)


def apply_edits(q, edits):
    """Return a patched copy. Raises ValueError if an edit does not match the stored record exactly once."""
    q = copy.deepcopy(q)
    for e in edits:
        f = e["field"]
        if f == "questionType":
            if q["questionType"] != e["find"]:
                raise ValueError(f"questionType is {q['questionType']!r}, not {e['find']!r}")
            q[e["replace"]] = q.pop(q["questionType"])   # the body block is stored under its type name
            q["questionType"] = e["replace"]
        elif f == "answer":
            if body(q)["answer"] != e["find"]:
                raise ValueError(f"stored answer is {body(q)['answer']!r}, not {e['find']!r}")
            body(q)["answer"] = e["replace"]
        elif f in ("question", "solution"):
            n = body(q)[f].count(e["find"])
            if n != 1:
                raise ValueError(f"'find' occurs {n} times in {f}; it must occur exactly once")
            body(q)[f] = body(q)[f].replace(e["find"], e["replace"])
        else:
            raise ValueError(f"unknown field {f!r}")
    return q


def check(q, repair, edits, taxonomy, solves=(), confidence=0.0):
    """Run every guard. Returns {"pass": bool, "checks": [{name, ok, detail}], "patched": question|None}."""
    spec = taxonomy["repairs"][repair]
    out = []

    def add(name, ok, detail=""):
        out.append({"name": name, "ok": bool(ok), "detail": detail})

    add("Repair type may be auto-applied", spec["auto"], "" if spec["auto"] else "taxonomy says a human must author this")
    if not spec["auto"]:
        add("No edit proposed for a human-only repair", not edits, "the system may suggest, never write")
        return {"pass": False, "checks": out, "patched": None}

    add("An edit is proposed", bool(edits))
    outside = [e["field"] for e in edits if e["field"] not in spec["fields"]]
    add("Edit stays inside the repair's fields", not outside,
        f"{repair} may touch {spec['fields']}" + (f"; proposal touches {outside}" if outside else ""))

    patched = None
    try:
        patched = apply_edits(q, edits)
        add("'find' matches the stored record exactly once", True)
    except (ValueError, KeyError) as err:
        add("'find' matches the stored record exactly once", False, str(err))
    if patched is None or outside or not edits:
        return {"pass": False, "checks": out, "patched": None}

    b0, b1 = body(q), body(patched)
    stem0, opts0 = split_options(b0["question"])
    stem1, opts1 = split_options(b1["question"])
    qt0, qt1 = linear(b0["question"]), linear(b1["question"])
    st0, st1 = linear(b0["solution"]), linear(b1["solution"])

    if repair in WORDING_ONLY:
        strip = (lambda t: EXAM_TAG.sub("", t)) if repair == "exam_reference" else (lambda t: t)   # the tag's own year may go
        same = numbers(strip(qt0)) == numbers(qt1) and numbers(strip(st0)) == numbers(st1)
        add("No number moved (wording-only repair)", same, "numeric tokens before and after are identical" if same else "a value changed")
        add("Options keep their count", len(opts0) == len(opts1))
        add("Answer key untouched", b0["answer"] == b1["answer"])

    if repair == "answer_form":
        additive = all(is_insertion(e["find"], e["replace"]) for e in edits) and numbers(qt0) == numbers(qt1)
        add("Additive only: nothing removed, no existing value changed", additive)

    if repair == "stem_data":
        new_nums = list((Counter(numbers(qt1)) - Counter(numbers(qt0))).elements())
        backed = all(n in numbers(st0) for n in new_nums)
        add("Every added value is stated in the stored solution", backed and bool(new_nums),
            f"added {new_nums}; solution contains them" if backed else f"added {new_nums}; not found in the solution")
        add("Options and key untouched", opts0 == opts1 and b0["answer"] == b1["answer"])

    if repair == "option_repair":
        add("Stem text unchanged", stem0 == stem1)
        kept = all(opts1.get(l) == t for l, t in opts0.items() if t)
        add("Existing options unchanged", kept)
        vals = [re.sub(r"\s+", "", t).lower() for t in opts1.values()]
        add("All four options present and distinct", len(opts1) == 4 and all(vals) and len(set(vals)) == 4)
        key = b1["answer"]
        if isinstance(key, str) and key in opts0 and opts0[key]:
            add("Keyed option was already present, so marking is unaffected", True)
        else:
            agree = [s for s in solves if s.get("fills_option") == key]
            add("Restored keyed option is backed by the solution and an independent solve", len(agree) >= 1,
                "the blank option is the keyed one, so its content must be proven")

    if repair in ("solution_fix", "solution_missing"):
        add("Question and key untouched", b0["question"] == b1["question"] and b0["answer"] == b1["answer"])
        agree = [s for s in solves if norm_answer(s.get("answer", "")) == norm_answer(b1["answer"])]
        add("Key independently confirmed before touching its solution", len(agree) >= 2, f"{len(agree)} of {len(solves)} solves agree with the key")

    if repair in ("answer_key", "type_mismatch"):
        old, new = norm_answer(b0["answer"]), norm_answer(b1["answer"])
        if old == new:
            add("Format-only change: the keyed letters are the same", True, f"{b0['answer']!r} -> {b1['answer']!r}")
        else:
            agree = [s for s in solves if norm_answer(s.get("answer", "")) == new]
            add("Two independent solves agree on the new key", len(agree) >= 2, f"{len(agree)} of {len(solves)} solves give {new}")
            add("Student's suggested answer was not used as evidence", True, "solvers never see reports")
        add("Question text untouched", repair == "type_mismatch" or b0["question"] == b1["question"])

    new_flags = {f["flag"] for f in question_flags(patched)} - {f["flag"] for f in question_flags(q)}
    add("Patched record passes static checks with no new problem", not new_flags, ", ".join(sorted(new_flags)))
    need = THRESHOLD.get(repair, DEFAULT_THRESHOLD)
    add(f"Confidence {confidence:.2f} meets the bar for {repair} ({need})", confidence >= need)
    return {"pass": all(c["ok"] for c in out), "checks": out, "patched": patched}

"""Report -> Fix pipeline.

    reports ──► group by question ──► static checks ──► read comments (as data)
                                           │
                     blind solve A + independent check B (never see key or comments)
                                           │
                               judge (question-level finding)
                                           │
              code decides: verdict per report ─► guards ─► route ─► student reply

Models propose. Code decides what is applied. See guards.py.
"""
import json
import os
from collections import defaultdict

from . import guards, prompts
from .checks import comment_flags, fixed_since, question_flags
from .textutil import body, linear, split_options

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NON_CONTENT = {"display": "display_issue", "app": "app_issue", "language": "language_mode"}
NO_SIGNAL = {"injection", "gibberish", "vague"}

# "Is a student losing marks on this right now?" drives the order of the faculty queue.
HARM = {
    "answer_key": (100, "every student who answers correctly is marked wrong"),
    "unsound": (95, "no valid answer: nobody can get this right"),
    "type_mismatch": (90, "wrong marking scheme applied, students get negatives"),
    "identical_options": (80, "two options are the same, a correct choice can be marked wrong"),
    "option_repair": (80, "an option is missing or blank"),
    "stem_data": (75, "cannot be solved as written"),
    "diagram": (75, "cannot be solved without the figure"),
    "wrong_question": (70, "question and solution do not belong together"),
    "solution_fix": (50, "students learn a wrong step"),
    "solution_missing": (45, "no usable solution to learn from"),
    "notation": (40, "an expression reads wrongly"),
    "answer_form": (40, "unit or form is ambiguous"),
    "markup_leak": (30, "raw code is visible"),
    "wrong_chapter": (20, "filed in the wrong place"),
    "syllabus": (20, "may be out of syllabus"),
    "spelling": (10, "cosmetic"), "noise": (10, "cosmetic"), "exam_reference": (10, "cosmetic"),
}


def load(name):
    return json.load(open(os.path.join(ROOT, "data", name), encoding="utf-8"))


# ---------------------------------------------------------------- model stages
class Recorded:
    """Replays model-stage outputs captured while building (see PROMPTS.md for how they were produced)."""
    name = "recorded"

    def __init__(self):
        self.j = json.load(open(os.path.join(ROOT, "engine", "recorded", "judgments.json"), encoding="utf-8"))
        path = os.path.join(ROOT, "verify", "numeric_checks.json")
        self.numeric = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}

    def solves(self, q):
        out = []
        a = self.j["solves"].get(q["_id"])
        if a:
            out.append(dict(a, source="blind solve (model)"))
        n = self.numeric.get(q["_id"])
        if n:
            out.append({"answer": n["answer"], "value": str(n["value"]), "working": n["note"],
                        "fills_option": n["answer"], "source": "independent arithmetic (verify/numeric_checks.py)"})
        return out

    def read(self, report):
        return self.j["reads"][report["reportId"]]

    def judge(self, q, reports, flags, solves):
        return self.j["judge"][q["_id"]]

    def reply(self, report, row, evidence, answer, language):
        return self.j["replies"][report["reportId"]]


class Live:
    """Calls the model for every stage. Responses are cached on disk, so re-runs are free."""
    name = "live"

    def __init__(self, taxonomy):
        from . import llm
        self.llm = llm
        self.tax = "\n".join(f"- {k}: fields={v['fields']}, auto={v['auto']}. {v['label']}" for k, v in taxonomy["repairs"].items())

    def solves(self, q):
        user = prompts.SOLVER_USER.format(qtype=q["questionType"], subject=q["subject"], question_text=linear(body(q)["question"]))
        a = self.llm.call_json(prompts.SOLVER_SYSTEM, user)
        b = self.llm.call_json(prompts.SOLVER_B_SYSTEM, user)
        return [dict(a, source="blind solve A"), dict(b, source="blind solve B")]

    def read(self, report):
        return self.llm.call_json(prompts.READER_SYSTEM, prompts.READER_USER.format(comment=report["comment"]), model=self.llm.CHEAP, max_tokens=300)

    def judge(self, q, reports, flags, solves):
        b = body(q)
        user = prompts.JUDGE_USER.format(
            qtype=q["questionType"], subject=q["subject"], chapter=q["chapter"], answer=json.dumps(b["answer"]),
            question_html=b["question"], solution_html=b["solution"], question_text=linear(b["question"]),
            solution_text=linear(b["solution"]), flags=json.dumps(flags),
            solve_a=json.dumps(solves[0]) if solves else "none", solve_b=json.dumps(solves[1]) if len(solves) > 1 else "none",
            history=json.dumps(q.get("errorHistory") or []),
            reports="\n".join(f"- {r['reportId']} ({r['reportedAt']}): <student_comment>{r['comment']}</student_comment>" for r in reports) or "none",
        )
        return self.llm.call_json(prompts.JUDGE_SYSTEM.format(taxonomy=self.tax), user, max_tokens=2500)

    def reply(self, report, row, evidence, answer, language):
        user = prompts.REPLY_USER.format(language=language, verdict=row["verdict"], repair=row["repair"], route=row["route"],
                                         evidence=evidence, answer=answer, comment=report["comment"])
        return self.llm.call_json(prompts.REPLY_SYSTEM, user, model=self.llm.CHEAP, max_tokens=300)["student_reply"]


# ---------------------------------------------------------------- decisions made in code
def report_verdict(report, read, finding, q):
    """Map one report to a taxonomy verdict. The comment's intent matters; its content is never trusted."""
    rid = report["reportId"]
    intent = "injection" if "injection" in comment_flags(report["comment"]) else read.get("intent", "vague")
    if "gibberish" in comment_flags(report["comment"]):
        intent = "gibberish"
    explained = finding.get("reports", {}).get(rid, {}).get("explained", False)
    if finding["status"] == "defect" and explained and intent != "injection":
        return "defect", intent
    if fixed_since(q, report["reportedAt"]) and intent not in NON_CONTENT and intent not in NO_SIGNAL:
        return "already_fixed", intent
    if intent in NON_CONTENT:
        return NON_CONTENT[intent], intent
    if intent in NO_SIGNAL:
        return "not_actionable", intent
    return "no_error", intent


def urgency(repair, route, n_reports, oldest):
    harm, why = HARM.get(repair, (0, "nothing to change"))
    tier = {"faculty_review": 2, "auto_apply": 1, "no_change": 0}[route]
    score = harm * (1 + 0.25 * (n_reports - 1))
    return {"tier": tier, "score": round(score, 1), "harm": harm, "why": why, "oldest": oldest}


def run(mode="recorded"):
    questions, reports, taxonomy = load("questions.json"), load("reports.json"), load("taxonomy.json")
    stage = Recorded() if mode == "recorded" else Live(taxonomy)
    by_q = defaultdict(list)
    for r in sorted(reports, key=lambda r: r["reportedAt"]):
        by_q[r["questionId"]].append(r)

    results, cases, sweep = [], [], []
    for q in questions:
        qid, reps = q["_id"], by_q.get(q["_id"], [])
        flags = question_flags(q)
        solves = stage.solves(q)
        finding = stage.judge(q, reps, flags, solves)
        repair = finding.get("repair") if finding["status"] == "defect" else None
        edits = finding.get("edits") or []
        guard = guards.check(q, repair, edits, taxonomy, solves, finding.get("confidence", 0)) if repair else None

        # defects nobody reported: same guards, but never auto-applied without a report trail
        for other in finding.get("other_defects", []):
            g = guards.check(q, other["repair"], other.get("edits") or [], taxonomy, solves, other.get("confidence", 0))
            pb = body(g["patched"]) if g["patched"] else None
            sweep.append({"questionId": qid, "qid": q.get("qid"), "subject": q["subject"], "chapter": q["chapter"],
                          "questionType": q["questionType"], "stemText": split_options(body(q)["question"])[0][:140],
                          "repair": other["repair"], "edits": other.get("edits") or [], "evidence": other["evidence"],
                          "confidence": other.get("confidence", 0), "guards_pass": g["pass"], "guard_checks": g["checks"],
                          "before": {"question": body(q)["question"], "solution": body(q)["solution"], "answer": body(q)["answer"], "questionType": q["questionType"]},
                          "after": ({"question": pb["question"], "solution": pb["solution"], "answer": pb["answer"],
                                     "questionType": g["patched"]["questionType"]} if pb else None),
                          "harm": HARM.get(other["repair"], (0, ""))[0]})
        if not reps:
            continue

        rows = []
        for r in reps:
            read = stage.read(r)
            verdict, intent = report_verdict(r, read, finding, q)
            per = finding.get("reports", {}).get(r["reportId"], {})
            if verdict == "defect":
                route = "auto_apply" if guard["pass"] else "faculty_review"
                conf = finding.get("confidence", 0)
            else:
                route, conf = "no_change", per.get("confidence", finding.get("ok_confidence", finding.get("confidence", 0.8)))
            evidence = per.get("evidence") or finding["evidence"]
            row = {
                "reportId": r["reportId"], "questionId": qid, "verdict": verdict,
                "repair": repair if verdict == "defect" else None,
                "edit": (edits[0] if edits else None) if verdict == "defect" else None,
                "route": route, "confidence": conf, "evidence": evidence,
            }
            if verdict == "defect" and len(edits) > 1:
                row["edits"] = edits
            answer_now = body(guard["patched"])["answer"] if (guard and guard["patched"] and route == "auto_apply") else body(q)["answer"]
            row["student_reply"] = stage.reply(r, row, evidence, answer_now,
                                              "hinglish" if read.get("language") == "hinglish" else "english")
            rows.append(row)
            results.append(row)

        defect_rows = [x for x in rows if x["verdict"] == "defect"]
        route = defect_rows[0]["route"] if defect_rows else "no_change"
        stem, opts = split_options(body(q)["question"])
        cases.append({
            "questionId": qid, "qid": q.get("qid"), "subject": q["subject"], "chapter": q["chapter"],
            "questionType": q["questionType"], "level": q.get("level"),
            "before": {"question": body(q)["question"], "solution": body(q)["solution"], "answer": body(q)["answer"], "questionType": q["questionType"]},
            "after": ({"question": body(guard["patched"])["question"], "solution": body(guard["patched"])["solution"],
                       "answer": body(guard["patched"])["answer"], "questionType": guard["patched"]["questionType"]}
                      if guard and guard["patched"] else None),
            "stemText": stem[:140], "flags": flags, "solves": solves, "history": q.get("errorHistory") or [],
            "finding": {"status": finding["status"], "repair": repair, "edits": edits, "evidence": finding["evidence"],
                        "faculty_note": finding.get("faculty_note", ""), "confidence": finding.get("confidence", 0)},
            "guard": {"pass": guard["pass"], "checks": guard["checks"]} if guard else None,
            "route": route,
            "urgency": urgency(repair if defect_rows else None, route, len(defect_rows) or len(rows), reps[0]["reportedAt"]),
            "reports": [dict(r, **{k: row[k] for k in ("verdict", "route", "confidence", "evidence", "student_reply")},
                             intent=stage.read(r).get("intent"), flags=comment_flags(r["comment"]))
                        for r, row in zip(reps, rows)],
        })

    results.sort(key=lambda x: x["reportId"])
    cases.sort(key=lambda c: (-c["urgency"]["tier"], -c["urgency"]["score"], c["urgency"]["oldest"]))
    return {"results": results, "cases": cases, "sweep": sweep, "taxonomy": taxonomy, "mode": stage.name}

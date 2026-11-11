# PRODUCT.md

**Who loses most when a question is broken.** Not the student who reports it. That student noticed, and
loses a minute. The one who loses is the student who *doesn't* report: who solved it correctly, was marked
wrong, and concluded "I don't understand this chapter" three weeks before JEE. A wrong key converts correct
understanding into self-doubt, silently, once per attempt, until someone fixes it. So the design optimises
for time-to-fix on mark-affecting defects, not for clearing reports:
the queue is ordered by "is someone losing marks right now" (wrong key, wrong type, no valid option first;
spelling last); reports are grouped by question, because the unit of harm is the question; provable key
fixes are applied without waiting for a person; and a sweep checks questions nobody reported, because
silence is not evidence of health. The second loser is the faculty member reading 60 reports at 10 PM,
most of them from students who are mistaken. The console shows them only what needs a human (6 of 39 questions here).

**What the AI must never auto-apply.**
- *Anything authored.* A new distractor, a figure, a rewritten stem. The system can prove an existing
  answer wrong; it cannot prove a new option is a *good* option.
- *A key change on one opinion,* or on the student's say-so, or to match the stored solution when an
  independent solve disagrees with it. R016 is the case: the solution was the broken part.
- *A value the record does not contain.* Missing data is filled only from the stored solution.
- *Any judgement call about the exam:* syllabus scope, chapter filing, retiring an unsound question.
- *Anything a comment asked for.* Comments choose where to look. They never choose what happens.

The reason is asymmetry. A missed fix leaves one question as broken as it was yesterday. A wrong auto-fix
breaks a question that worked, for every student, with the system's authority behind it, and teaches faculty
to stop trusting the queue.

**One metric for week 1.** *Faculty overturn rate on auto-applied fixes* (auto-fixes undone ÷ auto-fixes
spot-checked). It is the direct measure of whether auto-apply deserves to exist. Above about 2%, tighten the
guards before doing anything else. Read alongside it: median time from first report to fix on mark-affecting
defects, which is what students actually feel.

**One idea beyond the brief: fix the damage, not only the question.** When a key or type is corrected,
the system knows every past attempt that was marked wrong against the old key. Re-mark them, restore the
lost marks, and tell each affected student ("You were right on this one. We had the key wrong. Your score
for the 3 Nov test is now 184."), including the ones who never reported. The same attempt data gives a
detector that needs no reports at all: a question where the top-scoring students converge on one "wrong"
option is very likely a wrong key. Reports become one signal among several, and the students who stayed
silent get their confidence back.

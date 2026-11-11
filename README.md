# Report desk: Acadza "Report → Fix" loop

Turns raw student error reports into safe fixes, and gives faculty a console to review what the system
could not safely decide alone. Built for the Acadza AI Intern build round (the original brief is in `BRIEF.md`).

| | |
|---|---|
| Live console | `ADD-LIVE-URL` |
| Results | [`results.json`](results.json): 44 reports, one row each |
| Bonus | [`unreported_defects.json`](unreported_defects.json): 20 defects nobody reported |
| Prompts and decisions | [`PROMPTS.md`](PROMPTS.md) |
| Product thinking | [`PRODUCT.md`](PRODUCT.md) |

## What it decided

| | Reports | Questions |
|---|---|---|
| Fixed automatically (every guard passed) | 21 | 16 |
| Sent to faculty (system not allowed, or not sure enough) | 6 | 6 |
| No change (student mistaken, display/app/language, already fixed, nothing to act on) | 17 | 17 |

## How it works

```
reports ─► group by question ─► static checks (code) ─► read comment (model, comment is quoted data)
                                      │
            blind solve A + independent check B   (neither sees the key, the solution or the reports)
                                      │
                         judge: one finding per question (model)
                                      │
        code decides ─► verdict per report ─► guards ─► route ─► student reply (model)
```

The rule the whole design hangs on: **models propose, code decides.**

- **The solver is blind.** It gets the question as a student sees it. No key, no stored solution, no student
  comment. A key is changed only when two independent solves agree with each other and disagree with the key.
  The student's suggested answer is never evidence (R004: the student was right that the key was wrong, and
  wrong about the answer).
- **Comments are data.** They are passed inside `<student_comment>` tags to a reader whose only job is to
  classify them. A regex catches instruction-like text before any model sees it (R027), and because solvers
  never see comments, an injected instruction has no path to an edit.
- **Guards are code** (`engine/guards.py`). An edit is auto-applied only if: its field is inside the repair's
  scope in `taxonomy.json`; `find` matches the stored record exactly once; the repair-specific rule holds
  (a spelling fix moves no number, a stem value must appear in the stored solution, an option repair leaves the
  stem alone, a solution fix needs the key independently confirmed first); the patched record passes the
  static checks; and confidence clears the bar for that repair. One failure sends it to faculty with the reason.
- **Reports are grouped by question**, so three students reporting one wrong key produce one decision and
  three replies.
- **A sweep runs on every question**, reported or not. What it finds goes to its own list in the console and
  is never applied without a person.

## Run it

```bash
python3 verify/numeric_checks.py     # independent arithmetic for every computational question
python3 run.py                       # writes results.json, unreported_defects.json, console/data.js
python3 -m unittest discover tests   # 14 tests, mostly adversarial cases against the guards
python3 -m http.server -d console    # open http://localhost:8000
```

No dependencies beyond Python 3.9+. The console is static HTML, CSS and JS with no build step.

### Recorded mode and live mode (please read)

`run.py` has two modes.

- `--mode recorded` (default, and what produced the committed `results.json`): the four model stages
  (blind solve, comment reading, judging, reply writing) are replayed from `engine/recorded/judgments.json`.
  Those outputs were produced by Claude inside the build session, following the prompts in `engine/prompts.py`,
  not by this code calling an API. Everything after them (static checks, grouping, verdict mapping, guards,
  routing, urgency) runs for real on every run. The second "solve" in this mode is plain arithmetic in
  `verify/numeric_checks.py`, which is stricter than a second model opinion.
- `--mode live`: calls a model API for every stage with the same prompts. The provider is chosen with
  `LLM_PROVIDER`: `anthropic` (default, needs `ANTHROPIC_API_KEY`) or `gemini` (needs `GEMINI_API_KEY`;
  Google AI Studio has a free tier). Live output goes to `results.live.json` so it never overwrites the
  committed results; add `--publish` to replace them.
  Responses are cached on disk by content hash, so a re-run costs nothing. Cost is roughly 3 strong-model calls
  per question and 2 cheap-model calls per report. **Live mode has been run on 7 of 39 questions only** (Gemini free tier, 20 requests
  per model per day). The solver and judge matched the recorded decisions on all of them; the reply stage did not,
  which led to reply prompt v2. Details in `PROMPTS.md`.

The deployed console loads the precomputed `console/data.js`. It does not call a model.

## The console

`console/` is the faculty review console. One row per question, ordered by "is a student losing marks on this
right now": things the system may not decide come first, then by harm (wrong key > unanswerable > wrong
solution > cosmetic), then by number of reports, then by age. The button "How the queue is ordered" explains
this in the product.

Each case shows the finding in one sentence, the change in one line, the question rendered before and after
with the edit marked, the safety checks, the independent solves, each student's comment, and the reply that
student will get (editable). Approve, edit and reject are one click or one key (`A`, `E`, `R`; `J`/`K` to move).
Every action is written to an audit log (who, when, what was proposed, what was finally applied, note),
which can be downloaded as JSON.

Decisions and the audit log are stored in the browser (localStorage), which keeps the deployment a static
site with nothing to break for 7 days. The cost is that the log is per device; a shared log needs a small
backend. That trade-off is discussed in `PROMPTS.md`.

## Deploy

Any static host works; the site is the `console/` folder.

- Netlify: drag the `console/` folder onto app.netlify.com/drop, or connect the repo (`netlify.toml` is set).
- Vercel: import the repo (`vercel.json` points at `console/`).
- GitHub Pages serves only `/` or `/docs`, so copy `console/` to `docs/` if you prefer Pages.

## Layout

```
engine/textutil.py   HTML + MathML → text, option splitting
engine/checks.py     static checks on questions and comments (no model)
engine/prompts.py    every product prompt, verbatim
engine/llm.py        API access with on-disk cache
engine/guards.py     the rules an edit must pass to be auto-applied
engine/pipeline.py   orchestration, verdict mapping, routing, urgency
engine/recorded/     recorded model-stage outputs
verify/              independent arithmetic checks
console/             the faculty console (static)
tests/               guard and pipeline tests
```

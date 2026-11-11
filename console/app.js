/* Report desk: faculty review console.
   Static page: reads window.TRIAGE (written by run.py), keeps decisions and the audit log in localStorage.
   Question HTML comes from the question bank and is rendered as-is (it is what students see).
   Student comments are untrusted and are only ever inserted with textContent. */
(function () {
  "use strict";
  const T = window.TRIAGE;
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode: keep in memory */ } },
  };
  let decisions = store.get("desk.decisions", {});
  let audit = store.get("desk.audit", []);
  let actor = store.get("desk.actor", "Faculty");

  const REPAIR_NAME = {
    answer_key: "Answer key is wrong", type_mismatch: "Stored as the wrong question type", stem_data: "A value is missing from the question",
    option_repair: "An option is missing or blank", solution_fix: "Solution is wrong", solution_missing: "Solution is missing",
    notation: "A symbol is garbled", answer_form: "Unit or answer form not stated", markup_leak: "Raw code is showing",
    spelling: "Spelling mistake", noise: "Stray text in the question", exam_reference: "Source tag left in the question",
    identical_options: "Two options are identical", diagram: "Figure is missing", wrong_question: "Question and solution don't match",
    unsound: "No valid answer as written", wrong_chapter: "Filed under the wrong chapter", syllabus: "Possibly out of syllabus",
  };
  const VERDICT_NAME = {
    defect: "Real defect", no_error: "Student was mistaken", display_issue: "Display problem", app_issue: "App problem",
    language_mode: "Language request", already_fixed: "Already fixed", not_actionable: "Nothing to act on",
  };

  /* ---------- build the three groups ---------- */
  const cases = T.cases.map((c) => Object.assign({ kind: "case", id: c.questionId }, c));
  const sweep = T.sweep.map((s, i) => Object.assign({ kind: "sweep", id: "sweep-" + i, route: "sweep", reports: [],
    finding: { status: "defect", repair: s.repair, edits: s.edits, evidence: s.evidence, confidence: s.confidence, faculty_note: "" },
    guard: { pass: s.guards_pass, checks: s.guard_checks }, solves: [], history: [], flags: [] }, s))
    .sort((a, b) => b.harm - a.harm);
  const groups = [
    { key: "faculty_review", title: "Needs your decision", tab: "Waiting for you",
      todo: "The system is not allowed to make this change on its own. Read what it found, check the question, then confirm or dismiss it.",
      items: cases.filter((c) => c.route === "faculty_review") },
    { key: "auto_apply", title: "Fixed automatically", tab: "Live now, spot-check",
      todo: "This fix is already live: it passed every safety check. Compare before and after. Keep it, or undo it if it is wrong.",
      items: cases.filter((c) => c.route === "auto_apply") },
    { key: "sweep", title: "Found by the system", tab: "Nobody reported these",
      todo: "No student reported this. The system's sweep of all questions found it, and nothing has been changed yet. Apply the fix or dismiss it.",
      items: sweep },
    { key: "no_change", title: "No problem found", tab: "Student was mistaken or similar",
      todo: "The question was checked and is correct, so nothing changes. Read the student's report and the reply they will get, then send it or reopen the case.",
      items: cases.filter((c) => c.route === "no_change") },
  ];
  const groupOf = (c) => groups.find((g) => g.key === c.route);
  const order = groups.flatMap((g) => g.items);
  let filter = "all", query = "";
  let startId = "";
  try { startId = (location.hash || "").slice(1); } catch (e) { /* sandboxed preview: no URL access */ }
  let current = (startId && order.find((c) => c.id === startId)) || order[0];

  /* ---------- filtering ---------- */
  function haystack(c) {
    return [headline(c), c.stemText, c.subject, c.chapter, c.qid, c.questionId]
      .concat(c.reports.map((r) => r.comment + " " + r.reportId)).join(" ").toLowerCase();
  }
  function visible() {
    const q = query.trim().toLowerCase();
    return order.filter((c) => (filter === "all" || c.route === filter) && (!q || haystack(c).includes(q)));
  }

  /* ---------- labels ---------- */
  function headline(c) {
    if (c.finding.status === "defect") return REPAIR_NAME[c.finding.repair] || c.finding.repair;
    const v = c.reports[0] ? c.reports[0].verdict : "no_error";
    return VERDICT_NAME[v] || v;
  }
  function verbs(c) {
    const hasEdit = c.finding.edits.length > 0;
    if (c.route === "auto_apply") return { approve: "Keep fix", approveHelp: "Leave the change live",
      reject: "Undo fix", rejectHelp: "Restore the original question", done: "Fix kept", undone: "Fix undone" };
    if (c.route === "no_change") return { approve: "Agree, send reply", approveHelp: "Student gets the reply shown above",
      reject: "Reopen as defect", rejectHelp: "Something is wrong after all", done: "Agreed", undone: "Reopened" };
    if (hasEdit) return { approve: "Apply fix", approveHelp: "Make this change live",
      reject: "Reject fix", rejectHelp: "Leave the question as it is", done: "Fix applied", undone: "Fix rejected" };
    return { approve: "Confirm, I'll fix it", approveHelp: "You handle the change by hand",
      reject: "Not a defect", rejectHelp: "Close with no change", done: "Confirmed", undone: "Dismissed" };
  }
  function confidenceWord(p) { return p >= 90 ? ["High", "conf-high"] : p >= 75 ? ["Medium", "conf-mid"] : ["Low", "conf-low"]; }
  const when = (iso) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const ansText = (a) => (Array.isArray(a) ? "[" + a.map((x) => (x === "" ? "empty" : x)).join(" | ") + "]" : String(a));

  /* ---------- diff marking ---------- */
  function snapBack(s, i) {           // do not cut inside a tag or an entity
    for (;;) {
      if (i <= 0) return 0;
      const lt = s.lastIndexOf("<", i - 1), gt = s.lastIndexOf(">", i - 1);
      if (lt > gt) { i = lt; continue; }
      const amp = s.lastIndexOf("&", i - 1), semi = s.lastIndexOf(";", i - 1);
      if (amp > semi && i - amp < 10 && /^&[#\w]*$/.test(s.slice(amp, i))) { i = amp; continue; }
      return i;
    }
  }
  function snapFwd(s, i) {
    if (i <= 0) return 0;
    const lt = s.lastIndexOf("<", i - 1), gt = s.lastIndexOf(">", i - 1);
    if (lt > gt) { const e = s.indexOf(">", i); return e < 0 ? s.length : e + 1; }
    const amp = s.lastIndexOf("&", i - 1), semi = s.lastIndexOf(";", i - 1);
    if (amp > semi && /^&[#\w]*$/.test(s.slice(amp, i))) { const e = s.indexOf(";", i); return e < 0 ? i : e + 1; }
    return i;
  }
  function balanced(h) {
    const voids = /^(br|img|hr|mspace)$/i, stack = [];
    const re = /<\/?([a-zA-Z0-9]+)[^>]*?(\/?)>/g;
    let m;
    while ((m = re.exec(h))) {
      if (m[2] === "/" || voids.test(m[1])) continue;
      if (m[0][1] === "/") { if (stack.pop() !== m[1].toLowerCase()) return false; } else stack.push(m[1].toLowerCase());
    }
    return stack.length === 0;
  }
  function splitEdit(find, replace) {
    if (!/[<&]/.test(find + replace) && find && replace) return { pre: "", suf: "", del: find, ins: replace };
    let p = 0;
    while (p < find.length && p < replace.length && find[p] === replace[p]) p++;
    p = Math.min(snapBack(find, p), snapBack(replace, p));
    let s = 0;
    while (s < find.length - p && s < replace.length - p && find[find.length - 1 - s] === replace[replace.length - 1 - s]) s++;
    let cutF = snapFwd(find, find.length - s), cutR = snapFwd(replace, replace.length - s);
    s = Math.min(find.length - cutF, replace.length - cutR);
    const out = { pre: find.slice(0, p), suf: find.slice(find.length - s), del: find.slice(p, find.length - s), ins: replace.slice(p, replace.length - s) };
    return balanced(out.del) && balanced(out.ins) ? out : null;
  }
  /* returns {before, after, marked} HTML for one field */
  function markField(html, edits) {
    let before = html, after = html, marked = true;
    for (const e of edits) {
      const parts = splitEdit(e.find, e.replace);
      if (!parts) { marked = false; after = after.replace(e.find, () => e.replace); continue; }
      const inMath = (() => { const i = html.indexOf(e.find); return html.lastIndexOf("<math", i) > html.lastIndexOf("</math>", i); })();
      const D = inMath ? ["<mrow class=\"d-del\">", "</mrow>"] : ["<del class=\"d-del\">", "</del>"];
      const I = inMath ? ["<mrow class=\"d-ins\">", "</mrow>"] : ["<ins class=\"d-ins\">", "</ins>"];
      const gone = "<span class=\"d-gap\" title=\"Removed here\"></span>", came = "<span class=\"d-gap d-gap-in\" title=\"Added here\"></span>";
      before = before.replace(e.find, () => parts.pre + (parts.del ? D[0] + parts.del + D[1] : (inMath ? "" : came)) + parts.suf);
      after = after.replace(e.find, () => parts.pre + (parts.ins ? I[0] + parts.ins + I[1] : (inMath ? "" : gone)) + parts.suf);
    }
    return { before, after, marked };
  }
  /* word-level summary of what changed, from rendered text */
  function words(html) {
    const d = document.createElement("div");
    d.innerHTML = html.replace(/<br\s*\/?>/gi, " ").replace(/<\/(h3|p|div|math)>/gi, " </$1>");
    return d.textContent.replace(/\s+/g, " ").trim().split(" ");
  }
  function wordDiff(a, b) {
    let p = 0;
    while (p < a.length && p < b.length && a[p] === b[p]) p++;
    let s = 0;
    while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s++;
    return { removed: a.slice(p, a.length - s).join(" "), added: b.slice(p, b.length - s).join(" ") };
  }

  /* ---------- queue ---------- */
  function renderTabs() {
    const t = $("#tabs");
    t.textContent = "";
    for (const g of groups) {
      const left = g.items.filter((c) => !decisions[c.id]).length;
      const b = el("button", "tab c-" + g.key);
      b.type = "button";
      b.setAttribute("aria-pressed", String(filter === g.key));
      b.title = filter === g.key ? "Show all groups" : "Show only: " + g.title;
      b.append(el("span", "tab-n", String(left)), el("span", "tab-t", g.title),
        el("span", "tab-s", left === g.items.length ? g.tab : (g.items.length - left) + " of " + g.items.length + " done"));
      b.addEventListener("click", () => {
        filter = filter === g.key ? "all" : g.key;
        const v = visible();
        if (v.length && !v.includes(current)) current = v[0];
        renderAll();
      });
      t.append(b);
    }
  }
  function renderGuide() {
    const g = $("#guide");
    g.textContent = "";
    if (store.get("desk.guideSeen", false)) return;
    const box = el("div", "guide");
    box.append(el("strong", null, "New here? Three steps:"));
    const ol = el("ol");
    ["Pick a question below. Amber ones are waiting for you.", "Read the case top to bottom: what was found, the change, the question.",
      "Decide with the buttons at the bottom. Everything is logged and can be undone."].forEach((s) => ol.append(el("li", null, s)));
    const ok = el("button", "ghost", "Got it");
    ok.type = "button";
    ok.addEventListener("click", () => { store.set("desk.guideSeen", true); renderGuide(); });
    box.append(ol, ok);
    g.append(box);
  }
  function renderQueue() {
    renderTabs();
    const q = $("#queue");
    q.textContent = "";
    const vis = visible();
    if (!vis.length) q.append(el("p", "q-empty", query ? "No questions match “" + query + "”." : "Nothing in this group."));
    for (const g of groups) {
      const items = g.items.filter((c) => vis.includes(c));
      if (!items.length) continue;
      const sec = el("section", "q-group q-" + g.key + " c-" + g.key);
      const done = items.filter((c) => decisions[c.id]).length;
      const head = el("header", "q-head");
      head.append(el("span", "dot dot-" + g.key), el("h2", null, g.title), el("span", "q-count", done ? done + " of " + items.length + " done" : String(items.length)));
      sec.append(head);
      const list = el("ol", "q-list");
      for (const c of items) {
        const li = el("li");
        const b = el("button", "q-item" + (c === current ? " is-current" : "") + (decisions[c.id] ? " is-done" : ""));
        b.type = "button";
        b.dataset.id = c.id;
        if (c === current) b.setAttribute("aria-current", "true");
        const top = el("span", "q-line");
        top.append(el("span", "q-what", headline(c)));
        const n = c.reports.length;
        if (n > 1) top.append(el("span", "q-n", n + " reports"));
        b.append(top, el("span", "q-stem", c.stemText || ""));
        const meta = el("span", "q-meta", c.subject + ", " + c.chapter);
        b.append(meta);
        if (decisions[c.id]) b.append(el("span", "q-state q-state-" + decisions[c.id].action, "✓ " + decisions[c.id].label));
        b.addEventListener("click", () => select(c));
        li.append(b);
        list.append(li);
      }
      sec.append(list);
      q.append(sec);
    }
    const need = groups[0].items.filter((c) => !decisions[c.id]).length;
    const reports = cases.reduce((n, c) => n + c.reports.length, 0);
    $("#bar-sub").textContent = reports + " student reports on " + cases.length + " questions. " + (need
      ? need + (need === 1 ? " question is" : " questions are") + " waiting for your decision."
      : "Nothing is waiting on you.");
    $("#audit-count").textContent = audit.length ? "(" + audit.length + ")" : "";
  }
  function renderAll() { renderQueue(); renderCase(); }

  /* ---------- case detail ---------- */
  function sheet(title, part, c, side) {
    const box = el("div", "sheet sheet-" + side);
    box.append(el("div", "sheet-tab", title));
    const stateOf = side === "before" ? c.before : (c.after || c.before);
    const qEdits = c.finding.edits.filter((e) => e.field === "question"), sEdits = c.finding.edits.filter((e) => e.field === "solution");
    const qm = markField(c.before.question, qEdits), sm = markField(c.before.solution, sEdits);
    const qh = el("div", "paper-q");
    qh.innerHTML = side === "before" ? qm.before : (c.after ? qm.after : c.before.question);
    box.append(qh);
    const key = el("p", "paper-key");
    const changedKey = c.after && JSON.stringify(c.after.answer) !== JSON.stringify(c.before.answer);
    const changedType = c.after && c.after.questionType !== c.before.questionType;
    key.append(el("span", "k-label", "Answer key "));
    key.append(el("span", "k-val" + (changedKey ? (side === "before" ? " d-del d-short" : " d-ins") : ""), ansText(stateOf.answer)));
    key.append(el("span", "k-label", "  Type "));
    key.append(el("span", "k-val" + (changedType ? (side === "before" ? " d-del d-short" : " d-ins") : ""), ({ scq: "single correct", mcq: "multiple correct", integerQuestion: "integer" })[stateOf.questionType]));
    box.append(key);
    const sol = el("details", "paper-sol");
    sol.open = sEdits.length > 0 || ["answer_key", "stem_data", "option_repair", "unsound"].includes(c.finding.repair);
    sol.append(el("summary", null, "Solution"));
    const sh = el("div", "paper-s");
    sh.innerHTML = side === "before" ? sm.before : (c.after ? sm.after : c.before.solution);
    sol.append(sh);
    box.append(sol);
    return box;
  }

  function changeLine(c) {
    const wrap = el("div", "change");
    const edits = c.finding.edits;
    if (!edits.length) {
      wrap.classList.add("change-none");
      wrap.append(el("p", "change-main", c.finding.status === "defect" ? "No edit proposed. This one needs a person." : "No change to the question."));
      if (c.finding.faculty_note) wrap.append(el("p", "change-note", c.finding.faculty_note));
      return wrap;
    }
    for (const e of edits) {
      const row = el("p", "change-main");
      if (e.field === "answer" || e.field === "questionType") {
        row.append(el("span", "change-field", e.field === "answer" ? "Answer key" : "Question type"));
        row.append(el("del", "d-del d-short", ansText(e.find)), el("span", "arrow", " becomes "), el("ins", "d-ins", ansText(e.replace)));
      } else {
        const d = wordDiff(words(e.find), words(e.replace));
        const whole = e.find.length > 400;
        row.append(el("span", "change-field", e.field === "question" ? "Question" : "Solution"));
        if (whole) row.append(el("span", null, "rewritten in full, see below"));
        else {
          if (d.removed) row.append(el("del", "d-del", d.removed));
          if (d.removed && d.added) row.append(el("span", "arrow", " becomes "));
          if (d.added) row.append(el("ins", "d-ins", d.added));
          if (!d.removed && !d.added) row.append(el("span", null, "markup only, the wording is the same"));
          else if (!d.added) row.append(el("span", "arrow", " removed"));
          else if (!d.removed) row.append(el("span", "arrow", " added"));
        }
      }
      wrap.append(row);
    }
    return wrap;
  }

  function step(n, title, sub) {
    const s = el("section", "step");
    const h = el("h3", "step-h");
    h.append(el("span", "num", String(n)), el("span", null, title));
    if (sub) h.append(el("span", "step-sub", sub));
    s.append(h);
    return s;
  }

  function renderCase() {
    const m = $("#case");
    m.textContent = "";
    const c = current;
    if (!c) { m.append(el("p", "q-empty", "Pick a question on the left.")); return; }
    const v = verbs(c), dec = decisions[c.id], g = groupOf(c);
    m.className = "case c-" + c.route;

    /* header */
    const head = el("header", "case-head");
    const top = el("div", "case-top");
    const pill = el("span", "pill");
    pill.append(el("span", "dot dot-" + c.route), el("span", null, g.title));
    const n = c.reports.length;
    top.append(pill, el("span", "case-meta", c.subject + " · " + c.chapter + (c.qid ? " · " + c.qid : "") + " · " +
      (n ? n + (n === 1 ? " report" : " reports") + ", first on " + when(c.reports[0].reportedAt) : "no student reported this")));
    head.append(top, el("h2", null, headline(c)));
    m.append(head);

    /* what to do, or what was decided */
    if (dec) {
      const done = el("div", "todo todo-done" + (dec.action === "reject" ? " is-reject" : ""));
      const p = el("p");
      p.append(el("strong", null, "✓ " + dec.label), el("span", null, " by " + dec.actor + ", " + when(dec.at) + ". Logged in the audit log."));
      const undo = el("button", "ghost", "Undo decision");
      undo.type = "button";
      undo.addEventListener("click", undoDecision);
      done.append(p, undo);
      m.append(done);
    } else {
      const todo = el("p", "todo");
      todo.append(el("strong", null, "What to do: "), el("span", null, g.todo));
      m.append(todo);
    }

    /* 1. finding */
    const s1 = step(1, c.finding.status === "defect" ? "What the system found" : "What the system checked");
    s1.append(el("p", "why-text", c.finding.evidence));
    const facts = el("div", "facts");
    const pct = Math.round(c.finding.confidence * 100), cwc = confidenceWord(pct);
    const f1 = el("span", "fact " + cwc[1]);
    f1.append(el("span", null, "Confidence "), el("b", null, cwc[0] + " (" + pct + "%)"));
    facts.append(f1);
    if (c.urgency && c.finding.status === "defect") {
      const f2 = el("span", "fact");
      f2.append(el("span", null, "Why it matters: "), el("b", null, c.urgency.why));
      facts.append(f2);
    }
    if (c.guard) {
      const f3 = el("span", "fact");
      f3.append(el("span", null, "Safety checks: "), el("b", null, c.guard.pass ? "all passed" : "did not all pass"));
      facts.append(f3);
    }
    s1.append(facts);
    m.append(s1);

    /* 2. change */
    const s2 = step(2, c.finding.edits.length ? "The change, in one line" : "The change");
    s2.append(changeLine(c));
    m.append(s2);

    /* 3. question */
    const s3 = step(3, c.after ? "Check it on the question" : "The question as students see it");
    if (c.after) {
      const lg = el("p", "legend");
      lg.append(el("del", "d-del", "red"), el("span", null, " is removed, "), el("ins", "d-ins", "green"), el("span", null, " is added. Open “Solution” to see it there too."));
      s3.append(lg);
    }
    const pair = el("div", "pair" + (c.after ? "" : " pair-single"));
    if (c.after) pair.append(sheet("Before", null, c, "before"), sheet(c.route === "auto_apply" ? "After (live now)" : "After (proposed)", null, c, "after"));
    else pair.append(sheet("As stored", null, c, "before"));
    s3.append(pair);
    m.append(s3);

    /* 4. reports + replies */
    let k = 4;
    if (c.reports.length) {
      const s4 = step(k++, c.reports.length === 1 ? "What the student said, and our reply" : "What the students said, and our replies", "You can edit a reply before deciding");
      for (const r of c.reports) {
        const row = el("div", "rep");
        const said = el("div", "rep-said");
        said.append(el("p", "rep-meta", "Student wrote"));
        said.append(el("blockquote", "rep-comment", r.comment));            // textContent: untrusted
        said.append(el("p", "rep-sub", r.reportId + " · " + r.source + " · " + when(r.reportedAt)));
        said.append(el("p", "rep-verdict v-" + r.verdict, "Verdict: " + VERDICT_NAME[r.verdict]));
        if (r.flags.includes("injection")) said.append(el("p", "rep-flag", "⚠ This comment tries to give the system orders. It was ignored and nothing was changed because of it."));
        if (r.evidence !== c.finding.evidence) said.append(el("p", "rep-why", r.evidence));
        const reply = el("div", "rep-reply");
        reply.append(el("p", "rep-meta", "Reply the student will get"));
        const ta = el("textarea");
        ta.value = (dec && dec.replies && dec.replies[r.reportId]) || r.student_reply;
        ta.rows = 4;
        ta.dataset.rid = r.reportId;
        ta.setAttribute("aria-label", "Reply to student for " + r.reportId);
        reply.append(ta);
        row.append(said, reply);
        s4.append(row);
      }
      m.append(s4);
    }

    /* 5. how it was checked */
    const proof = el("details", "step proof");
    const sum = el("summary", "step-h");
    sum.append(el("span", "num", String(k)), el("span", null, c.guard && !c.guard.pass && c.finding.edits.length ? "Why this was not applied automatically" : "How this was checked"));
    proof.append(sum);
    if (c.guard) {
      proof.append(el("h4", null, c.guard.pass ? "Safety checks (all " + c.guard.checks.length + " passed)" : "Safety checks"));
      const ul = el("ul", "checks");
      for (const ck of c.guard.checks) {
        const li = el("li", ck.ok ? "ok" : "bad");
        li.append(el("span", "mark", ck.ok ? "pass" : "stop"), el("span", null, ck.name + (ck.detail ? ": " + ck.detail : "")));
        ul.append(li);
      }
      proof.append(ul);
    }
    if (c.solves.length) {
      proof.append(el("h4", null, "Independent solves (done without seeing the key or the reports)"));
      const ul = el("ul", "solves");
      for (const s of c.solves) {
        const li = el("li");
        li.append(el("strong", null, s.source + ": " + s.answer + " "), el("span", null, s.working || ""));
        ul.append(li);
      }
      proof.append(ul);
    }
    if (c.flags.length) proof.append(el("p", "proof-flags", "Automatic checks flagged: " + c.flags.map((f) => f.detail).join("; ") + "."));
    if (c.history.length) proof.append(el("p", "proof-flags", "Edit history: " + c.history.map((h) => when(h.at) + ", " + h.actor + ", " + h.note).join("; ") + "."));
    if (!c.guard && !c.solves.length && !c.flags.length && !c.history.length) proof.append(el("p", "proof-flags", "No further checks recorded for this case."));
    proof.open = !!(c.guard && !c.guard.pass && c.finding.edits.length > 0);
    m.append(proof);

    /* editor (hidden until Edit) */
    const editor = el("section", "step editor");
    editor.hidden = true;
    editor.id = "editor";
    const eh = el("h3", "step-h");
    eh.append(el("span", null, c.finding.edits.length ? "Edit the fix before applying it" : "Add a note for the audit log"));
    editor.append(eh);
    c.finding.edits.forEach((e, i) => {
      const lab = el("label", null, (e.field === "answer" ? "New answer key" : e.field === "questionType" ? "New question type" : "Replace with (" + e.field + " HTML)"));
      const ta = el("textarea", "mono");
      ta.rows = typeof e.replace === "string" && e.replace.length > 120 ? 6 : 2;
      ta.value = typeof e.replace === "string" ? e.replace : JSON.stringify(e.replace);
      ta.dataset.edit = i;
      lab.append(ta);
      editor.append(lab);
    });
    const noteL = el("label", null, "Note for the audit log (optional)");
    const note = el("textarea");
    note.rows = 2;
    note.id = "note";
    noteL.append(note);
    editor.append(noteL);
    const save = el("button", "primary", "Save and " + v.approve.toLowerCase());
    save.type = "button";
    save.addEventListener("click", () => decide("edit"));
    editor.append(save);
    m.append(editor);

    /* action bar */
    const bar = el("footer", "actions");
    const btn = (cls, label, help, key, fn) => {
      const b = el("button", "act " + cls);
      b.type = "button";
      const t = el("b", null, label);
      if (key) t.append(el("kbd", null, key));
      b.append(t, el("small", null, help));
      b.addEventListener("click", fn);
      return b;
    };
    if (dec) {
      bar.append(btn("act-edit", "Undo decision", "Put this case back in the queue", "U", undoDecision));
    } else {
      bar.append(btn("act-approve", v.approve, v.approveHelp, "A", () => decide("approve")),
        btn("act-edit", "Edit first", "Change the fix or add a note", "E", openEditor),
        btn("act-reject", v.reject, v.rejectHelp, "R", () => decide("reject")));
    }
    const vis = visible(), i = vis.indexOf(c);
    const nav = el("div", "nav");
    const prev = el("button", "ghost", "← Previous"), next = el("button", "ghost", "Next →");
    [prev, next].forEach((b) => (b.type = "button"));
    prev.disabled = i <= 0; next.disabled = i < 0 || i >= vis.length - 1;
    prev.addEventListener("click", () => { if (i > 0) select(vis[i - 1]); });
    next.addEventListener("click", () => { if (i < vis.length - 1) select(vis[i + 1]); });
    nav.append(prev, el("span", null, (i < 0 ? "-" : i + 1) + " of " + vis.length), next);
    bar.append(nav);
    m.append(bar);
    m.scrollTop = 0;
    window.scrollTo({ top: 0 });
  }

  /* ---------- actions + audit ---------- */
  function openEditor() {
    const ed = $("#editor");
    ed.hidden = false;
    ed.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    const first = $("textarea", ed);
    if (first) first.focus();
  }
  function decide(action) {
    const c = current, v = verbs(c);
    const replies = {};
    document.querySelectorAll(".rep-reply textarea").forEach((t) => { if (t.value !== (c.reports.find((r) => r.reportId === t.dataset.rid) || {}).student_reply) replies[t.dataset.rid] = t.value; });
    let edits = c.finding.edits;
    if (action === "edit") {
      edits = c.finding.edits.map((e, i) => {
        const t = document.querySelector('#editor textarea[data-edit="' + i + '"]');
        let val = t ? t.value : e.replace;
        if (t && typeof e.replace !== "string") { try { val = JSON.parse(t.value); } catch (err) { val = t.value; } }
        return Object.assign({}, e, { replace: val });
      });
    }
    const note = ($("#note") || {}).value || "";
    const label = action === "reject" ? v.undone : action === "edit" ? "Edited, " + v.done.toLowerCase() : v.done;
    const entry = {
      at: new Date().toISOString(), actor: actor || "Faculty", action, label, questionId: c.questionId, item: c.id,
      repair: c.finding.repair, systemRoute: c.route, reports: c.reports.map((r) => r.reportId),
      proposedEdits: c.finding.edits, finalEdits: action === "reject" ? [] : edits,
      editedReplies: replies, note,
    };
    audit.unshift(entry);
    decisions[c.id] = { action, label, at: entry.at, actor: entry.actor, replies };
    persist();
    toast(label + ". Logged.");
    // Move on to the next case still waiting, preferring the same group, within the current filter.
    const vis = visible(), after = vis.slice(vis.indexOf(c) + 1);
    const next = after.find((x) => !decisions[x.id] && x.route === c.route) || after.find((x) => !decisions[x.id]) || after[0] || c;
    select(next);
  }
  function undoDecision() {
    const c = current, d = decisions[c.id];
    if (!d) return;
    audit.unshift({ at: new Date().toISOString(), actor: actor || "Faculty", action: "undo", label: "Undid: " + d.label, questionId: c.questionId, item: c.id, reports: c.reports.map((r) => r.reportId) });
    delete decisions[c.id];
    persist();
    toast("Decision undone. Logged.");
    renderQueue(); renderCase();
  }
  function persist() { store.set("desk.decisions", decisions); store.set("desk.audit", audit); }
  function select(c) {
    current = c;
    // Deep link to the case. Sandboxed previews (srcdoc/blob frames) refuse URL changes; the console works without it.
    try { history.replaceState(null, "", "#" + c.id); } catch (e) { /* ignore */ }
    renderQueue(); renderCase();
    const b = document.querySelector(".q-item.is-current");
    if (b) b.scrollIntoView({ block: "nearest" });
  }
  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
  }
  function renderAudit() {
    const ol = $("#audit-list");
    ol.textContent = "";
    if (!audit.length) { ol.append(el("li", "empty", "No decisions yet. Approve, edit or reject a case and it will be listed here.")); return; }
    for (const a of audit) {
      const li = el("li");
      li.append(el("strong", null, a.label), el("span", null, "  " + a.actor + ", " + when(a.at)));
      li.append(el("p", null, "Question " + a.questionId + (a.reports && a.reports.length ? "  |  " + a.reports.join(", ") : "") + (a.repair ? "  |  " + a.repair : "")));
      if (a.finalEdits && a.finalEdits.length) li.append(el("p", "mono", a.finalEdits.map((e) => e.field + ": " + (typeof e.find === "string" && e.find.length > 60 ? e.find.slice(0, 60) + "..." : ansText(e.find)) + "  ->  " + (typeof e.replace === "string" && e.replace.length > 60 ? e.replace.slice(0, 60) + "..." : ansText(e.replace))).join("\n")));
      if (a.note) li.append(el("p", "note", "Note: " + a.note));
      ol.append(li);
    }
  }

  /* ---------- wiring ---------- */
  $("#actor").value = actor;
  $("#actor").addEventListener("input", (e) => { actor = e.target.value.trim(); store.set("desk.actor", actor); });
  $("#open-audit").addEventListener("click", () => { renderAudit(); $("#audit").hidden = false; $("#close-audit").focus(); });
  $("#close-audit").addEventListener("click", () => { $("#audit").hidden = true; $("#open-audit").focus(); });
  $("#export-audit").addEventListener("click", () => {
    try {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(audit, null, 1)], { type: "application/json" }));
      a.download = "audit-log.json";
      a.click();
    } catch (e) { toast("Download is blocked in this preview. Open the console in its own tab."); }
  });
  $("#open-help").addEventListener("click", () => { const d = $("#help"); try { d.showModal(); } catch (e) { d.setAttribute("open", ""); } });
  $("#search").addEventListener("input", (e) => {
    query = e.target.value;
    const v = visible();
    if (v.length && !v.includes(current)) current = v[0];
    renderAll();
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
    if ($("#help").open) return;
    const vis = visible(), k = e.key.toLowerCase(), i = vis.indexOf(current);
    if (k === "escape" && !$("#audit").hidden) { $("#audit").hidden = true; return; }
    if (k === "/") { e.preventDefault(); $("#search").focus(); return; }
    if (k === "j" && i < vis.length - 1) select(vis[i + 1]);
    else if (k === "k" && i > 0) select(vis[i - 1]);
    else if (!decisions[current.id] && k === "a") decide("approve");
    else if (!decisions[current.id] && k === "r") decide("reject");
    else if (!decisions[current.id] && k === "e") { e.preventDefault(); openEditor(); }
    else if (decisions[current.id] && k === "u") undoDecision();
  });
  // A plain button, not a form: sandboxed previews block form submission, which left the dialog stuck open.
  $("#close-help").addEventListener("click", () => { const d = $("#help"); try { d.close(); } catch (e) { /* not modal */ } d.removeAttribute("open"); });
  window.addEventListener("hashchange", () => {
    let id = "";
    try { id = (location.hash || "").slice(1); } catch (e) { return; }
    const c = order.find((x) => x.id === id);
    if (c && c !== current) select(c);
  });
  renderGuide();
  renderAll();
})();

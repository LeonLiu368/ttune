// Experiments and tasks: the sections that tie runs to the tasks they scored (data from viewer/explore.py).
//   viewExperiments()            every experiment, with its headline numbers
//   viewExperiment(id)           summary, leaderboard, and a searchable task x run grid
//   viewTasks(experiment)        every task, searchable, with its results in each run
//   viewTask(task, run, tab)     the task's files (PDFs rendered) beside one trial: summary, answer, trajectory
// Uses the helpers in app.js. Model output and trajectories are untrusted: always text, never HTML.
"use strict";

const STATUSES = [["pass", "Pass"], ["partial", "Partial"], ["fail", "Fail"], ["error", "Error"], ["skipped", "Not run"]];
const STATUS_NOTE = { pass: "reward 1.00", partial: "reward above 0, below 1", fail: "reward 0", error: "never reached the verifier", skipped: "not run" };
const SPLITS = { "holdout-id": "Holdout, typical (ID)", "holdout-ood": "Holdout, unusual (OOD)", train: "Train (private)", validation: "Validation (private)" };
const ISSUES = { name_variant: "name written two ways", rent_mismatch: "rent disagrees with the lease", stale_stub: "stale pay stub",
  partner_moved_out: "partner moved out", missing_lease_page: "missing lease page", missing_childcare_receipt: "missing childcare receipt",
  missing_income_doc: "missing pay stubs" };

const enc = encodeURIComponent;
const short = (id) => id.replace(/^benefits-/, "");
function runLabel(r) {
  const model = (r.model || r.run_id).replace(/^local\//, "");
  return r.base ? `${model} (from ${r.base})` : model;
}
function square(c, attrs) {
  const status = c ? c.status : "none";
  const title = c ? `${STATUS_NOTE[status] || status}${c.reward !== undefined ? ` · reward ${num(c.reward)}` : ""}${c.malformed ? " · malformed" : ""}` : "not in this run";
  return h(attrs && attrs.href ? "a" : "span", { class: `sq sq-${status}`, title, "aria-label": title, ...attrs },
    status === "pass" ? "✓" : status === "fail" ? "✕" : status === "partial" ? "~" : status === "error" ? "!" : "");
}
function stackBar(counts, total) {
  return h("div", { class: "stack", role: "img", "aria-label": STATUSES.map(([k, l]) => `${counts[k] || 0} ${l.toLowerCase()}`).join(", ") },
    STATUSES.map(([k]) => (counts[k] ? h("span", { class: `seg seg-${k}`, style: `flex-grow:${counts[k]}` }) : null)),
    total > STATUSES.reduce((n, [k]) => n + (counts[k] || 0), 0) ? h("span", { class: "seg", style: "flex-grow:0" }) : null);
}
const legend = (counts) => h("ul", { class: "legend" }, STATUSES.map(([k, l]) =>
  h("li", {}, h("span", { class: `dot seg-${k}` }), `${counts[k] || 0} ${l.toLowerCase()}`)));
function terms(text) {
  return text.toLowerCase().split(",").map((t) => t.trim()).filter(Boolean);
}
function matches(haystack, q) {
  const list = terms(q);
  return !list.length || list.some((t) => haystack.includes(t));
}
function copyTSV(button, header, rows) {
  const text = [header, ...rows].map((r) => r.map((v) => String(v ?? "").replace(/[\t\n]/g, " ")).join("\t")).join("\n");
  navigator.clipboard.writeText(text).then(() => { button.textContent = "Copied"; setTimeout(() => { button.textContent = "Copy TSV"; }, 1500); },
    () => { button.textContent = "Couldn't copy"; });
}
function chips(list, cls) {
  return list.map((t) => h("span", { class: cls ? `chip ${cls}` : "chip" }, t));
}
function familyChips(t) {
  return [t.shift && t.shift !== "none" ? h("span", { class: "chip" }, FAMILIES[t.shift] || t.shift) : null, chips(t.twists || [])];
}

// --- experiments --------------------------------------------------------------------------------

async function viewExperiments() {
  const list = await getJSON("data/experiments.json");
  show(
    h("section", {}, h("div", { class: "head" }, h("h1", {}, "Experiments"),
      h("p", {}, "An experiment groups runs that worked the same way on the same 400 holdout tasks (200 typical, 200 unusual households), so they rank side by side. Open one for its leaderboard and every task's result; open a task for its documents and the agent's turns."))),
    list.length ? h("div", { class: "exp-list" }, list.map((e) => {
      const href = `#/experiment/${enc(e.id)}`;
      return h("a", { class: "card exp-card", href },
        h("div", { class: "exp-card-head" }, h("h2", {}, e.title), h("span", { class: "mono muted" }, e.id)),
        e.description ? h("p", { class: "muted" }, e.description) : null,
        h("div", { class: "exp-card-stats" },
          h("div", {}, h("span", { class: "label" }, "Avg reward"), h("span", { class: "value" }, num(e.reward))),
          h("div", {}, h("span", { class: "label" }, "Runs"), h("span", { class: "value" }, e.runs.length)),
          h("div", {}, h("span", { class: "label" }, "Tasks"), h("span", { class: "value" }, e.tasks)),
          h("div", {}, h("span", { class: "label" }, "Trials"), h("span", { class: "value" }, `${e.finished}/${e.trials}`))),
        stackBar(e.counts, e.trials), legend(e.counts));
    })) : h("p", { class: "muted" }, "No experiments yet."));
}

async function viewExperiment(id) {
  const x = await getJSON(`data/experiments/${enc(id)}.json`);
  const board = x.leaderboard;
  const runs = board.map((b) => b.run_id);
  const tokens = board.reduce((n, b) => n + (b.tokens || 0), 0);
  const cost = board.reduce((n, b) => n + (b.cost_usd || 0), 0);

  const leaderboard = h("section", { class: "card board" }, h("div", { class: "controls" }, h("h2", {}, "Leaderboard"),
    h("span", { class: "muted" }, "mean reward over the trials each run scored")),
    h("ol", { class: "board-list" }, board.map((b) => h("li", {},
      h("div", { class: "board-row" },
        h("a", { href: `#/run/${enc(b.run_id)}`, class: "mono", title: b.run_id }, runLabel(b)),
        b.note ? h("span", { class: "muted" }, b.note) : null,
        h("span", { class: "board-score mono" }, num(b.reward))),
      h("div", { class: "bar wide", "aria-hidden": "true" }, h("span", { style: `width:${Math.round((b.reward || 0) * 100)}%` })),
      h("div", { class: "board-meta muted" },
        `ID ${num(b.sets.id?.reward)} · OOD ${num(b.sets.ood?.reward)}`,
        b.task_reward !== null && b.task_reward !== undefined ? ` · task reward ${num(b.task_reward)}` : "",
        ` · ${b.finished}/${b.trials} trials · ${runDate(b.run_id)}`)))));

  show(
    h("section", {}, h("p", { class: "crumbs" }, h("a", { href: "#/" }, "Experiments"), " / ", x.id),
      h("div", { class: "controls spread" }, h("div", { class: "head" }, h("h1", { class: "mono-title" }, x.title),
        h("p", { class: "muted" }, `${x.id} · created ${x.created.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")} · ${runs.length} run${runs.length === 1 ? "" : "s"}`)),
        h("a", { class: "button ghost", href: `#/tasks/experiment/${enc(x.id)}` }, "Get the tasks")),
      x.description ? h("p", { class: "muted" }, x.description) : null),
    h("div", { class: "statbar" },
      h("div", { class: "stat" }, h("span", { class: "label" }, "Avg reward"), h("span", { class: "value" }, num(x.reward)),
        h("span", { class: "label" }, "Tasks"), h("span", { class: "value small" }, x.tasks)),
      h("div", { class: "stat grow" }, h("span", { class: "label" }, "Trials finished"),
        h("span", { class: "value" }, `${x.finished}`, h("span", { class: "muted small" }, ` / ${x.trials}`)),
        stackBar(x.counts, x.trials), legend(x.counts)),
      h("div", { class: "stat" }, h("span", { class: "label" }, "Run cost"), h("span", { class: "value" }, cost ? `$${cost.toFixed(2)}` : "$0"),
        h("span", { class: "note muted" }, tokens ? `${(tokens / 1e6).toFixed(1)}M tokens` : "self-hosted"))),
    leaderboard,
    gridSection(x, board));
}

function gridSection(x, board) {
  const search = h("input", { type: "search", class: "search", placeholder: "Search tasks (comma-separated): id, state, family, twist, issue", "aria-label": "Search tasks" });
  const active = new Set(STATUSES.map(([k]) => k));
  const statusButtons = STATUSES.map(([k, l]) => h("button", { type: "button", class: "toggle", "aria-pressed": "true",
    onclick: (e) => { if (active.has(k)) active.delete(k); else active.add(k); e.currentTarget.setAttribute("aria-pressed", String(active.has(k))); render(); } },
    h("span", { class: `dot seg-${k}` }), l));
  const views = { all: "All", any_error: "Any error", any_failed: "Any failed", all_failed: "All failed" };
  let view = "all";
  const viewButtons = Object.entries(views).map(([k, l]) => h("button", { type: "button", class: "toggle", "aria-pressed": String(k === "all"),
    onclick: (e) => { view = k; for (const b of viewButtons) b.setAttribute("aria-pressed", "false"); e.currentTarget.setAttribute("aria-pressed", "true"); render(); } }, l));
  const shown = new Set(board.map((b) => b.run_id));
  const columns = h("details", { class: "columns" }, h("summary", {}, `Columns ${shown.size}/${board.length}`),
    h("div", { class: "menu" }, board.map((b) => h("label", {}, h("input", { type: "checkbox", checked: true,
      onchange: (e) => { if (e.target.checked) shown.add(b.run_id); else shown.delete(b.run_id); columns.firstChild.textContent = `Columns ${shown.size}/${board.length}`; render(); } }),
      ` ${runLabel(b)}`, b.note ? h("span", { class: "muted" }, ` · ${b.note}`) : null))));
  const count = h("span", { class: "muted", "aria-live": "polite" });
  const copy = h("button", { type: "button", class: "button ghost small" }, "Copy TSV");
  const body = h("tbody");
  const head = h("thead");
  let visible = [];

  function keep(row, cols) {
    const cells = cols.map((r) => row.cells[r]).filter(Boolean);
    const failed = (c) => c.status === "fail" || c.status === "error";
    if (view === "any_error" && !cells.some((c) => c.status === "error")) return false;
    if (view === "any_failed" && !cells.some(failed)) return false;
    if (view === "all_failed" && !(cells.length && cells.every(failed))) return false;
    if (active.size < STATUSES.length && !cells.some((c) => active.has(c.status))) return false;
    const hay = [row.case, row.task, row.state, row.shift, FAMILIES[row.shift], ...row.twists, ...row.issues, ...row.issues.map((i) => ISSUES[i])].join(" ").toLowerCase();
    return matches(hay, search.value);
  }
  function render() {
    const cols = board.filter((b) => shown.has(b.run_id));
    head.replaceChildren(h("tr", {}, h("th", { class: "num" }, "#"), h("th", {}, "Task"),
      cols.map((b) => h("th", { class: "run-col" }, h("a", { href: `#/run/${enc(b.run_id)}`, title: b.run_id }, runLabel(b)),
        h("div", { class: "muted" }, b.note || runDate(b.run_id))))));
    visible = x.rows.filter((row) => keep(row, cols.map((b) => b.run_id)));
    count.textContent = `${visible.length} of ${x.rows.length} tasks`;
    body.replaceChildren(...visible.map((row, i) => h("tr", {},
      h("td", { class: "num muted" }, i + 1),
      h("td", { class: "task-cell" }, h("a", { href: `#/task/${enc(row.task)}`, class: "mono" }, row.case),
        h("div", {}, h("span", { class: "chip" }, row.state), familyChips(row), chips(row.issues.map((k) => ISSUES[k] || k), "soft"))),
      cols.map((b) => {
        const c = row.cells[b.run_id];
        return h("td", { class: "run-col" }, c ? h("div", { class: "cell" },
          square(c, { href: `#/task/${enc(row.task)}/trial/${enc(b.run_id)}` }),
          c.reward !== undefined ? h("span", { class: "mono" }, num(c.reward)) : h("span", { class: "muted" }, STATUS_NOTE[c.status])) : h("span", { class: "muted" }, "–"));
      }))));
  }
  copy.addEventListener("click", () => {
    const cols = board.filter((b) => shown.has(b.run_id));
    copyTSV(copy, ["case", "task", "state", "family", "twists", "issues", ...cols.flatMap((b) => [`${b.run_id} status`, `${b.run_id} reward`])],
      visible.map((r) => [r.case, r.task, r.state, r.shift, r.twists.join(" "), r.issues.join(" "),
        ...cols.flatMap((b) => [r.cells[b.run_id]?.status ?? "", r.cells[b.run_id]?.reward ?? ""])]));
  });
  search.addEventListener("input", render);
  render();
  return h("section", {}, h("h2", {}, "Tasks"),
    h("div", { class: "toolbar" }, search,
      h("div", { class: "toggles", role: "group", "aria-label": "Trial status" }, h("span", { class: "toolbar-label" }, "Trial"), statusButtons)),
    h("div", { class: "toolbar" }, h("div", { class: "toggles", role: "group", "aria-label": "View" }, h("span", { class: "toolbar-label" }, "View"), viewButtons),
      columns, copy, count),
    h("div", { class: "table-scroll grid-table" }, h("table", {}, head, body)));
}

// --- tasks --------------------------------------------------------------------------------------

function truthCell(t) {
  const yn = (v) => h("span", { class: `tv tv-${v}` }, v === "yes" ? "Y" : v === "no" ? "N" : "?");
  const mem = (m) => h("span", { class: m.unknown ? "tv tv-unknown" : "tv" }, `${m.eligible}${m.unknown ? `+${m.unknown}?` : ""}/${m.of}`);
  return h("span", { class: "truth-cell" }, "SNAP ", yn(t.snap), " EITC ", yn(t.eitc), " Medicaid ", mem(t.medicaid), " WIC ", mem(t.wic));
}

async function viewTasks(experiment) {
  const idx = await getJSON("data/tasks.json");
  const all = idx.tasks;
  const exps = idx.experiments;
  const runExp = {};
  for (const e of exps) for (const r of e.runs) runExp[r] = e.id;
  const values = (key) => [...new Set(all.flatMap((t) => (Array.isArray(t[key]) ? t[key] : [t[key]])).filter((v) => v !== null && v !== undefined))].sort();
  const select = (label, options, names) => h("select", { "aria-label": label },
    h("option", { value: "" }, label), options.map((o) => h("option", { value: o }, (names && names[o]) || o)));
  const search = h("input", { type: "search", class: "search", placeholder: "Search (comma-separated): case id, task id, state, twist, issue, document", "aria-label": "Search tasks" });
  const fSplit = select("All splits", values("split"), SPLITS);
  const fFamily = select("All families", values("shift"), FAMILIES);
  const fTwist = select("All twists", values("twists"));
  const fIssue = select("All issues", values("issues"), ISSUES);
  const fState = select("All states", values("state"));
  const fTruth = h("select", { "aria-label": "PolicyEngine answer" }, h("option", { value: "" }, "Any answer"),
    [["snap", "SNAP"], ["eitc", "EITC"]].flatMap(([k, l]) => [["yes", "eligible"], ["no", "not eligible"], ["unknown", "unknown"]].map(([v, n]) =>
      h("option", { value: `${k}:${v}` }, `${l}: ${n}`))));
  const fExp = h("select", { "aria-label": "Experiment" }, h("option", { value: "" }, "Any experiment"),
    exps.map((e) => h("option", { value: e.id, selected: e.id === experiment }, e.title)));
  const fResult = h("select", { "aria-label": "Result" }, h("option", { value: "" }, "Any result"),
    STATUSES.map(([k, l]) => h("option", { value: k }, `Latest run: ${l.toLowerCase()}`)));
  const count = h("span", { class: "muted", "aria-live": "polite" });
  const copy = h("button", { type: "button", class: "button ghost small" }, "Copy TSV");
  const body = h("tbody");
  let visible = [];

  function latest(t, exp) {
    const runs = Object.keys(t.results).filter((r) => !exp || runExp[r] === exp).sort().reverse();
    return runs.length ? t.results[runs[0]] : null;
  }
  function render() {
    visible = all.filter((t) => {
      if (fSplit.value && t.split !== fSplit.value) return false;
      if (fFamily.value && t.shift !== fFamily.value) return false;
      if (fTwist.value && !t.twists.includes(fTwist.value)) return false;
      if (fIssue.value && !t.issues.includes(fIssue.value)) return false;
      if (fState.value && t.state !== fState.value) return false;
      if (fTruth.value) { const [k, v] = fTruth.value.split(":"); if (t.truth[k] !== v) return false; }
      if (fExp.value && !Object.keys(t.results).some((r) => runExp[r] === fExp.value)) return false;
      if (fResult.value) { const c = latest(t, fExp.value); if (!c || c.status !== fResult.value) return false; }
      const hay = [t.case, t.task, t.state, t.split, t.shift, FAMILIES[t.shift], ...t.twists, ...t.issues, ...t.issues.map((i) => ISSUES[i]), ...t.gaps, ...t.missing].join(" ").toLowerCase();
      return matches(hay, search.value);
    });
    count.textContent = `${visible.length} of ${all.length} tasks`;
    body.replaceChildren(...visible.slice(0, 500).map((t) => {
      const href = `#/task/${enc(t.task)}`;
      const go = () => { location.hash = href; };
      return h("tr", { class: "link", tabindex: 0, onclick: (e) => { if (!e.target.closest("a")) go(); }, onkeydown: (e) => { if (e.key === "Enter") go(); } },
        h("td", {}, h("a", { href, class: "mono" }, t.case), h("div", { class: "mono muted" }, short(t.task))),
        h("td", { class: "wrap-cell" }, h("span", { class: "chip" }, SPLITS[t.split] || t.split), t.sample ? h("span", { class: "chip cool" }, "sample") : null,
          h("span", { class: "chip" }, t.state), h("span", { class: "chip" }, `${t.members} ${t.members === 1 ? "person" : "people"}`), familyChips(t)),
        h("td", { class: "wrap-cell" }, chips(t.issues.map((k) => ISSUES[k] || k), "soft"), !t.issues.length ? h("span", { class: "muted" }, "clean") : null),
        h("td", {}, truthCell(t.truth)),
        h("td", {}, h("div", { class: "squares" }, exps.map((e) => {
          const runs = e.runs.filter((r) => t.results[r]);
          return runs.length ? h("span", { class: "sq-group", title: e.title }, runs.map((r) =>
            square(t.results[r], { href: `#/task/${enc(t.task)}/trial/${enc(r)}`, title: `${e.title}: ${r}` }))) : null;
        }))));
    }));
  }
  copy.addEventListener("click", () => copyTSV(copy, ["case", "task", "split", "state", "members", "family", "twists", "issues", "snap", "eitc"],
    visible.map((t) => [t.case, t.task, t.split, t.state, t.members, t.shift, t.twists.join(" "), t.issues.join(" "), t.truth.snap, t.truth.eitc])));
  search.addEventListener("input", render);
  for (const f of [fSplit, fFamily, fTwist, fIssue, fState, fTruth, fExp, fResult]) f.addEventListener("change", render);
  render();
  const private_ = all.some((t) => t.split === "train" || t.split === "validation");
  show(
    h("section", {}, h("div", { class: "head" }, h("h1", {}, "Tasks"),
      h("p", {}, "Every task is one household's case: an application and its documents as PDFs, a calculator, and an answer file to write. ",
        private_ ? "This local server also lists the private train and validation tasks." : "This site lists the 400 holdout tasks; train and validation tasks have secret answers and only appear on a local server started with --private-splits."))),
    h("div", { class: "toolbar" }, search),
    h("div", { class: "toolbar" }, fSplit, fFamily, fTwist, fIssue, fState, fTruth, fExp, fResult),
    h("div", { class: "toolbar" }, count, copy,
      h("span", { class: "muted small" }, "Squares: one per run, grouped by experiment; click one to open that trial.")),
    h("div", { class: "table-scroll cases" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Task"), h("th", {}, "Household"),
      h("th", {}, "Issues"), h("th", {}, "PolicyEngine's answer"), h("th", {}, "Results"))), body)),
    visible.length > 500 ? h("p", { class: "muted" }, "Showing the first 500; narrow the search to see the rest.") : null);
}

// --- one task -----------------------------------------------------------------------------------

const GROUP_ORDER = ["Overview", "Prompt", "Documents", "Reference solution", "Verification", "Agent environment", "Task metadata"];
const GROUP_PREFIX = { Documents: "environment/case/", "Reference solution": "solution/", Verification: "tests/", "Agent environment": "environment/" };
function fileURL(task, f) {
  return f.shared ? `data/task-shared/${f.path.split("/").map(enc).join("/")}` : `data/tasks/${enc(task)}/files/${f.path.split("/").map(enc).join("/")}`;
}
function sizeLabel(n) {
  return n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`;
}

// A small Markdown renderer for the task instruction (our own text, rendered with text nodes all the same).
function inline(text) {
  const out = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(m[0].startsWith("`") ? h("code", {}, m[0].slice(1, -1)) : h("strong", {}, m[0].slice(2, -2)));
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}
function markdown(src) {
  const nodes = [];
  const lines = src.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const code = [];
      for (i++; i < lines.length && !lines[i].startsWith("```"); i++) code.push(lines[i]);
      nodes.push(h("pre", { class: "text" }, code.join("\n")));
    } else if (/^#{1,4} /.test(line)) {
      const level = Math.min(line.indexOf(" ") + 1, 4);
      nodes.push(h(`h${level}`, {}, inline(line.replace(/^#+ /, ""))));
    } else if (/^\s*([-*]|\d+\.) /.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items = [];
      for (; i < lines.length && /^\s*([-*]|\d+\.) /.test(lines[i]); i++) items.push(h("li", {}, inline(lines[i].replace(/^\s*([-*]|\d+\.) /, ""))));
      i--;
      nodes.push(h(ordered ? "ol" : "ul", {}, items));
    } else if (line.startsWith("|")) {
      const rows = [];
      for (; i < lines.length && lines[i].startsWith("|"); i++) if (!/^\|[\s|:-]+\|$/.test(lines[i])) rows.push(lines[i].slice(1, -1).split("|").map((c) => c.trim()));
      i--;
      nodes.push(h("div", { class: "table-scroll" }, h("table", {}, h("thead", {}, h("tr", {}, rows[0].map((c) => h("th", {}, inline(c))))),
        h("tbody", {}, rows.slice(1).map((r) => h("tr", {}, r.map((c) => h("td", { class: "wrap-cell" }, inline(c)))))))));
    } else if (line.trim()) {
      const para = [line];
      for (; i + 1 < lines.length && lines[i + 1].trim() && !/^(#|```|\s*([-*]|\d+\.) |\|)/.test(lines[i + 1]); i++) para.push(lines[i + 1]);
      nodes.push(h("p", {}, inline(para.join(" "))));
    }
  }
  return h("div", { class: "md" }, nodes);
}

// The task PDFs, drawn with pdf.js (vendored in vendor/pdfjs) so every browser shows them the same way.
// "Text" shows the text layer, close to what pdftotext gives the agent.
let pdfjsReady = null;
function loadPdfjs() {
  if (!pdfjsReady) {
    pdfjsReady = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "vendor/pdfjs/pdf.min.js";
      script.onload = () => { window.pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js"; resolve(window.pdfjsLib); };
      script.onerror = () => { pdfjsReady = null; reject(new Error("couldn't load the PDF renderer")); };
      document.head.append(script);
    });
  }
  return pdfjsReady;
}
function pdfPane(url, name) {
  const pages = h("div", { class: "pdf-pages" }, h("p", { class: "muted" }, "Rendering…"));
  let mode = "rendered", doc = null;
  const buttons = [["rendered", "Rendered"], ["text", "Text"]].map(([k, l]) => h("button", { type: "button", class: "toggle", "aria-pressed": String(k === mode),
    onclick: () => { mode = k; for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset.mode === mode)); draw(); } }, l));
  buttons.forEach((b, i) => { b.dataset.mode = i ? "text" : "rendered"; });
  async function draw() {
    if (!doc) return;
    const out = [];
    for (let n = 1; n <= doc.numPages; n++) {
      const page = await doc.getPage(n);
      if (mode === "text") {
        const content = await page.getTextContent();
        const lines = [];
        let y = null;
        for (const item of content.items) {
          const iy = Math.round(item.transform[5]);
          if (y !== null && Math.abs(iy - y) > 2) lines.push("\n"); else if (lines.length) lines.push(" ");
          lines.push(item.str);
          y = iy;
        }
        out.push(h("pre", { class: "text open" }, `— page ${n} —\n${lines.join("").replace(/ +/g, " ")}`));
      } else {
        const viewport = page.getViewport({ scale: 1.6 });
        const canvas = h("canvas", { class: "pdf-page", width: Math.floor(viewport.width), height: Math.floor(viewport.height), "aria-label": `${name}, page ${n}` });
        await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
        out.push(canvas);
      }
    }
    pages.replaceChildren(...out);
  }
  loadPdfjs().then((lib) => lib.getDocument(url).promise).then((d) => { doc = d; return draw(); })
    .catch((e) => pages.replaceChildren(h("p", { class: "error" }, `Couldn't render the PDF (${e.message}). `, h("a", { href: url }, "Open it directly"))));
  return h("div", { class: "pane-body" }, h("div", { class: "controls" }, h("div", { class: "toggles" }, buttons),
    h("a", { class: "muted small", href: url, target: "_blank", rel: "noopener" }, "Open the PDF")), pages);
}

async function fetchText(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.text();
}
async function fetchTrajectory(run, task) {
  const r = await fetch(`data/runs/${enc(run)}/trajectories/${enc(task)}.json.gz`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const bytes = new Uint8Array(await r.arrayBuffer());
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) { // still gzipped (the host didn't decode it for us)
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text());
  }
  return JSON.parse(new TextDecoder().decode(bytes));
}

function overviewPane(t) {
  const issues = t.issues_detail.length ? h("ul", { class: "plain" }, t.issues_detail.map((i) =>
    h("li", {}, h("span", { class: "chip soft" }, ISSUES[i.kind] || i.kind), i.detail || "", i.missing ? h("div", { class: "muted" }, `Missing: ${i.missing}`) : null)))
    : h("p", { class: "muted" }, "No distractors or gaps: a clean packet.");
  return h("div", { class: "pane-body" },
    h("h3", {}, "Household"),
    h("p", {}, h("span", { class: "chip" }, SPLITS[t.split] || t.split), h("span", { class: "chip" }, t.state),
      h("span", { class: "chip" }, `${t.members} ${t.members === 1 ? "person" : "people"}`), familyChips(t),
      t.sample ? h("span", { class: "chip cool" }, "sample task in tasks/") : null),
    t.edge ? h("p", { class: "muted" }, `Threshold edge: income within 1% of a ${String(t.edge).toUpperCase()} cutoff.`) : null,
    h("h3", {}, "Distractors and gaps"), issues,
    h("h3", {}, "Documents"), h("ul", { class: "plain" }, t.documents_detail.map((d) => h("li", {}, h("span", { class: "mono" }, `${d.name}.pdf`), ` · ${d.kind.replace(/_/g, " ")}`, d.date ? h("span", { class: "muted" }, ` · ${d.date}`) : null))),
    h("h3", {}, "PolicyEngine's answer"), h("p", {}, truthCell(t.truth)),
    t.missing.length ? h("p", { class: "muted" }, `Missing information to flag: ${t.missing.map((m) => (typeof m === "string" ? m : m.document || JSON.stringify(m))).join(", ")}`) : null);
}

function filePane(t, f) {
  if (!f) return overviewPane(t);
  const url = fileURL(t.task, f);
  if (f.kind === "pdf") return pdfPane(url, f.path);
  const holder = h("div", { class: "pane-body" }, h("p", { class: "muted" }, "Loading…"));
  let raw = f.kind !== "markdown";
  const render = (text) => {
    const toggle = f.kind === "markdown" ? h("div", { class: "toggles" },
      h("button", { type: "button", class: "toggle", "aria-pressed": String(!raw), onclick: () => { raw = false; render(text); } }, "Rendered"),
      h("button", { type: "button", class: "toggle", "aria-pressed": String(raw), onclick: () => { raw = true; render(text); } }, "Raw")) : null;
    holder.replaceChildren(toggle || "", raw ? h("pre", { class: "text open" }, text) : markdown(text));
  };
  fetchText(url).then(render, (e) => holder.replaceChildren(h("p", { class: "error" }, `Couldn't load ${f.path}: ${e.message}`)));
  return holder;
}

function definitionPane(t, state) {
  const viewer = h("div", { class: "file-view" });
  const label = h("span", { class: "mono muted" });
  const tree = h("nav", { class: "file-tree", "aria-label": "Task files" });
  const groups = {};
  for (const f of t.files) (groups[f.group] ||= []).push(f);
  function open(f) {
    state.file = f ? f.path : null;
    for (const b of tree.querySelectorAll("button")) b.setAttribute("aria-current", String(b.dataset.path === (f ? f.path : "")));
    label.textContent = f ? f.path : "overview";
    viewer.replaceChildren(filePane(t, f));
  }
  tree.append(...GROUP_ORDER.filter((g) => g === "Overview" || groups[g]).map((g) => h("div", { class: "tree-group" },
    h("div", { class: "tree-label" }, g),
    g === "Overview" ? h("button", { type: "button", "data-path": "", onclick: () => open(null) }, "household & answer")
      : groups[g].map((f) => h("button", { type: "button", "data-path": f.path, title: f.path, onclick: () => open(f) },
        h("span", {}, f.path.slice((GROUP_PREFIX[g] || "").length)), h("span", { class: "muted" }, sizeLabel(f.size)))))));
  open(t.files.find((f) => f.path === state.file) || (state.file === null ? null : t.files.find((f) => f.path === "instruction.md")));
  return h("section", { class: "pane definition" }, h("div", { class: "pane-head" }, h("span", { class: "pane-title" }, "Task definition"), label),
    h("div", { class: "definition-body" }, tree, viewer));
}

function timeline(traj, trial) {
  if (!traj) {
    return trial.seconds ? h("p", { class: "muted" }, `Agent ran ${Math.round(trial.seconds / 60)} min; the full timeline is kept for trials with trajectories.`) : null;
  }
  const phases = traj.phases.filter((p) => p.started_at);
  const start = Date.parse(traj.started_at || phases[0]?.started_at);
  const end = Date.parse(traj.finished_at || phases[phases.length - 1]?.finished_at);
  const span = Math.max(end - start, 1);
  const fmt = (s) => (s === null || s === undefined ? "" : s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`);
  return h("div", { class: "timeline" },
    h("ol", {}, phases.map((p) => h("li", {}, h("span", { class: "dot seg-pass" }), h("span", {}, p.label), h("span", { class: "muted mono" }, fmt(p.seconds))))),
    h("div", { class: "track" }, phases.map((p) => h("span", { class: `phase phase-${p.key}`, title: `${p.label} ${fmt(p.seconds)}`,
      style: `left:${((Date.parse(p.started_at) - start) / span) * 100}%;width:${Math.max(((Date.parse(p.finished_at) - Date.parse(p.started_at)) / span) * 100, 0.5)}%` }))),
    h("p", { class: "muted small mono" }, `${(traj.started_at || "").replace("T", " ").slice(0, 19)} → ${(traj.finished_at || "").replace("T", " ").slice(0, 19)} UTC · total ${fmt((end - start) / 1000)}`));
}

function agentMessage(text) {
  // terminus-2 replies with JSON: analysis, plan, commands, task_complete. Show those parts; fall back to the text.
  let parsed = null;
  try { parsed = JSON.parse(text); } catch { /* not JSON */ }
  if (!parsed || typeof parsed !== "object") return h("pre", { class: "text open" }, text);
  return h("div", { class: "agent-msg" },
    parsed.analysis ? h("div", {}, h("span", { class: "tag" }, "analysis"), h("p", {}, String(parsed.analysis))) : null,
    parsed.plan ? h("div", {}, h("span", { class: "tag" }, "plan"), h("p", {}, String(parsed.plan))) : null,
    parsed.task_complete ? h("span", { class: "chip good" }, "marked complete") : null);
}

function trajectoryPane(traj, trial, caseData) {
  if (!traj) {
    if (trial.harness) return h("p", { class: "muted" }, "This trial's turns weren't kept (it ran before trajectories were stored).");
    return h("div", { class: "steps" }, h("p", { class: "muted" }, "One-reply run: the model saw the case once and answered once."),
      h("div", { class: "step agent" }, h("div", { class: "step-head" }, h("span", { class: "tag" }, "model"), "reply"),
        h("pre", { class: "text open" }, caseData?.reply || "(empty reply)")));
  }
  const steps = traj.steps.map((s, i) => {
    const longOut = s.output.join("\n").length > 1200;
    const body = [];
    if (s.source === "agent") {
      body.push(agentMessage(s.message));
      for (const c of s.calls) {
        const keys = c.args && (c.args.keystrokes ?? c.args.command);
        body.push(h("pre", { class: "text cmd open" }, keys !== undefined ? String(keys) : JSON.stringify(c.args, null, 1)));
      }
    } else if (s.message) {
      const pre = h("pre", { class: "text" }, s.message);
      body.push(s.message.length > 600 ? h("details", {}, h("summary", {}, `${s.source === "user" && i === 0 ? "Task instruction" : "Message"} (${s.message.length.toLocaleString("en-US")} characters)`), pre) : h("pre", { class: "text open" }, s.message));
    }
    if (s.output.length) {
      const out = h("pre", { class: "text out open" }, s.output.join("\n"));
      body.push(longOut ? h("details", {}, h("summary", {}, `Terminal output (${s.output.join("").length.toLocaleString("en-US")} characters)`), out) : out);
    }
    return h("li", { class: `step ${s.source}` }, h("div", { class: "step-head" }, h("span", { class: "tag" }, s.source), `step ${s.id ?? i + 1}`,
      s.tokens && s.tokens.completion_tokens ? h("span", { class: "muted mono" }, `${s.tokens.prompt_tokens?.toLocaleString("en-US") ?? "–"} in · ${s.tokens.completion_tokens} out`) : null,
      s.time ? h("span", { class: "muted mono" }, s.time.replace("T", " ").slice(11, 19)) : null), body);
  });
  return h("div", {}, h("ol", { class: "steps" }, steps),
    h("h3", {}, "answer.json"), h("pre", { class: "text open" }, traj.answer ?? "(no answer file)"));
}

async function trialPane(t, trial, tab) {
  const base = `#/task/${enc(t.task)}/trial/${enc(trial.run_id)}`;
  const [caseData, traj] = await Promise.all([
    getJSON(`data/runs/${enc(trial.run_id)}/cases/${enc(t.case)}.json`).catch(() => null),
    trial.trajectory ? fetchTrajectory(trial.run_id, t.task).catch(() => null) : Promise.resolve(null)]);
  const byExp = {};
  for (const tr of t.trials) (byExp[tr.experiment] ||= []).push(tr);
  const picker = h("div", { class: "picker" }, Object.entries(byExp).map(([e, list]) => h("span", { class: "sq-group", title: e },
    h("span", { class: "muted small" }, e), list.map((tr) => square(tr, { href: `#/task/${enc(t.task)}/trial/${enc(tr.run_id)}/${tab}`,
      "aria-current": String(tr.run_id === trial.run_id), class: `sq sq-${tr.status}${tr.run_id === trial.run_id ? " current" : ""}`,
      onclick: () => { keepScroll = true; } })))));
  const usage = trial.usage || {};
  const ts = caseData?.task_score;
  const stats = h("div", { class: "trial-stats" },
    h("span", {}, h("span", { class: `dot seg-${trial.status}` }), "Reward ", h("strong", { class: "mono" }, num(trial.reward))),
    trial.task_reward !== undefined ? h("span", {}, "Task reward ", h("strong", { class: "mono" }, num(trial.task_reward))) : null,
    usage.prompt_tokens ? h("span", {}, h("strong", { class: "mono" }, `${((usage.prompt_tokens + (usage.completion_tokens || 0)) / 1000).toFixed(1)}k`), " tokens") : null,
    trial.seconds ? h("span", {}, "Agent run ", h("strong", { class: "mono" }, `${Math.floor(trial.seconds / 60)}m ${Math.round(trial.seconds % 60)}s`)) : null,
    trial.turns ? h("span", {}, h("strong", { class: "mono" }, trial.turns), " steps") : null);
  const tabs = h("div", { class: "tabs", role: "tablist" }, [["summary", "Summary"], ["answer", "Answer"], ["trajectory", "Trajectory"]].map(([k, l]) =>
    h("a", { role: "tab", href: `${base}/${k}`, "aria-selected": String(k === tab), onclick: () => { keepScroll = true; } }, l)));
  let body;
  if (tab === "answer") {
    body = caseData ? h("div", {}, verdictTable(caseData),
      h("h3", {}, "Model's reply"), h("pre", { class: "text open" }, caseData.reply || "(no reply)")) : h("p", { class: "muted" }, "No result for this case in this run.");
  } else if (tab === "trajectory") {
    body = trajectoryPane(traj, trial, caseData);
  } else {
    const ok = caseData && caseData.status === "ok";
    body = h("div", { class: "pane-body" },
      h("div", { class: "card inset" }, h("div", { class: "controls" }, h("h3", {}, "Execution timeline"),
        h("span", { class: `chip ${trial.status === "pass" ? "good" : trial.status === "error" || trial.status === "skipped" ? "bad" : ""}` },
          `${(STATUSES.find(([k]) => k === trial.status) || [, trial.status])[1]} · ${STATUS_NOTE[trial.status] || ""}`)),
        timeline(traj, trial)),
      h("div", { class: "tiles four" },
        tile("Reward", ok ? num(caseData.score.reward) : "–", "evals scorer"),
        tile("Eligibility", ok ? num(caseData.score.eligibility) : "–", "false denials count double"),
        tile("Amounts", ok ? num(caseData.score.amount) : "–", "SNAP and EITC"),
        ts ? tile("Missing info", num(ts.missing_info), "task verifier only") : null),
      traj?.exception ? h("p", { class: "notice bad" }, `${traj.exception.type}: ${traj.exception.message.split("\n")[0]}`) : null,
      ok && caseData.parse_error ? h("p", { class: "notice bad" }, `No readable answer: ${caseData.parse_error}`) : null,
      h("p", { class: "muted small" }, h("a", { href: `#/run/${enc(trial.run_id)}/case/${enc(t.case)}` }, "This case in the run view"), ` · ${trial.run_id}`));
  }
  return h("section", { class: "pane trial" },
    h("div", { class: "pane-head" }, h("span", { class: "pane-title mono" }, t.case), h("span", { class: "chip" }, runLabel(trial)),
      trial.note ? h("span", { class: "muted small" }, trial.note) : null),
    h("div", { class: "trial-head" }, picker, stats), tabs, h("div", { class: "trial-body" }, body));
}

const taskState = { task: null, file: undefined };
async function viewTask(task, runId, tab) {
  const t = await getJSON(`data/tasks/${enc(task)}/task.json`);
  if (taskState.task !== task) { taskState.task = task; taskState.file = undefined; }
  const trial = t.trials.find((tr) => tr.run_id === runId) || t.trials[0];
  const right = trial ? await trialPane(t, trial, ["summary", "answer", "trajectory"].includes(tab) ? tab : "summary")
    : h("section", { class: "pane trial" }, h("p", { class: "muted" }, "No run has scored this task yet."));
  show(
    h("section", {}, h("p", { class: "crumbs" }, h("a", { href: "#/tasks" }, "Tasks"), " / ", t.case),
      h("div", { class: "controls spread" }, h("h1", { class: "mono-title" }, t.case),
        h("span", { class: "mono muted" }, t.task))),
    h("div", { class: "task-split" }, definitionPane(t, taskState), right));
}

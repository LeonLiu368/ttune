// ttune eval viewer. Hash routes:
//   #/                          runs list + launch form
//   #/run/<run>[/set/<id|ood>]  one run: metrics, OOD families, case table
//   #/run/<run>/case/<case>     one household traced: case text, model answer vs PolicyEngine, the full reply
// Model replies are untrusted text: everything is added with textContent, never as HTML.
"use strict";

const app = document.getElementById("app");
const cache = new Map();
let health = null; // set when a viewer server answers /api/health; null on the static (read-only) site

const PROGRAMS = [["snap", "SNAP"], ["eitc", "EITC"], ["medicaid", "Medicaid"], ["wic", "WIC"]];
const SETS = { id: "Typical (ID)", ood: "Unusual (OOD)" };
const FAMILIES = { rare_shape: "Rare shapes", threshold_edge: "Threshold edges", held_out_state: "Held-out states", none: "Typical" };

// --- helpers ------------------------------------------------------------------------------------

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const pct = (v) => (v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`);
const num = (v) => (v === null || v === undefined ? "–" : v.toFixed(2));
const money = (v) => (v === null || v === undefined ? "–" : `$${Math.round(v).toLocaleString("en-US")}`);
function signed(d, points) {
  if (d === null || d === undefined) return "–";
  const v = points ? Math.round(d * 100) : Math.round(d * 100) / 100;
  const text = points ? `${Math.abs(v)} pts` : Math.abs(v).toFixed(2);
  return `${v > 0 ? "+" : v < 0 ? "−" : "±"}${text}`;
}
function changeCell(change, points) {
  if (!change) return "–";
  const cls = change.high < 0 ? "down" : change.low > 0 ? "up" : "";
  const bound = (v) => signed(v, points).replace(" pts", "");
  return h("span", { class: cls }, signed(change.change, points), h("span", { class: "muted" },
    ` (${bound(change.low)} to ${bound(change.high)})`));
}
function runDate(runId) {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(runId);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]} UTC` : "";
}
async function getJSON(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }).catch((e) => { cache.delete(path); throw e; }));
  }
  return cache.get(path);
}
function show(...nodes) {
  app.replaceChildren(...nodes.filter(Boolean));
  app.focus({ preventScroll: true });
}
const table = (head, rows) => h("div", { class: "table-scroll" }, h("table", {},
  h("thead", {}, h("tr", {}, head.map(([label, cls]) => h("th", { class: cls }, label)))),
  h("tbody", {}, rows)));
const tile = (label, value, note) => h("div", { class: "tile" },
  h("span", { class: "label" }, label), h("span", { class: "value" }, value), note ? h("span", { class: "note" }, note) : null);

// --- runs list + launch -------------------------------------------------------------------------

async function viewRuns() {
  const runs = await getJSON("data/runs.json");
  const rows = runs.map((r) => {
    const id = r.sets.id || {}, ood = r.sets.ood || {};
    const go = () => { location.hash = `#/run/${encodeURIComponent(r.run_id)}`; };
    return h("tr", { class: "link", tabindex: 0, onclick: go, onkeydown: (e) => { if (e.key === "Enter") go(); } },
      h("td", {}, h("a", { href: `#/run/${encodeURIComponent(r.run_id)}`, title: r.run_id }, r.model || r.run_id),
        h("div", {}, h("span", { class: "chip" }, r.hosted), r.parameters ? h("span", { class: "chip" }, r.parameters) : null)),
      h("td", {}, runDate(r.run_id)),
      h("td", { class: "num" }, `${id.n ?? 0} + ${ood.n ?? 0}`),
      h("td", { class: "num" }, num(id.reward)),
      h("td", { class: "num" }, num(ood.reward)),
      h("td", { class: "num" }, `${pct(id.false_denial_rate)} → ${pct(ood.false_denial_rate)}`),
      h("td", { class: "num" }, `${pct(id.malformed)} / ${pct(ood.malformed)}`),
      h("td", { class: "num" }, r.cost_usd ? `$${r.cost_usd.toFixed(4)}` : "$0"));
  });
  show(
    h("section", {}, h("div", { class: "head" }, h("h1", {}, "Eval runs"),
      h("p", { class: "muted" }, "Each run asks a model about the same 200 typical (ID) and 200 unusual (OOD) households, and grades every answer against PolicyEngine. Reward is 0 to 1; false denials are \"not eligible\" answers to people who qualify."))),
    runs.length ? table([["Model"], ["Started"], ["Households", "num"], ["ID reward", "num"],
      ["OOD reward", "num"], ["False denials ID → OOD", "num"], ["Malformed ID / OOD", "num"], ["Cost", "num"]], rows)
      : h("p", { class: "muted" }, "No runs yet."),
    launchPanel());
}

function launchPanel() {
  const live = health && health.server;
  const canLaunch = live && health.launch;
  const status = h("div", { "aria-live": "polite" });
  const recent = h("div");
  const backend = (value, label, checked) => h("label", {}, h("input", { type: "radio", name: "backend", value, checked }), ` ${label}`);
  const selfHosted = h("div", { class: "grid", "data-backend": "self-hosted" },
    h("label", { class: "field" }, "Model", h("select", { name: "preset" },
      (health?.presets || ["qwen3-4b-instruct", "llama-3.1-8b-instruct", "gemma-3-4b-it"]).map((p) =>
        h("option", { value: p, selected: p === "qwen3-4b-instruct" }, p)))),
    h("label", { class: "field" }, "Households per set", h("input", { type: "text", name: "limit", value: "10", inputmode: "numeric", "aria-describedby": "limit-help" })),
    h("label", { class: "field" }, "Parallel jobs", h("input", { type: "number", name: "shards", value: "1", min: 1, max: 20 })),
    h("label", { class: "field" }, "Max tokens", h("input", { type: "number", name: "max_tokens", value: "6000", min: 500, max: 16000 })));
  const openrouter = h("div", { class: "grid", "data-backend": "openrouter", hidden: true },
    h("label", { class: "field" }, "OpenRouter model", h("input", { type: "text", name: "model", value: "free", spellcheck: "false" })),
    h("label", { class: "field" }, "Households per set", h("input", { type: "text", name: "limit", value: "10", inputmode: "numeric" })),
    h("label", { class: "field" }, "Max tokens", h("input", { type: "number", name: "max_tokens", value: "8000", min: 500, max: 16000 })),
    h("label", { class: "field" }, "Reasoning effort", h("select", { name: "reasoning_effort" },
      ["", "none", "minimal", "low", "medium", "high"].map((v) => h("option", { value: v }, v || "model default")))),
    h("label", { class: "field" }, "Paid models",
      h("span", {}, h("input", { type: "checkbox", name: "allow_paid", disabled: !(health && health.allow_paid) }),
        health && health.allow_paid ? " allow (costs money)" : " off on this server")));
  const keyField = health && health.needs_key
    ? h("label", { class: "field", style: "max-width:320px" }, "Launch key", h("input", { type: "password", name: "key", autocomplete: "off" })) : null;
  const fieldset = h("fieldset", { disabled: !canLaunch },
    h("div", { class: "radio-row", role: "radiogroup", "aria-label": "Where the model runs" },
      backend("self-hosted", "Self-hosted open model ($0)", true), backend("openrouter", "OpenRouter API")),
    selfHosted, openrouter, keyField,
    h("p", { id: "limit-help", class: "muted", style: "font-size:0.8rem" }, "Households per set: a number up to 200, or \"all\". Self-hosted runs take about 5 minutes per household per job, so use 20 parallel jobs for full sets."),
    h("div", {}, h("button", { class: "button", type: "submit" }, "Launch run")));
  const form = h("form", { class: "launch" }, fieldset);
  form.addEventListener("change", (e) => {
    if (e.target.name !== "backend") return;
    for (const group of form.querySelectorAll("[data-backend]")) group.hidden = group.dataset.backend !== e.target.value;
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const choice = form.querySelector("input[name=backend]:checked").value;
    const group = form.querySelector(`[data-backend="${choice}"]`);
    const body = { backend: choice };
    for (const input of group.querySelectorAll("input, select")) {
      body[input.name] = input.type === "checkbox" ? input.checked : input.value;
    }
    const headers = { "Content-Type": "application/json" };
    const key = form.querySelector("input[name=key]");
    if (key) headers["X-Launch-Key"] = key.value;
    status.replaceChildren(h("p", { class: "notice" }, "Launching…"));
    try {
      const resp = await fetch("api/runs", { method: "POST", headers, body: JSON.stringify(body) });
      const reply = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(reply.error || `HTTP ${resp.status}`);
      status.replaceChildren(h("p", { class: "notice good" }, `Started ${reply.workflow}. Follow it on `,
        h("a", { href: reply.actions_url, rel: "noopener" }, "GitHub Actions"),
        "; its results appear here once the results PR is merged."));
      loadRecent(recent);
    } catch (err) {
      status.replaceChildren(h("p", { class: "notice bad" }, `Couldn't launch: ${err.message}`));
    }
  });
  let notice;
  if (!live) {
    notice = h("p", { class: "notice" }, "This copy is read-only. Launching runs needs the ttune viewer server: ",
      h("code", {}, "VIEWER_GITHUB_TOKEN=… python -m viewer serve"), ". Runs started there show up here after their results are merged.");
  } else if (!health.launch) {
    notice = h("p", { class: "notice" }, "This server can't launch runs: start it with VIEWER_GITHUB_TOKEN set to a token allowed to run Actions on the repo.");
  }
  if (canLaunch) loadRecent(recent);
  return h("section", { class: "card" }, h("div", { class: "head" }, h("h2", {}, "Launch a run"),
    h("p", { class: "muted" }, "Runs execute on GitHub Actions. Self-hosted models cost nothing; paid API models stay off unless the server allows them.")),
    notice, form, status, recent);
}

async function loadRecent(target) {
  try {
    const resp = await fetch("api/launches");
    if (!resp.ok) return;
    const runs = await resp.json();
    if (!runs.length) return;
    target.replaceChildren(h("h3", {}, "Recent launches"), table([["Workflow"], ["Status"], ["Started"], [""]],
      runs.map((r) => h("tr", {}, h("td", {}, r.workflow),
        h("td", {}, h("span", { class: `chip ${r.conclusion === "success" ? "good" : r.conclusion ? "bad" : "warn"}` }, r.conclusion || r.status)),
        h("td", {}, (r.created_at || "").replace("T", " ").replace("Z", " UTC")),
        h("td", {}, h("a", { href: r.url, rel: "noopener" }, "Logs"))))));
  } catch { /* the list is a convenience; ignore failures */ }
}

// --- one run ------------------------------------------------------------------------------------

async function viewRun(runId, set) {
  const base = `data/runs/${encodeURIComponent(runId)}`;
  const [ov, rows] = await Promise.all([getJSON(`${base}/overview.json`), getJSON(`${base}/${set}.json`)]);
  const s = ov.settings, info = s.model_info || {};
  const hid = ov.headline.id || {}, hood = ov.headline.ood || {};
  const floors = (key) => ["id", "ood"].map((k) => num(ov.set_info?.[k]?.floors?.[key])).join(" / ");
  const progRows = ov.programs.map(({ key, label }) => {
    const a = ov.sets.id?.programs[key] || {}, b = ov.sets.ood?.programs[key] || {};
    return h("tr", {}, h("td", {}, label),
      h("td", { class: "num" }, pct(a.balanced_accuracy)), h("td", { class: "num" }, pct(b.balanced_accuracy)),
      h("td", { class: "num" }, changeCell(ov.changes.balanced_accuracy?.[key], true)),
      h("td", { class: "num" }, `${pct(a.false_denial_rate)} → ${pct(b.false_denial_rate)}`),
      h("td", { class: "num" }, a.amount_within_tolerance === undefined ? "–" : `${pct(a.amount_within_tolerance)} → ${pct(b.amount_within_tolerance)}`));
  });
  const groupTable = (groups) => table([["Group"], ["n", "num"], ["Reward", "num"],
    ...ov.programs.map((p) => [`${p.label} bal. acc.`, "num"]), ["False denials", "num"], ["Malformed", "num"]],
    groups.map((g) => h("tr", {}, h("td", {}, g.label), h("td", { class: "num" }, g.n), h("td", { class: "num" }, num(g.reward)),
      ov.programs.map((p) => h("td", { class: "num" }, pct(g.balanced_accuracy?.[p.key]))),
      h("td", { class: "num" }, pct(g.false_denial_rate)), h("td", { class: "num" }, pct(g.malformed)))));

  show(
    h("section", {}, h("p", { class: "crumbs" }, h("a", { href: "#/" }, "Runs"), " / ", runId),
      h("div", { class: "head" }, h("h1", {}, s.model || runId),
        h("p", { class: "muted" }, [runDate(runId), info.parameters && `${info.parameters} parameters`, info.license,
          `prompt v${s.prompt_version}`, s.max_tokens && `max ${s.max_tokens} tokens`].filter(Boolean).join(" · "))),
      h("div", { class: "tiles" },
        tile("Reward, typical (ID)", num(hid.reward), `${hid.n} households`),
        tile("Reward, unusual (OOD)", num(hood.reward), `${hood.n} households`),
        tile("Change", ov.changes.reward ? signed(ov.changes.reward.change, false) : "–",
          ov.changes.reward ? `95%: ${signed(ov.changes.reward.low, false)} to ${signed(ov.changes.reward.high, false)}` : null),
        tile("False denials", `${pct(hid.false_denial_rate)} → ${pct(hood.false_denial_rate)}`, "of truly eligible decisions"),
        tile("Malformed", `${pct(hid.malformed)} / ${pct(hood.malformed)}`, "replies with no readable answer")),
      h("p", { class: "muted", style: "font-size:0.85rem" },
        `Floors, ID / OOD: always "no" scores ${floors("always_no")}; always "yes" with $0 scores ${floors("always_yes")}. ` +
        "Judge the ID → OOD change by balanced accuracy: it doesn't move with how many households qualify.")),
    h("section", {}, h("h2", {}, "By program"), table([["Program"], ["Balanced acc. ID", "num"], ["OOD", "num"],
      ["Change (95%)", "num"], ["False denials ID → OOD", "num"], ["Amounts within 5% or $10", "num"]], progRows)),
    h("section", {}, h("h2", {}, "Unusual households by shift family"), groupTable(ov.families),
      ov.twists.length ? h("details", {}, h("summary", {}, `By twist (${ov.twists.length})`), groupTable(ov.twists)) : null),
    caseSection(runId, set, rows));
}

function caseSection(runId, set, rows) {
  const filters = {
    all: ["All", () => true],
    perfect: ["Perfect", (r) => r.reward === 1],
    zero: ["Reward 0", (r) => r.reward === 0],
    denials: ["Has false denials", (r) => r.false_denials > 0],
    malformed: ["Malformed", (r) => r.malformed],
    cut_off: ["Cut off", (r) => r.cut_off],
    api_error: ["No answer (API)", (r) => r.status !== "ok"],
  };
  const families = [...new Set(rows.map((r) => r.shift))];
  const body = h("tbody");
  const count = h("span", { class: "muted", "aria-live": "polite" });
  const filterSelect = h("select", { "aria-label": "Filter cases" }, Object.entries(filters).map(([k, [label]]) => h("option", { value: k }, label)));
  const familySelect = h("select", { "aria-label": "Shift family", hidden: families.length < 2 },
    h("option", { value: "" }, "All families"), families.map((f) => h("option", { value: f }, FAMILIES[f] || f)));
  function render() {
    const keep = filters[filterSelect.value][1];
    const shown = rows.filter((r) => keep(r) && (!familySelect.value || r.shift === familySelect.value));
    count.textContent = `${shown.length} of ${rows.length} households`;
    body.replaceChildren(...shown.map((r) => {
      const href = `#/run/${encodeURIComponent(runId)}/case/${encodeURIComponent(r.id)}`;
      const go = () => { location.hash = href; };
      const flags = [r.malformed && h("span", { class: "chip bad" }, r.cut_off ? "cut off" : "malformed"),
        r.status !== "ok" && h("span", { class: "chip warn" }, "no answer"),
        r.false_denials > 0 && h("span", { class: "chip bad" }, `${r.false_denials} false denial${r.false_denials > 1 ? "s" : ""}`),
        r.reward === 1 && h("span", { class: "chip good" }, "perfect")];
      return h("tr", { class: "link", tabindex: 0, onclick: go, onkeydown: (e) => { if (e.key === "Enter") go(); } },
        h("td", {}, h("a", { href, class: "mono" }, r.id)),
        h("td", { class: "wrap-cell" }, h("span", { class: "chip" }, FAMILIES[r.shift] || r.shift), r.twists.map((t) => h("span", { class: "chip" }, t))),
        h("td", { class: "num" }, r.reward === null ? "–" : [h("span", { class: "bar", "aria-hidden": "true" }, h("span", { style: `width:${Math.round(r.reward * 100)}%` })), num(r.reward)]),
        h("td", { class: "wrap-cell" }, flags));
    }));
  }
  filterSelect.addEventListener("change", render);
  familySelect.addEventListener("change", render);
  render();
  const tabs = h("div", { class: "tabs", role: "group", "aria-label": "Household set" }, Object.entries(SETS).map(([k, label]) =>
    h("button", { type: "button", "aria-pressed": String(k === set), onclick: () => { location.hash = `#/run/${encodeURIComponent(runId)}/set/${k}`; } }, label)));
  return h("section", {}, h("h2", {}, "Cases"), h("div", { class: "controls" }, tabs, filterSelect, familySelect, count),
    h("div", { class: "table-scroll cases" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Household"), h("th", {}, "Family and twists"),
      h("th", { class: "num" }, "Reward"), h("th", {}, "Flags"))), body)));
}

// --- one case -----------------------------------------------------------------------------------

function verdict(truthYes, answered) {
  if (answered === null || answered === undefined) return h("span", { class: "muted" }, "no answer");
  if (answered === "unknown") return h("span", { class: "muted" }, "unknown");
  if (answered === truthYes) return h("span", { class: "mark-right" }, "✓ right");
  return h("span", { class: "mark-wrong" }, truthYes ? "✗ false denial" : "✗ false approval");
}
const yesNo = (v) => (v === "unknown" ? "unknown" : v === null || v === undefined ? "–" : v ? "yes" : "no");

async function viewCase(runId, caseId) {
  const base = `data/runs/${encodeURIComponent(runId)}`;
  const set = caseId.split("-")[0];
  const [c, rows, ov] = await Promise.all([getJSON(`${base}/cases/${encodeURIComponent(caseId)}.json`),
    getJSON(`${base}/${set}.json`), getJSON(`${base}/overview.json`)]);
  const at = rows.findIndex((r) => r.id === caseId);
  const neighbour = (i) => (rows[i] ? h("a", { href: `#/run/${encodeURIComponent(runId)}/case/${encodeURIComponent(rows[i].id)}` }, i < at ? `← ${rows[i].id}` : `${rows[i].id} →`) : h("span"));
  const ok = c.status === "ok";
  const ans = ok ? c.answer : null;
  const truth = c.truth || {};
  const verdictRows = [];
  for (const [key, label] of PROGRAMS) {
    if (key === "snap" || key === "eitc") {
      const t = truth[key] || {};
      const a = ans && ans[key];
      const tAmount = key === "snap" ? t.monthly_benefit : t.annual_amount;
      const unit = key === "snap" ? "/mo" : "/yr";
      verdictRows.push(h("tr", {}, h("td", {}, label), h("td", {}, "Household"),
        h("td", {}, a ? [yesNo(a.eligible), a.eligible === true ? ` · ${money(a.amount)}${unit}` : ""] : "–"),
        h("td", {}, yesNo(t.eligible), t.eligible ? ` · ${money(tAmount)}${unit}` : ""),
        h("td", {}, verdict(Boolean(t.eligible), a ? a.eligible : null),
          t.eligible && ok ? h("div", { class: "muted" }, `amount score ${num(c.score.programs[key].amount_score)}`) : null)));
    } else {
      const listed = new Set(ans ? ans[key].members : []);
      const eligible = new Set((truth[key] || {}).eligible_members || []);
      c.members.forEach((m, i) => {
        verdictRows.push(h("tr", {}, h("td", {}, i === 0 ? label : ""), h("td", {}, `${m.name}, ${m.age}`),
          h("td", {}, ans ? yesNo(listed.has(m.id)) : "–"), h("td", {}, yesNo(eligible.has(m.id))),
          h("td", {}, verdict(eligible.has(m.id), ans ? listed.has(m.id) : null))));
      });
      const unknown = ans ? ans[key].unknown_names : [];
      if (unknown && unknown.length) verdictRows.push(h("tr", {}, h("td", {}), h("td", { class: "wrap-cell muted", colspan: 4 }, `Names not in the case: ${unknown.join(", ")}`)));
    }
  }
  const reply = h("pre", { class: "text reply" }, c.reply || "(empty reply)");
  const usage = c.usage || {};
  show(
    h("section", {}, h("p", { class: "crumbs" }, h("a", { href: "#/" }, "Runs"), " / ",
      h("a", { href: `#/run/${encodeURIComponent(runId)}/set/${set}` }, ov.settings.model || runId), " / ", caseId),
      h("div", { class: "pager" }, neighbour(at - 1), neighbour(at + 1)),
      h("div", { class: "head" }, h("h1", {}, caseId),
        h("p", {}, h("span", { class: "chip" }, SETS[set]), h("span", { class: "chip" }, FAMILIES[c.shift] || c.shift),
          c.twists.map((t) => h("span", { class: "chip" }, t)), c.state ? h("span", { class: "chip" }, c.state) : null)),
      h("div", { class: "tiles" },
        tile("Reward", ok ? num(c.score.reward) : "–", ok && c.score.malformed ? "malformed reply scores 0" : null),
        tile("Eligibility", ok ? num(c.score.eligibility) : "–", "false denials count double"),
        tile("Amounts", ok ? num(c.score.amount) : "–", "SNAP and EITC, when eligible"),
        tile("Tokens", usage.completion_tokens ? usage.completion_tokens.toLocaleString("en-US") : "–",
          c.finish_reason === "length" ? "cut off at the limit" : (usage.prompt_tokens ? `${usage.prompt_tokens.toLocaleString("en-US")} in` : null)))),
    !ok ? h("p", { class: "notice bad" }, `The API never answered this case: ${c.api_error || ""}`) : null,
    ok && c.parse_error ? h("p", { class: "notice bad" }, `No readable answer: ${c.parse_error}`) : null,
    h("div", { class: "split" },
      h("section", { class: "card" }, h("h2", {}, "What the model saw"), h("pre", { class: "text" }, c.case || "(case text not found)")),
      h("section", { class: "card" }, h("h2", {}, "Model vs PolicyEngine"),
        h("div", { class: "verdict" }, table([["Program"], ["Who"], ["Model says"], ["PolicyEngine"], ["Result"]], verdictRows)))),
    h("section", { class: "card" }, h("div", { class: "controls" }, h("h2", {}, "Full reply"),
      h("button", { type: "button", class: "link-button", onclick: (e) => { reply.classList.toggle("open"); e.target.textContent = reply.classList.contains("open") ? "Collapse" : "Show all"; } }, "Show all")),
      reply));
}

// --- routing ------------------------------------------------------------------------------------

async function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  try {
    if (parts[0] === "run" && parts[1] && parts[2] === "case" && parts[3]) await viewCase(parts[1], parts[3]);
    else if (parts[0] === "run" && parts[1]) await viewRun(parts[1], parts[2] === "set" && parts[3] === "ood" ? "ood" : "id");
    else await viewRuns();
    window.scrollTo(0, 0);
  } catch (err) {
    show(h("p", { class: "error" }, `Couldn't load this page: ${err.message}`), h("p", {}, h("a", { href: "#/" }, "Back to runs")));
  }
}

(async function start() {
  // The static build writes data/site.json with "static": true, so it never asks for an API that isn't there.
  const site = await getJSON("data/site.json").catch(() => ({}));
  if (!site.static) {
    try {
      const resp = await fetch("api/health");
      if (resp.ok) health = await resp.json();
    } catch { /* no server */ }
  }
  const mode = document.getElementById("mode");
  mode.hidden = false;
  mode.textContent = health && health.server ? "Live server" : "Read-only";
  if (health && health.server) mode.classList.add("live");
  window.addEventListener("hashchange", route);
  route();
})();

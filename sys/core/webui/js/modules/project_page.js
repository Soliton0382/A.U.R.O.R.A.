// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📁 One project's page, the Models page's way (owner, 23 Oct: «le pagine mi sembrano incasinate e il concetto usato
// fino ad ora che parte dalla struttura della pagina modelli mi piace»): its name, how it is handled and whether all
// is saved on top; then a row of sections, one shown at a time, in the order of the work: talk to the conductor, the
// plan, the documents, the model seen built, the simulators, the files, the 3D print, the terminal, the history,
// Aurora's reports, the preview. A section is made the first time it is opened and kept (a terminal stays open while
// the others are looked at); the last one opened is remembered on this device for this project.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { policyBox } from "./project_policy.js";
import { conductView } from "./project_conduct.js";
import { planView } from "./project_plan.js";
import { docsView } from "./project_docs.js";
import { filesView } from "./project_files.js";
import { printView } from "./project_print.js";
import { renderView } from "./project_render.js";
import { simView } from "./project_sim.js";
import { terminalView } from "./project_term.js";

// section → its label (existing keys) and whether it is made again each time it is opened (fresh lists)
const SECTIONS = [["conduct", "conduct.button"], ["plan", "plan.button"], ["docs", "docs.button"], ["render", "prj.render"],
  ["sim", "prj.sim"], ["files", "prj.tab_files"],
  ["print", "prj.print"], ["term", "prj.term"], ["history", "prj.history", true], ["reports", "prj.reports", true],
  ["preview", "prj.preview", true]];
// the sections in three groups (owner, 23 Oct: «dentro il progetto le diverse sezioni sembrano incasinate»): a row of
// groups, then the row of the chosen group's sections — two short rows instead of eleven chips over four lines
const GROUPS = [["work", "prj.g_work", ["conduct", "plan", "term", "reports"]],
  ["model", "prj.g_model", ["docs", "render", "sim", "print"]],
  ["files", "prj.g_files", ["files", "history", "preview"]]];
const groupOf = (id) => GROUPS.find(([, , ids]) => ids.includes(id))?.[0] || "work";

async function history(name) {
  const { commits } = await call(`/v1/aurora/projects/${name}/log`);
  return [el("h4", "", t("prj.history")), ...(commits.length ? commits.map((c) => {
    const r = el("div", "ev");
    r.append(el("code", "", c.hash), el("span", "muted", clock(c.date)), el("span", "", c.subject), el("span", "muted", c.author));
    return r;
  }) : [el("p", "muted", t("prj.no_history"))])];
}

// Aurora's reports on this project (owner, 2026-10-05): her considerations, beside the alerts and the chat
async function reports(name) {
  const items = await call(`/v1/aurora/projects/${name}/reports`);
  return [el("h4", "", t("prj.reports")), ...(items.length ? items.map((r, i) => {
    const box = el("details", "report");
    box.open = i === 0;
    box.append(el("summary", "", `${clock(r.at)} · ${t("prj.report_meta", { steps: r.steps ?? "?", min: Math.round((r.seconds || 0) / 60) })}`),
      renderMarkdown(r.summary || ""));
    return box;
  }) : [el("p", "muted", t("prj.no_reports"))])];
}

async function preview(name) {
  const { url } = await call(`/v1/aurora/projects/${name}/preview`, { method: "POST", body: "{}" });
  const f = el("iframe", "prj-frame");
  f.setAttribute("sandbox", "allow-scripts allow-forms allow-popups");   // opaque origin: no cookie, no API
  f.setAttribute("referrerpolicy", "no-referrer");
  f.src = url;
  return [el("p", "muted", t("prj.preview_note")), f];
}

export function openProject(d, p, { base, back }) {
  const name = p.name;
  d.innerHTML = `
    <div class="ev prj-bar"><button class="back"></button><h3></h3></div>
    <div class="prj-tabs prj-groups">${GROUPS.map(([g, label]) => `<button type="button" class="cat-chip" data-group="${g}" data-i18n="${label}"></button>`).join("")}</div>
    <div class="prj-tabs prj-sections">${SECTIONS.map(([id, label]) => `<button type="button" class="cat-chip" data-tab="${id}" data-group="${groupOf(id)}" data-i18n="${label}"></button>`).join("")}</div>
    ${SECTIONS.map(([id]) => `<div class="prj-section md-tab" data-tab="${id}" hidden></div>`).join("")}`;
  apply(d);
  d.querySelector("h3").textContent = `📁 ${name}`;
  d.querySelector(".back").textContent = t("prj.back");
  d.querySelector(".back").addEventListener("click", back);
  // the policy beside the save state, on one row; a page opened again meanwhile (a double tap) keeps its own only
  const saveRow = el("div", "prj-save-row");
  policyBox(name).then((b) => { if (saveRow.isConnected) saveRow.prepend(b); });
  // 💾 what «saved» means: the project's history (git commits) — said here, and done with one click
  const saveBox = el("div", "prj-save");
  const drawSave = (changes) => {
    const st = el("span", changes ? "prj-state warn" : "prj-state ok", changes ? t("prj.changes", { n: changes }) : t("prj.clean"));
    st.title = t(changes ? "prj.changes_hint" : "prj.clean_hint");
    const b = el("button", changes ? "approve" : "", t("prj.save"));
    b.title = t("prj.save_hint");
    b.disabled = !changes;
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await call(`/v1/aurora/projects/${name}/save`, { method: "POST", body: JSON.stringify({ message: prompt(t("prj.save_q"), "") || "" }) });
        drawSave(0);
      } catch (e) { b.textContent = t("ev.error", { m: e.message }); }
    });
    saveBox.replaceChildren(st, b);
  };
  drawSave(p.changes || 0);
  saveRow.append(saveBox);
  d.querySelector(".prj-groups").before(saveRow);
  const pane = (id) => d.querySelector(`.prj-section[data-tab="${id}"]`);
  let files = null;
  const fileSection = () => { if (!files) { files = filesView(name, base); pane("files").append(files.box); } return files; };
  const make = {
    conduct: () => [conductView(name)],          // 🧑‍🔬 plain words → a phase's goal → the agent → a reply (N39)
    plan: () => [planView(name)],                // 🏗️ the project carried by Aurora, step by step (ROADMAP 97)
    docs: () => [docsView(name, (path) => { show("files"); fileSection().show(path); })],   // 📑 blueprints, patents (100)
    render: () => [renderView(name)],            // 🎨 the model seen built, in a studio light (N42)
    sim: () => [simView(name)],                  // 🧮 the project's simulators: parameters → results (N42)
    files: () => { fileSection(); return null; },
    print: () => [printView(name)],              // 🖨️ the models for a 3D printer (N41)
    term: () => [terminalView(name)],            // 🖥️ the project run in its cage (roadmap 75)
    history: () => history(name), reports: () => reports(name), preview: () => preview(name),
  };
  const key = `aurora.prj.tab.${name}`;
  const show = async (id) => {
    const g = groupOf(id);
    d.querySelectorAll(".prj-groups button").forEach((b) => b.classList.toggle("on", b.dataset.group === g));
    d.querySelectorAll(".prj-sections button").forEach((b) => { b.classList.toggle("on", b.dataset.tab === id); b.hidden = b.dataset.group !== g; });
    d.querySelectorAll(".prj-section").forEach((x) => { x.hidden = x.dataset.tab !== id; });
    try { localStorage.setItem(key, id); localStorage.setItem(`${key}.${g}`, id); } catch { /* not kept */ }
    const box = pane(id);
    const again = SECTIONS.find(([s]) => s === id)?.[2];
    if (box.dataset.made && !again) return;
    box.dataset.made = "1";
    if (again) box.replaceChildren(el("p", "muted", t("prj.loading")));
    try {
      const nodes = await make[id]();
      if (nodes) box.replaceChildren(...nodes);
    } catch (e) { box.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
  };
  d.querySelectorAll(".prj-sections button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  // a group opens its section seen last on this device, else its first
  d.querySelectorAll(".prj-groups button").forEach((b) => b.addEventListener("click", () => {
    const ids = GROUPS.find(([g]) => g === b.dataset.group)[2];
    let last = null;
    try { last = localStorage.getItem(`${key}.${b.dataset.group}`); } catch { /* the first */ }
    show(ids.includes(last) ? last : ids[0]);
  }));
  let first = "conduct";
  try { first = localStorage.getItem(key) || first; } catch { /* the conductor first */ }
  show(make[first] ? first : "conduct");
}

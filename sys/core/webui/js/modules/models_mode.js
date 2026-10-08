// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧭 Models → Modalità (owner, 2026-10-08: «massima libertà di configurazione, con indicazioni su dove possono essere i
// rischi… se si vuole tutto Cloud allora si indica con triangolo giallo e popup e si indica di eseguire il comando da
// Shell»): local, mixed, cloud with privacy, all cloud; every aspect checked in each (mdl_modes.check); what the owner
// must do from a shell (the exemption, the consent) in a popup with the command to copy; the local reasoner on/off.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { lang, t } from "../i18n.js";
import { restartPrompt } from "../restart.js";

useCss("/static/css/models_mode.css");

const MODES = [
  { id: "local", icon: "🏠" }, { id: "mixed", icon: "🔀" },
  { id: "cloud_private", icon: "☁️🔒" }, { id: "cloud_full", icon: "☁️", risky: true },
];
const MARK = { ok: "✅", stay: "🔒", warn: "⚠️", no: "⛔" };

function words(o) { return (String(lang).startsWith("it") ? o.it : o.en) || ""; }

// a popup: the reason, and the command to run in a shell (copied with one tap)
export function shellPopup(title, text, command) {
  const dlg = el("dialog", "modal");
  dlg.append(el("h3", "", title), el("p", "", text));
  if (command) {
    const row = el("div", "mm-cmd");
    const code = el("code", "", command);
    const copy = el("button", "", `📋 ${t("mm.copy")}`);
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(command); copy.textContent = `✔ ${t("mm.copied")}`; }
      catch { getSelection().selectAllChildren(code); }
    });
    row.append(code, copy);
    dlg.append(el("p", "muted", t("mm.shell_where")), row, el("p", "muted", t("mm.shell_after")));
  }
  const close = el("button", "", t("mm.close"));
  close.addEventListener("click", () => { dlg.close(); dlg.remove(); });
  dlg.append(el("div", "appr-actions"), close);
  document.body.append(dlg);
  dlg.showModal();
}

function confirmRisk(title, text) {
  return new Promise((done) => {
    const dlg = el("dialog", "modal");
    dlg.append(el("h3", "", title), el("p", "mm-warn", text));
    const yes = el("button", "approve", t("mm.go_on")), no = el("button", "", t("mm.cancel"));
    const row = el("div", "appr-actions");
    row.append(yes, no);
    dlg.append(row);
    document.body.append(dlg);
    dlg.showModal();
    const end = (v) => { dlg.close(); dlg.remove(); done(v); };
    yes.addEventListener("click", () => end(true));
    no.addEventListener("click", () => end(false));
  });
}

export async function renderModes(box, providers, onChange) {
  let s;
  try { s = await call("/v1/aurora/models/modes"); } catch (e) { box.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
  box.replaceChildren(el("h3", "setting-cat", t("mm.title")), el("p", "muted", t("mm.hint")));

  // the provider and model the cloud modes use (the cloud default: AURORA_CLOUD_PROVIDER / MODEL)
  const pick = el("div", "mm-pick");
  const prov = el("select");
  prov.id = "mm-provider";
  for (const p of providers.filter((x) => x.id !== "local")) {
    const o = el("option", "", `${p.label}${p.configured ? "" : " — " + t("mm.no_key")}`);
    o.value = p.id;
    o.selected = p.id === s.provider;
    prov.append(o);
  }
  const model = el("input");
  model.id = "mm-model";
  model.value = s.model;
  model.placeholder = t("mm.model");
  model.setAttribute("list", "mm-models");
  const list = el("datalist");
  list.id = "mm-models";
  const fetchList = el("button", "", `📋 ${t("mm.list")}`);
  fetchList.addEventListener("click", async () => {
    fetchList.disabled = true;
    try {
      const r = await call(`/v1/aurora/models/${encodeURIComponent(prov.value)}/list`);
      list.replaceChildren(...(r.models || []).map((m) => { const o = el("option"); o.value = m; return o; }));
      fetchList.textContent = `📋 ${(r.models || []).length}`;
    } catch (e) { fetchList.textContent = `⛔ ${e.message.slice(0, 60)}`; }
    fetchList.disabled = false;
  });
  pick.append(el("span", "muted", t("mm.cloud_with")), prov, model, list, fetchList);

  // the four modes
  const modes = el("div", "mm-modes");
  for (const m of MODES) {
    const b = el("button", `mm-mode${s.mode === m.id ? " now" : ""}${m.risky ? " risky" : ""}`);
    b.append(el("strong", "", `${m.icon} ${t(`mm.${m.id}`)}`), el("span", "", t(`mm.${m.id}_hint`)));
    if (s.mode === m.id) b.append(el("span", "", `● ${t("mm.now")}`));
    b.addEventListener("click", () => choose(m.id));
    modes.append(b);
  }

  async function choose(mode) {
    if (mode === "mixed") { document.querySelector(".md-roles")?.scrollIntoView({ behavior: "smooth" }); return; }
    if (mode === "cloud_full" && !(await confirmRisk(`☁️ ${t("mm.cloud_full")} ⚠️`, t("mm.full_risk")))) return;
    try {
      const r = await call("/v1/aurora/models/mode", { method: "POST",
        body: JSON.stringify({ mode, provider: prov.value, model: model.value.trim() }) });
      if (r.restart && r.restart.length) await restartPrompt(r.restart);
      onChange();
    } catch (e) { explain(e); }
  }

  // the table: each aspect in each mode, and what it is now
  const head = el("tr");
  for (const h of [t("mm.aspect"), t("mm.local"), t("mm.cloud_private"), t("mm.cloud_full"), t("mm.now")]) head.append(el("th", "", h));
  const body = el("tbody");
  for (const a of s.aspects) {
    const tr = el("tr");
    tr.append(el("td", "", words(a)));
    for (const m of ["local", "cloud_private", "cloud_full"]) {
      const c = a.modes[m], td = el("td", "mm-cell");
      td.append(el("span", `mm-st ${c.state}`, MARK[c.state] || ""), el("small", "", words(c)));
      tr.append(td);
    }
    tr.append(el("td", "muted", a.now));
    body.append(tr);
  }
  const table = el("table", "mm-table");
  const thead = el("thead");
  thead.append(head);
  table.append(thead, body);
  const wrap = el("div", "mm-table-wrap");
  wrap.append(table);
  const legend = el("p", "muted", t("mm.legend"));

  // what is still needed for the cloud modes: each with its command
  const needs = el("div", "mm-needs");
  for (const n of s.needs) {
    const row = el("div", "mm-cmd");
    row.append(el("span", "mm-warn", `⚠️ ${words(n)}`));
    if (n.command) {
      const how = el("button", "", t("mm.how"));
      how.addEventListener("click", () => shellPopup(`⚠️ ${t(`mm.need_${n.need}`)}`, words(n), n.command));
      row.append(how);
    }
    needs.append(row);
  }

  // the local reasoner: on (private data stays here) or off (the GPU free, Aurora reasons in the cloud)
  const reasoner = el("div", "mm-reasoner");
  if (s.can_have_local || s.local_reasoner) {
    reasoner.append(el("span", "", `🖥️ ${t(s.local_reasoner ? "mm.reasoner_on" : "mm.reasoner_off")}`));
    const flip = el("button", s.local_reasoner ? "" : "approve", t(s.local_reasoner ? "mm.turn_off" : "mm.turn_on"));
    flip.addEventListener("click", async () => {
      if (s.local_reasoner && !(await confirmRisk(`🖥️ ${t("mm.turn_off")}`, t("mm.off_risk")))) return;
      try {
        const r = await call("/v1/aurora/models/reasoner", { method: "POST", body: JSON.stringify({ on: !s.local_reasoner }) });
        await restartPrompt(r.restart);
        onChange();
      } catch (e) { explain(e); }
    });
    reasoner.append(flip);
  }
  box.append(modes, pick, needs, wrap, legend, reasoner);
}

function explain(e) {
  let d = null;
  try { d = JSON.parse(e.message); } catch { /* a plain message */ }
  if (typeof d === "string") shellPopup(`⚠️ ${t("mm.cannot")}`, d, "");
  else if (d && typeof d === "object") shellPopup(`⚠️ ${t(`mm.need_${d.need}`) || t("mm.cannot")}`, d.message, d.command);
  else shellPopup(`⚠️ ${t("mm.cannot")}`, e.message, "");
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → 🎛️ the values advised (ROADMAP N28; owner, 16 Oct: «una tabella di valori consigliati… con possibilità di
// modificarli… se l'attrezzatura non è correttamente dimensionata»): the API's rows (ast_advice) — what is set, what
// Aurora advises, the person's own value, whether it fits and why with its numbers — the facts only the person knows,
// and the N.I.N.A. sequences checked against the darks. Nothing is set on the telescope's PC: the table says where.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const MARK = { ok: "✅", warn: "⚠️", bad: "❌", unknown: "❓", info: "ℹ️" };
const GROUPS = ["sampling", "guiding", "dither", "meridian", "mount", "camera"];
const show = (v) => (v == null || v === "" ? "—" : typeof v === "number" ? String(Math.round(v * 100) / 100) : String(v));

function factsForm(d, save) {
  const box = el("details", "aa-facts");
  const missing = d.facts_spec.filter((f) => d.facts[f.key] == null).length;
  box.open = missing > 6;
  box.append(el("summary", "", `📐 ${t("aa.facts")}${missing ? ` · ${t("aa.facts_missing", { n: missing })}` : ""}`));
  box.append(el("p", "muted", t("aa.facts_hint")));
  const grid = el("div", "aa-grid");
  for (const f of d.facts_spec) {
    const lab = el("label", "aa-fact");
    lab.append(el("span", "", `${t(`aa.fact.${f.key}`)}${f.unit ? ` (${f.unit})` : ""}`));
    let inp;
    if (f.choices) {
      inp = el("select");
      inp.append(el("option", "", "—"));
      inp.firstChild.value = "";
      for (const c of f.choices) { const o = el("option", "", t(`aa.fact.${f.key}.${c}`)); o.value = c; inp.append(o); }
      inp.value = d.facts[f.key] ?? "";
    } else {
      inp = el("input");
      inp.type = "number";
      inp.step = "any";
      inp.value = d.facts[f.key] ?? "";
      if (f.default != null) inp.placeholder = String(f.default);
    }
    inp.name = f.key;
    lab.append(inp);
    grid.append(lab);
  }
  box.append(grid);
  const btn = el("button", "btn", `💾 ${t("aa.save")}`);
  btn.type = "button";
  btn.addEventListener("click", () => {
    const facts = {};
    grid.querySelectorAll("input,select").forEach((i) => { facts[i.name] = i.value; });
    save({ facts });
  });
  box.append(btn);
  return box;
}

function rowsTable(d, save) {
  const wrap = el("div", "an-wrap");
  const table = el("table", "an-table aa-table");
  const head = el("tr", "aa-head");
  for (const k of ["param", "now", "advised", "mine", "state"]) head.append(el("th", "", t(`aa.col.${k}`)));
  table.append(head);
  for (const g of GROUPS) {
    const rows = d.rows.filter((r) => r.group === g);
    if (!rows.length) continue;
    const gh = el("tr", "aa-group");
    gh.append(Object.assign(el("th", "", t(`aa.g.${g}`)), { colSpan: 5 }));
    table.append(gh);
    for (const r of rows) {
      const tr = el("tr", `aa-${r.status}`);
      const name = el("td");
      name.append(el("strong", "", t(`aa.k.${r.key}`)), el("br"), el("small", "muted", t(`aa.where.${r.where}`)));
      const mine = el("td");
      if (r.status !== "info" && r.advised != null) {
        const inp = el("input", "aa-mine");
        inp.value = (r.fact ? r.current : r.choice) ?? "";      // a fact's row: the box is the fact itself
        inp.placeholder = "—";
        inp.setAttribute("aria-label", t(r.fact ? `aa.fact.${r.fact}` : "aa.col.mine"));
        inp.addEventListener("change", () => save(r.fact ? { facts: { [r.fact]: inp.value.trim() } }
          : { choices: { [r.key]: inp.value.trim() } }));
        mine.append(inp);
      }
      const cell = (k, v) => el("td", `aa-${k}`, v);
      const SRC = { live: "🟢", inventory: "📄", measured: "📏", fact: "✍️" };
      const now = cell("now", `${show(r.current)} ${r.current == null ? "" : r.unit}`.trim() + (r.current == null ? "" : ` ${SRC[r.src] || ""}`));
      now.title = t(`aa.src.${r.src || "inventory"}`);
      const adv = cell("adv", `${show(r.advised)} ${r.advised == null ? "" : r.unit}`.trim());
      now.dataset.label = t("aa.col.now");
      adv.dataset.label = t("aa.col.advised");
      mine.className = "aa-minecell";
      name.className = "aa-name";
      tr.append(name, now, adv, mine, el("td", "aa-state", `${MARK[r.status] || ""}${r.choice ? " ✋" : ""}`));
      const why = el("tr", "aa-why");
      why.append(Object.assign(el("td", "muted", t(`aa.w.${r.why}`, { ...r.n, unit: r.unit, now: show(r.current), cw: r.key === "payload" ? (r.n.cw ? t("aa.with_cw") : "") : r.n.cw })), { colSpan: 5 }));
      table.append(tr, why);
    }
  }
  wrap.append(table);
  return wrap;
}

function sequences(d) {
  const box = el("div", "aa-seqs");
  if (!d.sequences.length) { box.append(el("p", "muted", t("aa.seq_none"))); return box; }
  for (const q of d.sequences) {
    const bad = q.findings?.length;
    const det = el("details", "an-night");
    const exp = (q.exposures || []).map((e) => `${e.s}s g${e.gain === -1 ? "*" : e.gain} o${e.offset === -1 ? "*" : e.offset}`).join(", ");
    det.append(el("summary", "", `${bad ? (q.findings.some((f) => f.level === "high") ? "❌" : "⚠️") : "✅"} ${q.name}${exp ? ` · ${exp}` : ""}`));
    const ul = el("ul", "an-findings");
    ul.append(...(bad ? q.findings.map((f) => el("li", "", `${MARK[f.level === "high" ? "bad" : "warn"]} ${t(`aa.s.${f.code}`, { ...f, darks: (f.darks || []).join(", ") })}`))
      : [el("li", "muted", t("aa.seq_ok"))]));
    det.append(ul);
    box.append(det);
  }
  return box;
}

export async function adviceTab(box) {
  const draw = (d) => {
    const s = d.summary;
    box.replaceChildren(el("p", "muted", t("aa.hint")));
    if (!d.inventory) { box.append(el("p", "warn", t("aa.no_inventory"))); return; }
    box.append(el("p", "aa-sum", `✅ ${s.ok} · ⚠️ ${s.warn} · ❌ ${s.bad} · ❓ ${s.unknown}`));
    const lv = d.live || {};
    box.append(el("p", "muted", lv.phd2 || lv.nina
      ? t("aa.live_on", { what: [lv.phd2 && "PHD2", lv.nina && "N.I.N.A."].filter(Boolean).join(" + "), when: new Date(lv.at * 1000).toLocaleTimeString(), w: d.written })
      : t("aa.live_off", { w: d.written })));
    box.append(factsForm(d, save), rowsTable(d, save));
    box.append(el("h4", "", `🗂️ ${t("aa.sequences")}`), sequences(d));
  };
  const save = async (body) => {
    try { draw(await call("/v1/aurora/astro/advice", { method: "PUT", body: JSON.stringify(body) })); } catch (e) { box.prepend(el("p", "warn", e.message)); }
  };
  box.replaceChildren(el("p", "muted", "…"));
  try { draw(await call("/v1/aurora/astro/advice")); } catch (e) { box.replaceChildren(el("p", "warn", e.message)); }
}

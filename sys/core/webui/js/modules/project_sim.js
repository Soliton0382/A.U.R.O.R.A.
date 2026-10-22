// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧮 A project's simulators (ROADMAP N42, prj_sim): the files in sim/ — parameters on sliders, the outputs computed
// while they move, one chart per plotted output (one axis each) with the current value marked and a crosshair; the
// notes say what the model leaves out. Values are kept on this device per project and simulator.
import { call } from "../api.js";
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { compile, evaluate } from "./project_sim_expr.js";

const SVGNS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const fmt = (v, digits) => (Number.isFinite(v)
  ? new Intl.NumberFormat(lang, { maximumSignificantDigits: digits }).format(v) : "—");

function chart(sim, out, values, compiled) {
  const p = sim.params.find((x) => x.id === sim.plot.x);
  const W = 420, H = 190, L = 56, R = 12, T = 12, B = 34, n = 80;
  const xs = Array.from({ length: n + 1 }, (_, i) => p.min + ((p.max - p.min) * i) / n);
  const ys = xs.map((x) => evaluate(sim, { ...values, [p.id]: x }, compiled)[out.id]);
  const ok = ys.filter(Number.isFinite);
  const box = el("figure", "sim-chart");
  box.append(el("figcaption", "", `${out.label}${out.unit ? ` (${out.unit})` : ""} — ${p.label}`));
  if (!ok.length) { box.append(el("p", "muted", "—")); return box; }
  let lo = Math.min(...ok), hi = Math.max(...ok);
  if (lo > 0 && lo < hi * 0.5) lo = 0;                    // magnitudes from zero when it is near
  if (hi === lo) { hi += Math.abs(hi) || 1; lo -= Math.abs(lo) || 1; }
  const X = (x) => L + ((x - p.min) / (p.max - p.min)) * (W - L - R);
  const Y = (y) => T + (1 - (y - lo) / (hi - lo)) * (H - T - B);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "sim-svg", role: "img" });
  for (let k = 0; k <= 4; k++) {                          // recessive grid, labels in muted ink
    const v = lo + ((hi - lo) * k) / 4, y = Y(v);
    s.append(svg("line", { x1: L, x2: W - R, y1: y, y2: y, class: "sim-rule" }));
    const tx = svg("text", { x: L - 6, y: y + 4, "text-anchor": "end", class: "sim-tick" });
    tx.textContent = fmt(v, 3);
    s.append(tx);
  }
  for (let k = 0; k <= 4; k++) {
    const v = p.min + ((p.max - p.min) * k) / 4;
    const tx = svg("text", { x: X(v), y: H - B + 16, "text-anchor": "middle", class: "sim-tick" });
    tx.textContent = fmt(v, 3);
    s.append(tx);
  }
  const unitX = svg("text", { x: W - R, y: H - 4, "text-anchor": "end", class: "sim-tick" });
  unitX.textContent = `${p.label}${p.unit ? ` (${p.unit})` : ""}`;
  s.append(unitX);
  let d = "", pen = false;
  xs.forEach((x, i) => {
    if (!Number.isFinite(ys[i])) { pen = false; return; }
    d += `${pen ? "L" : "M"}${X(x).toFixed(1)},${Y(ys[i]).toFixed(1)}`;
    pen = true;
  });
  s.append(svg("path", { d, class: "sim-line" }));
  const now = evaluate(sim, values, compiled)[out.id];
  if (Number.isFinite(now)) s.append(svg("circle", { cx: X(values[p.id]), cy: Y(now), r: 5, class: "sim-dot" }));
  const cross = svg("line", { y1: T, y2: H - B, class: "sim-cross", visibility: "hidden" });
  const tip = el("div", "sim-tip");
  tip.hidden = true;
  s.append(cross);
  const hit = svg("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" });
  hit.addEventListener("pointermove", (ev) => {
    const r = s.getBoundingClientRect();
    const x = ((ev.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(n, Math.round(((x - L) / (W - L - R)) * n)));
    cross.setAttribute("x1", X(xs[i])); cross.setAttribute("x2", X(xs[i])); cross.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.textContent = `${p.label} ${fmt(xs[i], 4)} ${p.unit} → ${fmt(ys[i], out.digits)} ${out.unit}`;
  });
  hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; });
  s.append(hit);
  box.append(s, tip);
  return box;
}

function simCard(project, sim) {
  const box = el("div", "sim-card");
  if (sim.error) { box.append(el("h4", "", `🧮 ${sim.name}`), el("p", "error", t("prj.sim_bad", { m: sim.error }))); return box; }
  const compiled = {};
  for (const o of sim.outputs) {
    try { compiled[o.id] = compile(o.expr); } catch (e) { compiled[o.id] = () => NaN; console.warn(o.id, e.message); }
  }
  const key = `aurora.prj.sim.${project}.${sim.name}`;
  const start = Object.fromEntries(sim.params.map((p) => [p.id, p.value]));
  let values = { ...start };
  try {
    const kept = JSON.parse(localStorage.getItem(key) || "{}");
    for (const p of sim.params) if (Number.isFinite(kept[p.id]) && kept[p.id] >= p.min && kept[p.id] <= p.max) values[p.id] = kept[p.id];
  } catch { /* the file's values */ }
  box.append(el("h4", "", `🧮 ${sim.title || sim.name}`));
  const grid = el("div", "sim-grid");
  const inputs = el("div", "sim-params"), outputs = el("table", "sim-out"), charts = el("div", "sim-charts");
  grid.append(inputs, outputs);
  const rows = {};
  let group = null;
  for (const p of sim.params) {
    if (p.group && p.group !== group) { group = p.group; inputs.append(el("h5", "", group)); }
    const row = el("label", "sim-param");
    const name = el("span", "", p.label);
    const range = el("input"), num = el("input");
    for (const i of [range, num]) Object.assign(i, { min: p.min, max: p.max, step: p.step, value: values[p.id] });
    range.type = "range"; num.type = "number"; num.className = "sim-num";
    const set = (v) => {
      v = Math.min(p.max, Math.max(p.min, Number(v)));
      if (!Number.isFinite(v)) return;
      values[p.id] = v; range.value = v; num.value = v;
      redraw();
    };
    range.addEventListener("input", () => set(range.value));
    num.addEventListener("change", () => set(num.value));
    row.append(name, range, num, el("span", "muted", p.unit));
    rows[p.id] = { range, num };
    inputs.append(row);
  }
  const redraw = () => {
    const s = evaluate(sim, values, compiled);
    group = null;
    const body = [];
    for (const o of sim.outputs.filter((x) => !x.hidden)) {
      if (o.group && o.group !== group) {
        group = o.group;
        const tr = el("tr", "sim-group"), th = el("th", "", group);
        th.colSpan = 3; tr.append(th); body.push(tr);
      }
      const tr = el("tr");
      tr.title = o.expr;
      tr.append(el("td", "", o.label), el("td", "sim-val", fmt(s[o.id], o.digits)), el("td", "muted", o.unit));
      body.push(tr);
    }
    outputs.replaceChildren(...body);
    if (sim.plot) charts.replaceChildren(...sim.plot.y.map((id) => chart(sim, sim.outputs.find((o) => o.id === id), values, compiled)));
    try { localStorage.setItem(key, JSON.stringify(values)); } catch { /* not kept */ }
  };
  const bar = el("div", "sim-bar");
  const reset = el("button", "", t("prj.sim_reset"));
  reset.addEventListener("click", () => {
    values = { ...start };
    for (const p of sim.params) { rows[p.id].range.value = values[p.id]; rows[p.id].num.value = values[p.id]; }
    redraw();
  });
  const copy = el("button", "", t("prj.sim_copy"));
  copy.addEventListener("click", () => {
    const s = evaluate(sim, values, compiled);
    const text = [sim.title || sim.name, ...sim.params.map((p) => `${p.label}: ${fmt(values[p.id], 6)} ${p.unit}`), "",
      ...sim.outputs.filter((o) => !o.hidden).map((o) => `${o.label}: ${fmt(s[o.id], o.digits)} ${o.unit}`)].join("\n");
    navigator.clipboard?.writeText(text).then(() => { copy.textContent = t("prj.sim_copied"); }).catch(() => {});
  });
  bar.append(reset, copy);
  box.append(grid, charts, bar);
  if (sim.notes) {
    const n = el("details", "sim-notes");
    n.append(el("summary", "", t("prj.sim_notes")), renderMarkdown(sim.notes));
    box.append(n);
  }
  redraw();
  return box;
}

export function simView(name) {
  const box = el("div", "prj-sim");
  box.append(el("p", "muted", t("prj.sim_hint")));
  call(`/v1/aurora/projects/${name}/sims`).then(({ sims }) => {
    if (!sims.length) { box.append(el("p", "muted", t("prj.sim_none"))); return; }
    if (sims.length === 1) { box.append(simCard(name, sims[0])); return; }
    const chips = el("div", "prj-tabs"), pane = el("div");
    const pick = (i) => {
      chips.querySelectorAll("button").forEach((b, k) => b.classList.toggle("on", k === i));
      pane.replaceChildren(simCard(name, sims[i]));
    };
    sims.forEach((s, i) => {
      const b = el("button", "cat-chip", s.title || s.name);
      b.type = "button";
      b.addEventListener("click", () => pick(i));
      chips.append(b);
    });
    box.append(chips, pane);
    pick(0);
  }).catch((e) => box.append(el("p", "error", t("ev.error", { m: e.message }))));
  return box;
}

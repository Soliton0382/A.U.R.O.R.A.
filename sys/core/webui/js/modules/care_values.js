// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📈 Exam values over time (owner, 2026-10-05): each test with its last value, its direction and its range; opened, a
// chart (one line, the reference range as a band, a marker per exam with its value on hover) and each value with
// "correct" and "delete". Outside the range: said plainly, with "talk to your doctor" — never a diagnosis.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString([], { maximumFractionDigits: 2 }));

function chart(s) {
  const W = 560, H = 200, L = 48, R = 16, T = 14, B = 30;
  const pts = s.points;
  const times = pts.map((p) => Date.parse(p.date));
  const vals = pts.map((p) => p.value);
  const lows = pts.map((p) => p.low).filter((v) => v !== null), highs = pts.map((p) => p.high).filter((v) => v !== null);
  let lo = Math.min(...vals, ...lows), hi = Math.max(...vals, ...highs);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.12;
  lo -= pad; hi += pad;
  const t0 = Math.min(...times), t1 = Math.max(...times);
  const x = (tm) => (t1 === t0 ? L + (W - L - R) / 2 : L + (tm - t0) / (t1 - t0) * (W - L - R));
  const y = (v) => T + (hi - v) / (hi - lo) * (H - T - B);
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "care-chart", role: "img", "aria-label": `${s.name} (${s.unit})` });
  const last = s.last;
  if (last.low !== null || last.high !== null) {                         // the reference range, recessive
    const top = y(last.high ?? hi), bottom = y(last.low ?? lo);
    g.append(svg("rect", { x: L, y: top, width: W - L - R, height: Math.max(0, bottom - top), class: "care-band" }));
  }
  for (let k = 0; k <= 3; k++) {                                         // one axis, a quiet grid
    const v = lo + (hi - lo) * k / 3;
    g.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "care-grid" }));
    const tx = svg("text", { x: L - 6, y: y(v) + 4, class: "care-axis", "text-anchor": "end" });
    tx.textContent = fmt(v);
    g.append(tx);
  }
  if (pts.length > 1) g.append(svg("polyline", { points: pts.map((p, i) => `${x(times[i])},${y(p.value)}`).join(" "), class: "care-line" }));
  pts.forEach((p, i) => {
    const out = (p.low !== null && p.value < p.low) || (p.high !== null && p.value > p.high);
    const c = svg("circle", { cx: x(times[i]), cy: y(p.value), r: 5, class: out ? "care-dot out" : "care-dot" });
    const tip = svg("title");
    tip.textContent = `${p.date}: ${fmt(p.value)} ${p.unit}`;
    c.append(tip);
    g.append(c);
    const d = svg("text", { x: x(times[i]), y: H - 10, class: "care-axis", "text-anchor": "middle" });
    d.textContent = p.date.slice(2).split("-").reverse().join("/");
    if (pts.length <= 8 || i === 0 || i === pts.length - 1) g.append(d);
  });
  const lbl = svg("text", { x: x(times.at(-1)), y: y(last.value) - 10, class: "care-label", "text-anchor": "middle" });
  lbl.textContent = fmt(last.value);                                     // the last value, labelled
  g.append(lbl);
  return g;
}

function valueRow(p, refresh) {
  const r = el("div", "ev");
  const range = p.low === null && p.high === null ? "" : ` (${fmt(p.low)}–${fmt(p.high)})`;
  r.append(el("span", "", `${p.date} · ${fmt(p.value)} ${p.unit}${range}${p.by === "owner" ? " ✏️" : ""}`));
  const fix = el("button", "", t("care.v_fix"));
  fix.addEventListener("click", async () => {
    const v = prompt(t("care.v_fix_q", { name: p.name }), String(p.value));
    if (v === null) return;
    try { await call(`/v1/aurora/health/values/${p.id}`, { method: "PUT", body: JSON.stringify({ value: v }) }); refresh(); }
    catch (e) { alert(e.message); }
  });
  const del = el("button", "danger", "🗑️");
  del.title = t("care.v_delete");
  del.addEventListener("click", async () => { await call(`/v1/aurora/health/values/${p.id}`, { method: "DELETE" }); refresh(); });
  r.append(fix, del);
  return r;
}

export async function renderValues(box) {
  const refresh = () => renderValues(box);
  let d;
  try { d = await call("/v1/aurora/health/values"); } catch { box.replaceChildren(); return; }
  const reading = Object.values(d.reading).filter((s) => s === "reading").length;
  const head = [el("h4", "", t("care.values")), el("p", "muted", t("care.values_hint"))];
  if (reading) head.push(el("p", "muted", t("care.reading", { n: reading })));
  if (!d.series.length) { box.replaceChildren(...head, el("p", "muted", t("care.no_values"))); return; }
  const outs = d.series.filter((s) => s.out_of_range).length;
  if (outs) head.push(el("p", "warn", t("care.doctor", { n: outs })));
  const arrow = { up: "↗", down: "↘", same: "→" };
  box.replaceChildren(...head, ...d.series.map((s) => {
    const det = el("details", "report");
    const range = s.last.low === null && s.last.high === null ? "" : ` · ${t("care.range")} ${fmt(s.last.low)}–${fmt(s.last.high)}`;
    det.append(el("summary", "", `${s.out_of_range ? "⚠️" : "✅"} ${s.name}: ${fmt(s.last.value)} ${s.unit} ${s.trend ? arrow[s.trend] : ""}`
      + ` · ${s.last.date}${range} · ${t("care.n_values", { n: s.points.length })}`));
    det.addEventListener("toggle", () => {
      if (!det.open || det.dataset.drawn) return;
      det.dataset.drawn = "1";
      det.append(chart(s), ...s.points.slice().reverse().map((p) => valueRow({ ...p, name: s.name }, refresh)));
    });
    return det;
  }));
}

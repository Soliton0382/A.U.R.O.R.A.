// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💶 The expenses' charts (expenses.js): the year by month — incomes and spendings as paired bars, what was saved as a
// line on the same axis (one unit, one scale) with the goal dashed — and a month's categories against their budgets.
// Colours: the first three categorical slots (blue, orange, aqua), validated together in both modes; text stays in
// the page's own ink.
import { el } from "../dom.js";
import { t } from "../i18n.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };

function legend(items) {
  const box = el("div", "exp-legend");
  for (const [cls, label] of items) {
    const s = el("span", "exp-key");
    s.append(el("i", cls), label);
    box.append(s);
  }
  return box;
}

// a rounded data-end on top, square at the baseline
function bar(x, y, w, h, cls) {
  const r = Math.min(4, w / 2, h);
  const d = `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  return svg("path", { d, class: cls });
}

export function yearChart(trend, goal, fmt, monthName, narrow = false) {
  const W = narrow ? 380 : 720, H = narrow ? 250 : 240, L = 54, R = 10, T = 12, B = 26;   // a phone: six months, larger type
  const vals = trend.flatMap((m) => [m.income, m.spent, m.saved, goal || 0]);
  const raw = (Math.max(1, ...vals) - Math.min(0, ...vals)) / 4;                // round steps: 250, 500, 1.000…
  const mag = 10 ** Math.floor(Math.log10(raw)), st = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((k) => k >= raw);
  const top = Math.ceil(Math.max(1, ...vals) / st) * st, bottom = Math.floor(Math.min(0, ...vals) / st) * st;
  const y = (v) => T + (top - v) / (top - bottom) * (H - T - B);
  const step = (W - L - R) / trend.length, bw = Math.max(3, Math.min(14, step / 2 - 4));
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "exp-chart", role: "img", "aria-label": t("exp.chart_year") });
  for (let v = bottom; v <= top + st / 2; v += st) {                          // recessive grid lines on round values
    g.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: v === 0 ? "exp-base" : "exp-grid" }));
    const lab = svg("text", { x: L - 6, y: y(v) + 4, class: "exp-axis", "text-anchor": "end" });
    lab.textContent = fmt(Math.round(v), true);
    g.append(lab);
  }
  if (goal) g.append(svg("line", { x1: L, x2: W - R, y1: y(goal), y2: y(goal), class: "exp-goal" }));
  const pts = [];
  trend.forEach((m, i) => {
    const cx = L + i * step + step / 2;
    g.append(bar(cx - bw - 1, y(m.income), bw, y(0) - y(m.income), "exp-in"));   // 2 px apart
    g.append(bar(cx + 1, y(m.spent), bw, y(0) - y(m.spent), "exp-out"));
    pts.push([cx, y(m.saved)]);
    const lab = svg("text", { x: cx, y: H - 8, class: "exp-axis", "text-anchor": "middle" });
    lab.textContent = monthName(m.month);
    g.append(lab);
  });
  g.append(svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), class: "exp-saved" }));
  pts.forEach(([cx, cy], i) => {
    g.append(svg("circle", { cx, cy, r: 4, class: "exp-dot" }));
    const m = trend[i];
    const hit = svg("rect", { x: L + i * step, y: T, width: step, height: H - T - B, class: "exp-hit" });   // bigger than the marks
    const tip = svg("title");
    tip.textContent = `${monthName(m.month, true)}\n${t("exp.in")}: ${fmt(m.income)}\n${t("exp.out")}: ${fmt(m.spent)}\n${t("exp.saved")}: ${fmt(m.saved)}`;
    hit.append(tip);
    g.append(hit);
  });
  const box = el("div", "exp-chartbox");
  box.append(legend([["exp-in", t("exp.in")], ["exp-out", t("exp.out")], ["exp-saved", t("exp.saved")]]
    .concat(goal ? [["exp-goal", t("exp.goal")]] : [])), g);
  const table = el("details", "exp-table");
  table.append(el("summary", "", t("exp.numbers")));
  const tb = el("table", "");
  tb.innerHTML = `<tr><th></th><th>${t("exp.in")}</th><th>${t("exp.out")}</th><th>${t("exp.saved")}</th></tr>`;
  for (const m of trend) {
    const tr = el("tr", "");
    for (const c of [monthName(m.month, true), fmt(m.income), fmt(m.spent), fmt(m.saved)]) tr.append(el("td", "", c));
    tb.append(tr);
  }
  table.append(tb);
  box.append(table);
  return box;
}

// a month's categories: one bar each, its budget as a tick, the amount beside in the page's ink
export function categoryBars(cats, total, fmt, label) {
  const box = el("div", "exp-cats");
  const top = Math.max(1, ...cats.map((c) => Math.max(c.cents, c.budget || 0)));
  for (const c of cats) {
    const row = el("div", "exp-cat");
    const track = el("div", "exp-track");
    const fill = el("div", "exp-fill");
    fill.style.width = `${(c.cents / top) * 100}%`;
    track.append(fill);
    if (c.budget) {
      const tick = el("div", "exp-budget");
      tick.style.left = `${(c.budget / top) * 100}%`;
      tick.title = `${t("exp.budget")} ${fmt(c.budget)}`;
      track.append(tick);
    }
    const over = c.budget && c.cents > c.budget;
    row.append(el("span", "exp-cat-name", label(c.category)), track,
      el("span", "exp-cat-val", `${fmt(c.cents)}${total ? ` · ${Math.round(c.cents / total * 100)}%` : ""}${over ? " ⚠️" : ""}`));
    row.title = c.budget ? `${t("exp.budget")} ${fmt(c.budget)}${over ? ` — ${t("exp.over")}` : ""}` : "";
    box.append(row);
  }
  return box;
}

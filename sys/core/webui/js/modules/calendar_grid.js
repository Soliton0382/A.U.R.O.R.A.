// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📅 The day and the week as a time grid, the way Outlook shows them (owner, 2026-10-13: «una rappresentazione stile
// outlook stile tabella con vista che si può cambiare in giorno e mese, ma lascerei quello che è già presente»): a
// column a day, an hour a row, each item a block as tall as it lasts, side by side when they overlap; the all-day
// items in a row on top; a red line at the time of now. A tap on a free hour opens a new item at that hour.
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { ymd } from "./calendar_form.js";

const HOUR_PX = 44;
const mins = (iso) => Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16));

// the blocks of one day: [{o, top, height, lane, lanes}], overlapping ones side by side
function blocks(list, d) {
  const timed = list.filter((o) => !o.all_day).map((o) => {
    const s = o.start_iso.slice(0, 10) < d ? 0 : mins(o.start_iso);
    const e = o.end_iso.slice(0, 10) > d ? 24 * 60 : Math.max(mins(o.end_iso), s + (o.kind === "reminder" ? 20 : 15));
    return { o, s, e };
  }).sort((a, b) => a.s - b.s || b.e - a.e);
  const out = [];
  let cluster = [], end = -1;
  const close = () => {                             // a run of overlapping items shares the width
    const lanes = [];
    for (const b of cluster) {
      let i = lanes.findIndex((last) => last <= b.s);
      if (i < 0) { i = lanes.length; lanes.push(0); }
      lanes[i] = b.e;
      b.lane = i;
    }
    for (const b of cluster) out.push({ ...b, lanes: lanes.length });
    cluster = [];
  };
  for (const b of timed) {
    if (b.s >= end && cluster.length) close();
    cluster.push(b);
    end = Math.max(end, b.e);
  }
  if (cluster.length) close();
  return out;
}

export function timeGrid(first, n, byDay, today, { open, add, hm }) {
  const wrap = el("div", `cal-grid-wrap${n > 1 ? " week" : ""}`);
  const grid = el("div", "cal-grid");
  grid.style.setProperty("--days", n);
  const dates = Array.from({ length: n }, (_, i) => { const x = new Date(first); x.setDate(x.getDate() + i); return x; });
  // the heads and the all-day row
  grid.append(el("div", "cal-g-corner"));
  for (const date of dates) {
    const d = ymd(date);
    grid.append(el("div", `cal-g-head${d === today ? " today" : ""}`,
      date.toLocaleDateString([], n > 1 ? { weekday: "short", day: "numeric" } : { weekday: "long", day: "numeric", month: "long" })));
  }
  grid.append(el("div", "cal-g-corner muted", t("cal.all_day")));
  for (const date of dates) {
    const cell = el("div", "cal-g-allday");
    for (const o of (byDay.get(ymd(date)) || []).filter((x) => x.all_day)) cell.append(item(o, open, hm));
    grid.append(cell);
  }
  // the hours: a gutter of labels and a column a day
  const gutter = el("div", "cal-g-hours");
  for (let h = 0; h < 24; h++) gutter.append(el("div", "cal-g-hour muted", `${String(h).padStart(2, "0")}:00`));
  grid.append(gutter);
  const now = new Date();
  for (const date of dates) {
    const d = ymd(date);
    const col = el("div", `cal-g-col${d === today ? " today" : ""}`);
    col.style.height = `${24 * HOUR_PX}px`;
    col.addEventListener("click", (ev) => {                   // a free hour: a new item there
      if (ev.target !== col) return;
      add(d, Math.min(23, Math.floor(ev.offsetY / HOUR_PX)));
    });
    for (const b of blocks(byDay.get(d) || [], d)) {
      const it = item(b.o, open, hm);
      Object.assign(it.style, {
        top: `${(b.s / 60) * HOUR_PX}px`, height: `${Math.max(18, ((b.e - b.s) / 60) * HOUR_PX - 2)}px`,
        left: `calc(${(b.lane / b.lanes) * 100}% + 2px)`, width: `calc(${100 / b.lanes}% - 4px)`,
      });
      it.classList.add("timed");
      col.append(it);
    }
    if (d === today) {
      const line = el("div", "cal-g-now");
      line.style.top = `${((now.getHours() * 60 + now.getMinutes()) / 60) * HOUR_PX}px`;
      col.append(line);
    }
    grid.append(col);
  }
  wrap.append(grid);
  // opened at 7:00, or an hour before now on today
  requestAnimationFrame(() => {
    const start = dates.some((x) => ymd(x) === today) ? Math.max(0, now.getHours() - 1) : 7;
    wrap.scrollTop = start * HOUR_PX;
  });
  return wrap;
}

function item(o, open, hm) {
  const own = !o.cal;
  const b = el(own ? "button" : "div", `cal-g-item${own ? "" : " ext"}${o.kind === "reminder" ? " rem" : ""}`);
  if (own) { b.type = "button"; b.addEventListener("click", (ev) => { ev.stopPropagation(); open(o); }); }
  if (!o.all_day) b.append(el("span", "cal-g-time", o.kind === "reminder" ? hm(o.start_iso) : `${hm(o.start_iso)}–${hm(o.end_iso)}`));
  b.append(el("span", "cal-g-title", `${o.kind === "reminder" ? "⏰ " : ""}${o.title}`));
  if (o.location) b.append(el("span", "cal-g-place muted", `📍 ${o.location}`));
  b.title = `${o.title}${o.location ? ` · ${o.location}` : ""}${own ? "" : ` · ${o.cal}`}`;
  return b;
}

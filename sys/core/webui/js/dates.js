// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📅 Dates as each person writes them (owner, 2026-10-19: «nei campi di selezione delle date… la scelta del calendario
// così la compilazione va in base a come è configurato il sistema… la selezione del tipo di formato della data, sai
// dd-mm-aaaa o mm-dd-aaaa»): the format is the person's own (/v1/aurora/me/prefs date_format, the same on every device,
// chosen beside the time zone in Settings); datePicker() is a field written in that format with a month's calendar to
// pick from. Values travel as AAAA-MM-GG (ISO) whatever is shown.
import { call } from "./api.js";
import { el } from "./dom.js";
import { lang, t } from "./i18n.js";

export const FORMATS = ["dd/mm/yyyy", "dd-mm-yyyy", "mm/dd/yyyy", "mm-dd-yyyy", "yyyy-mm-dd"];
const KEY = "aurora.prefs.date";

function guess() {                                        // before a choice: the browser's own order of day and month
  try {
    const parts = new Intl.DateTimeFormat(navigator.language).formatToParts(new Date(2000, 10, 22));
    const order = parts.filter((p) => p.type !== "literal").map((p) => p.type[0]).join("");
    return order.startsWith("m") ? "mm/dd/yyyy" : order.startsWith("y") ? "yyyy-mm-dd" : "dd/mm/yyyy";
  } catch { return "dd/mm/yyyy"; }
}

export function dateFormat() {
  try { const f = localStorage.getItem(KEY); if (FORMATS.includes(f)) return f; } catch { /* none kept */ }
  return guess();
}

export function setDateFormat(f, save = true) {
  if (!FORMATS.includes(f)) return;
  try { localStorage.setItem(KEY, f); } catch { /* this visit only */ }
  if (save) call("/v1/aurora/me/prefs", { method: "PUT", body: JSON.stringify({ date_format: f }) }).catch(() => { /* kept here */ });
}

/** «2026-10-19» → as the person writes it. */
export function fmtDate(iso, f = dateFormat()) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!m) return String(iso || "");
  const [, y, mo, d] = m;
  const sep = f.includes("/") ? "/" : "-";
  return f.startsWith("yyyy") ? `${y}-${mo}-${d}` : f.startsWith("mm") ? `${mo}${sep}${d}${sep}${y}` : `${d}${sep}${mo}${sep}${y}`;
}

/** What the person wrote, in their format (any of / - . as separator) → «AAAA-MM-GG», or "" when it is not a date. */
export function parseDate(text, f = dateFormat()) {
  const s = String(text || "").trim();
  let y, mo, d;
  let m = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(s);
  if (m) [, y, mo, d] = m;
  else if ((m = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/.exec(s))) {
    [, d, mo, y] = m;
    if (f.startsWith("mm")) [d, mo] = [mo, d];
  } else return "";
  const date = new Date(Date.UTC(+y, +mo - 1, +d));
  if (date.getUTCFullYear() !== +y || date.getUTCMonth() !== +mo - 1 || date.getUTCDate() !== +d) return "";
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function placeholder(f) {
  const it = lang === "it_IT";
  return f.replace("dd", it ? "gg" : "dd").replace("yyyy", it ? "aaaa" : "yyyy");
}

/** A date field in the person's format with a month's calendar: { el, value (ISO, "" for none) }; onChange(value)
 * when a day is picked, cleared or typed. */
export function datePicker(iso = "", onChange = null) {
  const wrap = el("span", "datepick");
  const input = el("input");
  input.placeholder = placeholder(dateFormat());
  input.inputMode = "numeric";
  input.size = 11;
  const btn = el("button", "datepick-btn", "📅");
  btn.type = "button";
  btn.title = t("date.pick");
  const pop = el("div", "datepick-pop");
  pop.hidden = true;
  let value = parseDate(iso) || "";
  const changed = () => { if (onChange) onChange(value); };
  input.value = value ? fmtDate(value) : "";
  input.addEventListener("change", () => {
    const v = parseDate(input.value);
    input.classList.toggle("bad", Boolean(input.value.trim()) && !v);
    if (v || !input.value.trim()) { value = v; if (v) input.value = fmtDate(v); changed(); }
  });
  let shown = null;                                       // the month on show: [year, month 0-11]
  const draw = () => {
    const [y, mo] = shown;
    const loc = lang === "it_IT" ? "it-IT" : "en-US";
    const head = el("div", "datepick-head");
    const prev = el("button", "", "‹");
    const next = el("button", "", "›");
    prev.type = next.type = "button";
    prev.addEventListener("click", () => { shown = mo ? [y, mo - 1] : [y - 1, 11]; draw(); });
    next.addEventListener("click", () => { shown = mo < 11 ? [y, mo + 1] : [y + 1, 0]; draw(); });
    head.append(prev, el("span", "", new Date(y, mo, 1).toLocaleDateString(loc, { month: "long", year: "numeric" })), next);
    const grid = el("div", "datepick-grid");
    const monday = lang === "it_IT";                    // the week starts on Monday in Italian, on Sunday in English
    for (let i = 0; i < 7; i++) {
      const day = new Date(2024, 0, (monday ? 1 : 7) + i);  // 1 Jan 2024 was a Monday
      grid.append(el("span", "datepick-dow", day.toLocaleDateString(loc, { weekday: "narrow" })));
    }
    const first = new Date(y, mo, 1).getDay();
    const lead = monday ? (first + 6) % 7 : first;
    for (let i = 0; i < lead; i++) grid.append(el("span"));
    const days = new Date(y, mo + 1, 0).getDate();
    const today = new Date();
    for (let d = 1; d <= days; d++) {
      const iso2 = `${y}-${String(mo + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const b = el("button", `datepick-day${iso2 === value ? " on" : ""}${
        today.getFullYear() === y && today.getMonth() === mo && today.getDate() === d ? " today" : ""}`, String(d));
      b.type = "button";
      b.addEventListener("click", () => { value = iso2; input.value = fmtDate(iso2); input.classList.remove("bad"); pop.hidden = true; changed(); });
      grid.append(b);
    }
    const foot = el("div", "datepick-foot");
    const now = el("button", "", t("date.today"));
    const none = el("button", "", t("date.clear"));
    now.type = none.type = "button";
    now.addEventListener("click", () => {
      const d = new Date();
      value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      input.value = fmtDate(value);
      pop.hidden = true;
      changed();
    });
    none.addEventListener("click", () => { value = ""; input.value = ""; pop.hidden = true; changed(); });
    foot.append(now, none);
    pop.replaceChildren(head, grid, foot);
  };
  btn.addEventListener("click", () => {
    if (!pop.hidden) { pop.hidden = true; return; }
    const base = value ? new Date(`${value}T12:00:00`) : new Date();
    shown = [base.getFullYear(), base.getMonth()];
    draw();
    pop.hidden = false;
  });
  document.addEventListener("click", (e) => { if (!wrap.contains(e.target)) pop.hidden = true; });
  wrap.append(input, btn, pop);
  return { el: wrap, get value() { return value; }, set value(v) { value = parseDate(v) || ""; input.value = value ? fmtDate(value) : ""; } };
}

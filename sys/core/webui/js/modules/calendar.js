// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📅 Aurora's own calendar (owner, 2026-10-08: «un calendario tutto suo… appuntamenti, reminder»): the next two weeks
// as a list or the month as a grid, an item added or changed with a tap, the .ics out and in. The user's other
// calendars (Google, Outlook, CalDAV: the calendar plugin's card) are shown beside, read only.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { itemForm, ymd } from "./calendar_form.js";

useCss("/static/css/calendar.css");

const AGENDA_DAYS = 14;
const hm = (iso) => iso.slice(11, 16);                    // the wall time of Aurora's zone, as stored
const day0 = (s) => new Date(`${s.slice(0, 10)}T00:00`);
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

// the days an occurrence covers (an all-day of three days shows on each), at most a month
function days(o) {
  const first = day0(o.start_iso);
  const endsAtMidnight = o.end_iso.slice(11, 16) === "00:00" && o.end_iso.slice(0, 10) > o.start_iso.slice(0, 10);
  const last = o.all_day || endsAtMidnight ? addDays(day0(o.end_iso), -1) : day0(o.end_iso);
  const out = [];
  for (let d = first; d <= last && out.length < 31; d = addDays(d, 1)) out.push(ymd(d));
  return out.length ? out : [ymd(first)];
}

export default {
  id: "calendar",
  icon: "📅",
  title: "nav.calendar",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="cal.title"></h2><p class="muted" data-i18n="cal.hint"></p>
      <div class="cal-bar">
        <button type="button" data-go="-1" aria-label="◀">◀</button>
        <button type="button" data-go="0" data-i18n="cal.today"></button>
        <button type="button" data-go="1" aria-label="▶">▶</button>
        <strong class="cal-range"></strong>
        <span class="cal-views"><button type="button" class="cat-chip on" data-view="agenda" data-i18n="cal.agenda"></button><button type="button" class="cat-chip" data-view="month" data-i18n="cal.month"></button></span>
        <button type="button" class="primary cal-new">➕ <span data-i18n="cal.new"></span></button>
      </div>
      <div class="cal-edit" hidden></div>
      <div class="cal-out"></div>
      <div class="cal-body"></div>
      <div class="cal-day"></div>
      <details class="cal-files"><summary data-i18n="cal.files"></summary>
        <p class="muted" data-i18n="cal.files_hint"></p>
        <div class="appr-actions"><a class="button" href="/v1/aurora/calendar/export.ics" download="aurora.ics">⬇️ <span data-i18n="cal.export"></span></a>
        <label class="dj-upload"><span data-i18n="cal.import"></span><input type="file" accept=".ics,text/calendar" hidden></label></div>
        <span class="muted cal-imported"></span></details>`;
    apply(root);
    this.root = root;
    this.view = "agenda";
    this.anchor = new Date();
    this.picked = null;
    this.edit = root.querySelector(".cal-edit");
    root.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => this.go(Number(b.dataset.go))));
    root.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => {
      this.view = b.dataset.view;
      root.querySelectorAll("[data-view]").forEach((x) => x.classList.toggle("on", x === b));
      this.picked = null;
      this.enter();
    }));
    root.querySelector(".cal-new").addEventListener("click", () => this.open(null, this.picked || ymd(new Date())));
    root.querySelector(".cal-files input").addEventListener("change", async (ev) => {
      const f = ev.target.files[0];
      const said = root.querySelector(".cal-imported");
      if (!f) return;
      try {
        const r = await call("/v1/aurora/calendar/import", { method: "POST", body: await f.text(), headers: { "Content-Type": "text/calendar" } });
        said.textContent = t("cal.imported", r);
      } catch (e) { said.textContent = t("ev.error", { m: e.message }); }
      ev.target.value = "";
      this.enter();
    });
  },

  go(step) {
    if (!step) this.anchor = new Date();
    else if (this.view === "month") this.anchor = new Date(this.anchor.getFullYear(), this.anchor.getMonth() + step, 1);
    else this.anchor = addDays(this.anchor, step * AGENDA_DAYS);
    this.picked = null;
    this.enter();
  },

  range() {
    if (this.view === "agenda") { const a = new Date(this.anchor.getFullYear(), this.anchor.getMonth(), this.anchor.getDate()); return [a, addDays(a, AGENDA_DAYS)]; }
    const first = new Date(this.anchor.getFullYear(), this.anchor.getMonth(), 1);
    const a = addDays(first, -((first.getDay() + 6) % 7));                     // the Monday before the 1st
    return [a, addDays(a, 42)];
  },

  async enter() {
    const [a, b] = this.range();
    const out = this.root.querySelector(".cal-out");
    let v;
    try { v = await call(`/v1/aurora/calendar?start=${ymd(a)}&end=${ymd(b)}`); } catch (e) { out.textContent = t("ev.error", { m: e.message }); return; }
    this.today = v.today;
    const notes = [];
    if (v.failed.length) notes.push(el("div", "warn", `⚠️ ${t("cal.failed", { which: v.failed.join(", ") })}`));
    if (!v.connected) notes.push(el("div", "muted", t("cal.others")));
    out.replaceChildren(...notes);
    const byDay = new Map();
    for (const o of [...v.events, ...v.external]) for (const d of days(o)) { if (!byDay.has(d)) byDay.set(d, []); byDay.get(d).push(o); }
    for (const list of byDay.values()) list.sort((x, y) => (y.all_day - x.all_day) || x.start_iso.localeCompare(y.start_iso));
    this.byDay = byDay;
    const fmt = { day: "numeric", month: "long", year: "numeric" };
    this.root.querySelector(".cal-range").textContent = this.view === "month"
      ? this.anchor.toLocaleDateString([], { month: "long", year: "numeric" })
      : `${a.toLocaleDateString([], fmt)} – ${addDays(b, -1).toLocaleDateString([], fmt)}`;
    const body = this.root.querySelector(".cal-body");
    body.replaceChildren(this.view === "month" ? this.month(a) : this.agenda(a));
    this.showDay();
  },

  row(o) {
    const own = !o.cal;
    const r = el(own ? "button" : "div", `cal-item${own ? "" : " ext"}${o.kind === "reminder" ? " rem" : ""}`);
    if (own) r.type = "button";
    const when = o.all_day ? t("cal.all_day") : o.kind === "reminder" ? hm(o.start_iso) : `${hm(o.start_iso)}–${hm(o.end_iso)}`;
    r.append(el("span", "cal-when", when));
    const what = el("span", "cal-what", `${o.kind === "reminder" ? "⏰ " : ""}${o.title}`);
    r.append(what);
    const tags = [];
    if (o.location) tags.push(`📍 ${o.location}`);
    if (o.repeat) tags.push(`🔁 ${t(`cal.repeat.${o.repeat.freq}`)}`);
    if (own && o.alerts?.length) tags.push("🔔");
    if (!own) tags.push(`🔗 ${o.cal}`);
    if (tags.length) r.append(el("span", "cal-tags muted", tags.join(" · ")));
    if (own) r.addEventListener("click", () => this.open(o));
    return r;
  },

  dayTitle(d) {
    const s = day0(d).toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
    return d === this.today ? `${s} · ${t("cal.today")}` : s;
  },

  agenda(a) {
    const box = el("div", "cal-agenda");
    for (let i = 0; i < AGENDA_DAYS; i++) {
      const d = ymd(addDays(a, i));
      const list = this.byDay.get(d) || [];
      if (!list.length && d !== this.today) continue;
      const g = el("section", `cal-group${d === this.today ? " today" : ""}`);
      const h = el("h4", "", this.dayTitle(d));
      const add = el("button", "link", "➕");
      add.type = "button";
      add.title = t("cal.new");
      add.addEventListener("click", () => this.open(null, d));
      h.append(" ", add);
      g.append(h, ...(list.length ? list.map((o) => this.row(o)) : [el("p", "muted", t("cal.free"))]));
      box.append(g);
    }
    if (!box.childElementCount) box.append(el("p", "muted", t("cal.empty")));
    return box;
  },

  month(a) {
    const grid = el("div", "cal-month");
    for (let i = 0; i < 7; i++) grid.append(el("div", "cal-wd muted", addDays(a, i).toLocaleDateString([], { weekday: "short" })));
    const month = this.anchor.getMonth();
    for (let i = 0; i < 42; i++) {
      const date = addDays(a, i), d = ymd(date);
      const list = this.byDay.get(d) || [];
      const c = el("button", `cal-cell${date.getMonth() !== month ? " out" : ""}${d === this.today ? " today" : ""}${d === this.picked ? " picked" : ""}`);
      c.type = "button";
      c.append(el("span", "cal-num", String(date.getDate())));
      for (const o of list.slice(0, 3)) c.append(el("span", `cal-chip${o.cal ? " ext" : ""}${o.kind === "reminder" ? " rem" : ""}`, `${o.all_day ? "" : `${hm(o.start_iso)} `}${o.title}`));
      if (list.length > 3) c.append(el("span", "cal-more muted", `+${list.length - 3}`));
      c.addEventListener("click", () => { this.picked = d; grid.querySelectorAll(".picked").forEach((x) => x.classList.remove("picked")); c.classList.add("picked"); this.showDay(); });
      grid.append(c);
    }
    return grid;
  },

  showDay() {
    const box = this.root.querySelector(".cal-day");
    if (this.view !== "month" || !this.picked) { box.replaceChildren(); return; }
    const list = this.byDay.get(this.picked) || [];
    const h = el("h4", "", this.dayTitle(this.picked));
    const add = el("button", "link", `➕ ${t("cal.new")}`);
    add.type = "button";
    add.addEventListener("click", () => this.open(null, this.picked));
    h.append(" ", add);
    box.replaceChildren(h, ...(list.length ? list.map((o) => this.row(o)) : [el("p", "muted", t("cal.free"))]));
  },

  async open(o, day) {
    let item = null;
    if (o) {                                         // the stored item (its first start, its rule), and this occurrence
      try { item = { ...(await call(`/v1/aurora/calendar/items/${o.id}`)).item, at: o.at }; } catch (e) { return; }
    }
    this.edit.replaceChildren(el("h3", "", item ? `✏️ ${item.title}` : `➕ ${t("cal.new")}`), itemForm(item, day, (changed) => {
      this.edit.hidden = true;
      this.edit.replaceChildren();
      if (changed) this.enter();
    }));
    this.edit.hidden = false;
    this.edit.scrollIntoView({ behavior: "smooth", block: "start" });
  },
};

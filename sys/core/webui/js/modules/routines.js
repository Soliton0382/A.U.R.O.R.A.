// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Routines: what Aurora proposes for the connected plugins (switch on with one click), the active routines
// (schedule, on/off, last result, run now) and a routine of the owner's own words. Reading is automatic;
// anything else an agent routine wants to do waits in Approvals.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { viewLink } from "../viewer.js";
import { renderMarkdown } from "../md.js";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const GROUPS = ["all", "weekdays", "weekend", "workdays", "holidays"];

function when(s) {
  if (s.every === "hours") return t("rt.every_hours", { n: s.hours });
  if (s.every === "day") return t("rt.every_day", { at: s.at });
  if (s.every === "week") return t("rt.every_week", { day: t(`rt.day.${DAYS[s.weekday]}`), at: s.at });
  const days = s.group ? t(`rt.g.${s.group}`) : s.days.map((d) => t(`rt.day.${DAYS[d]}`)).join(", ");
  return t("rt.every_custom", { days, at: s.times.join(", ") });
}

// every N hours, or days and times (several times with "+", days one by one or a group: weekdays, holidays...):
// a calendar's recurrence, simpler (owner, 2026-10-04). An old daily or weekly routine opens as days and times.
function scheduleEditor(s) {
  const box = el("span", "rt-sched");
  const every = el("select");
  for (const v of ["hours", "custom"]) { const o = el("option", "", t(`rt.e.${v}`)); o.value = v; o.selected = (s.every === "hours") === (v === "hours"); every.append(o); }
  const hours = el("input"); hours.type = "number"; hours.min = 1; hours.max = 168; hours.value = s.hours || 1;
  const c = s.every === "day" ? { times: [s.at], group: "all" } : s.every === "week" ? { times: [s.at], days: [s.weekday] }
    : s.every === "custom" ? s : { times: ["08:00"], group: "all" };
  const times = el("span", "rt-times");
  const addTime = (v) => {
    const one = el("span", "rt-time");
    const at = el("input"); at.type = "time"; at.value = v;
    const x = el("button", "icon", "✖"); x.type = "button";
    x.addEventListener("click", () => { if (times.querySelectorAll("input").length > 1) one.remove(); });
    one.append(at, x);
    times.insertBefore(one, plus);
  };
  const plus = el("button", "", "+"); plus.type = "button"; plus.title = t("rt.add_time");
  plus.addEventListener("click", () => { if (times.querySelectorAll("input").length < 12) addTime("12:00"); });
  times.append(plus);
  for (const v of c.times) addTime(v);
  const group = el("select");
  for (const g of ["pick", ...GROUPS]) { const o = el("option", "", t(`rt.g.${g}`)); o.value = g; group.append(o); }
  group.value = c.group || "pick";
  const days = el("span", "rt-days");
  DAYS.forEach((d, i) => {
    const l = el("label", "rt-day"); const cb = el("input"); cb.type = "checkbox"; cb.value = i;
    cb.checked = (c.days || []).includes(i);
    l.append(cb, el("span", "", t(`rt.day.${d}`).slice(0, 3))); days.append(l);
  });
  const sync = () => {
    hours.classList.toggle("hidden", every.value !== "hours");
    for (const x of [times, group]) x.classList.toggle("hidden", every.value === "hours");
    days.classList.toggle("hidden", every.value === "hours" || group.value !== "pick");
  };
  every.addEventListener("change", sync);
  group.addEventListener("change", sync);
  sync();
  box.append(every, hours, times, group, days);
  box.value = () => {
    if (every.value === "hours") return { every: "hours", hours: Number(hours.value) };
    const at = [...new Set([...times.querySelectorAll("input")].map((i) => i.value).filter(Boolean))].sort();
    if (group.value !== "pick") return { every: "custom", times: at, group: group.value };
    return { every: "custom", times: at, days: [...days.querySelectorAll("input:checked")].map((i) => Number(i.value)) };
  };
  return box;
}

export default {
  id: "routines",
  icon: "🔁",
  title: "nav.routines",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="rt.title"></h2><p class="muted" data-i18n="rt.hint"></p>
      <h3 class="setting-cat" data-i18n="rt.proposed"></h3><div class="rt-welcome"></div><div class="rt-sugg"></div>
      <h3 class="setting-cat" data-i18n="rt.active"></h3><div class="rt-list"></div>
      <h3 class="setting-cat" data-i18n="rt.custom"></h3><p class="muted" data-i18n="rt.custom_hint"></p>
      <form class="rt-new"><textarea rows="2" data-i18n-placeholder="rt.goal_ph"></textarea><span class="sched"></span>
        <select class="notify"></select><button type="submit" data-i18n="rt.add"></button> <span class="muted out"></span></form>`;
    apply(root);
    this.welcome = root.querySelector(".rt-welcome");
    this.sugg = root.querySelector(".rt-sugg");
    this.list = root.querySelector(".rt-list");
    const form = root.querySelector(".rt-new");
    const sched = scheduleEditor({ every: "day", at: "08:00" });
    form.querySelector(".sched").append(sched);
    const notify = form.querySelector(".notify");
    for (const v of ["always", "if_any", "if_new"]) { const o = el("option", "", t(`rt.n.${v}`)); o.value = v; notify.append(o); }
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const goal = form.querySelector("textarea").value.trim();
      if (!goal) return;
      const out = form.querySelector(".out");
      try {
        await call("/v1/aurora/routines", { method: "POST", body: JSON.stringify({
          kind: "agent", goal, title: goal.slice(0, 80), schedule: sched.value(), notify: notify.value, event: "routine.done" }) });
        form.querySelector("textarea").value = "";
        out.textContent = t("rt.added");
        this.refresh();
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
  },

  async enter() { await this.refresh(); },

  async refresh() {
    const { routines, suggestions, welcome } = await call("/v1/aurora/routines");
    this.welcome.replaceChildren(...welcome.map((w) => el("p", "", w.text)));
    const open = suggestions.filter((s) => !s.active);
    this.sugg.replaceChildren(...(open.length ? open.map((s) => this.suggestion(s)) : [el("p", "muted", t("rt.no_sugg"))]));
    this.list.replaceChildren(...(routines.length ? routines.map((r) => this.routine(r)) : [el("p", "muted", t("rt.none"))]));
  },

  suggestion(s) {
    const row = el("div", "ev");
    const title = typeof s.title === "object" ? (s.title.it || s.title.en) : s.title;
    const b = el("button", "", t("rt.switch_on"));
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await call("/v1/aurora/routines", { method: "POST", body: JSON.stringify({ suggestion: s.suggestion }) }); this.refresh(); }
      catch (e) { b.textContent = t("ev.error", { m: e.message }); }
    });
    row.append(el("strong", "", title), el("span", "pill", s.plugin), el("span", "muted", `${when(s.schedule)} · ${t(`rt.n.${s.notify || "always"}`)}`), b);
    return row;
  },

  routine(r) {
    const c = el("div", "appr-card");
    const head = el("div", "ev");
    const toggle = el("button", "", r.enabled ? "⏸️" : "▶️");
    toggle.title = t(r.enabled ? "rt.pause" : "rt.resume");
    toggle.addEventListener("click", async () => { await call(`/v1/aurora/routines/${r.id}`, { method: "PUT", body: JSON.stringify({ enabled: !r.enabled }) }); this.refresh(); });
    const now = el("button", "", t("rt.run_now"));
    now.addEventListener("click", async () => { now.disabled = true; await call(`/v1/aurora/routines/${r.id}/run`, { method: "POST", body: "{}" }); now.textContent = t("rt.started"); setTimeout(() => this.refresh(), 8000); });
    const del = el("button", "", "🗑️");
    del.title = t("rt.remove");
    del.addEventListener("click", async () => { if (confirm(t("rt.confirm_remove"))) { await call(`/v1/aurora/routines/${r.id}`, { method: "DELETE" }); this.refresh(); } });
    head.append(el("strong", "", r.title), r.plugin ? el("span", "pill", r.plugin) : el("span", "pill", "agent"),
      el("span", r.enabled ? "pill ok" : "pill warn", r.enabled ? t("rt.on") : t("rt.off")), toggle, now, del);
    const sched = scheduleEditor(r.schedule);
    const save = el("button", "", t("rt.save"));
    save.addEventListener("click", async () => {
      try { await call(`/v1/aurora/routines/${r.id}`, { method: "PUT", body: JSON.stringify({ schedule: sched.value() }) }); this.refresh(); }
      catch (e) { save.textContent = t("ev.error", { m: e.message }); }
    });
    const line = el("div", "ev");
    line.append(el("span", "muted", `${when(r.schedule)} · ${t(`rt.n.${r.notify}`)}`), sched, save);
    c.append(head, line);
    if (r.last_run) {
      c.append(el("div", "muted", `${t("rt.last")} ${clock(r.last_run)} ${r.last_ok === false ? "❌" : r.last_ok ? "✅" : "⏳"}`));
      if (r.last_text) c.append(renderMarkdown(r.last_text));
      if (r.last_files?.length) {                   // documents the routine wrote: download them
        const row = el("div", "chips");
        for (const f of r.last_files) {
          const a = viewLink(el("a", "chip"), f.url, f.name, f.mime);
          a.append(el("span", "", "📄"), el("span", "", f.name));
          row.append(a);
        }
        c.append(row);
      }
    }
    return c;
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Agents and routines (owner, 2026-10-06): a grid of icons like the Plugins page — a click opens the card (change,
// run now, clone, pause, remove); "➕" makes a personal agent: a goal it works on until done, the plugins it may use,
// memory of its last report (only what is new), a budget of steps and minutes. What Aurora proposes for the connected
// plugins below, switched on with one tap. Reading is automatic; anything else an agent wants to do waits in Approvals.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { viewLink } from "../viewer.js";
import { renderMarkdown } from "../md.js";
import { templatesSection } from "./routines_templates.js";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function badge(n) {                                   // the advice waiting, on the menu (like Approvals)
  const b = document.querySelector('#nav button[data-view="routines"] .label');
  if (!b) return;
  b.dataset.count = n || "";
  b.classList.toggle("has-badge", n > 0);
}

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

// The icon of a routine (owner, 2026-10-06: "icons chosen automatically, like the plugins"): its own, its plugin's
// picture, or one read from the words of an agent's goal.
const WORDS = [[/prezz|price|offert|sconto|amazon/i, "🏷️"], [/notizi|news|giornal/i, "📰"], [/meteo|weather|pioggia/i, "☀️"],
  [/github|repository|issue|pull request/i, "🐙"], [/firewall|attacc|sicurezz|security/i, "🛡️"], [/mail|posta/i, "✉️"],
  [/calendar|agenda|appuntament/i, "📅"], [/film|serie|cinema/i, "🎬"], [/arxiv|paper|ricerca|studi|scienz/i, "🔬"],
  [/telescop|stell|astro|cielo/i, "🔭"], [/spes|budget|soldi|conto/i, "💶"], [/salute|dieta|allenament/i, "❤️"],
  [/post|facebook|instagram|social/i, "📣"], [/backup/i, "💾"], [/web|sito|pagina|cerca/i, "🔎"]];
const LEAD = /^(\p{Extended_Pictographic}\uFE0F?)\s*/u;
function emoji(r) {
  if (r.icon) return r.icon;
  const lead = LEAD.exec(r.title || "");
  if (lead) return lead[1];                          // the title's own emoji ("📘 Post del giorno")
  const hit = WORDS.find(([re]) => re.test(`${r.title || ""} ${r.goal || ""}`));
  return hit ? hit[1] : r.kind === "agent" ? "🤖" : "⚙️";
}

// Ready-made personal agents: a goal to complete, the plugins they use, an icon (owner, 2026-10-06; most asked of
// personal agents: research and summary of a subject, news, prices).
const TEMPLATES = [
  { key: "research", icon: "🔬", plugins: ["web"], memory: true, sched: { every: "custom", times: ["08:00"], group: "all" } },
  { key: "news", icon: "📰", plugins: ["web", "news"], memory: true, sched: { every: "custom", times: ["07:30"], group: "all" } },
  { key: "price", icon: "🏷️", plugins: ["web"], memory: true, sched: { every: "hours", hours: 12 } },
  { key: "page", icon: "👀", plugins: ["web"], memory: true, sched: { every: "hours", hours: 6 } },
  { key: "github", icon: "🐙", plugins: ["github"], memory: false, sched: { every: "custom", times: ["09:00"], days: [0] } },
];

export default {
  id: "routines",
  icon: "🤖",
  title: "nav.routines",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="rt.title"></h2><p class="muted" data-i18n="rt.hint"></p>
      <h3 class="setting-cat"><span data-i18n="rt.advice"></span> <button class="rt-review" data-i18n="rt.review"></button></h3>
      <div class="rt-advice"></div>
      <div class="rt-welcome"></div><div class="plug-grid rt-grid"></div>
      <h3 class="setting-cat" data-i18n="rt.proposed"></h3><div class="plug-grid rt-sugg"></div>
      <h3 class="setting-cat" data-i18n="rt.tpl_sets"></h3><div class="rt-sets"></div>`;
    apply(root);
    this.root = root;
    this.welcome = root.querySelector(".rt-welcome");
    this.grid = root.querySelector(".rt-grid");
    this.sugg = root.querySelector(".rt-sugg");
    this.advice = root.querySelector(".rt-advice");
    root.querySelector(".rt-review").addEventListener("click", async (e) => {
      e.target.disabled = true;
      await call("/v1/aurora/routines/advice/review", { method: "POST" }).catch(() => null);
      this.loadAdvice();
    });
    const poll = async () => { try { badge((await call("/v1/aurora/routines/advice")).items.length); } catch { /* offline */ } };
    poll();
    setInterval(poll, 60000);
  },

  async enter() {
    const sets = await templatesSection(() => this.refresh());
    this.root.querySelector(".rt-sets").replaceChildren(sets);
    await Promise.all([this.refresh(), this.loadAdvice()]);
  },

  // Aurora's advice (owner, 2026-10-08: «mi passano quasi in sordina… con relativo tasto applica»): the code's checks
  // and her own review, each with what it changes; «Applica» is the owner's click, «Scarta» never proposed again
  async loadAdvice() {
    let a;
    try { a = await call("/v1/aurora/routines/advice"); } catch (e) { this.advice.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
    badge(a.items.length);
    this.root.querySelector(".rt-review").disabled = a.reviewing;
    const head = el("p", "muted", a.reviewing ? `⏳ ${t("rt.reviewing")}` : a.reviewed ? t("rt.reviewed", { at: clock(a.reviewed) }) : "");
    if (a.reviewing) setTimeout(() => this.loadAdvice(), 8000);
    this.advice.replaceChildren(head, ...(a.items.length ? a.items.map((x) => this.adviceCard(x)) : [el("p", "ok", t("rt.no_advice"))]));
  },

  adviceCard(x) {
    const c = el("div", "report rt-adv");
    const icon = { pause: "⏸️", change: "✏️", new: "➕", run: "🔁" }[x.action] || "💡";
    c.append(el("strong", "", `${icon} ${x.title}`), el("span", "muted", ` · ${x.by === "aurora" ? t("rt.by_aurora") : t("rt.by_code")}`),
      el("p", "", x.why));
    const ch = x.change || {};
    if (x.action === "new") c.append(el("p", "muted", `🎯 ${ch.goal || ""}`), el("p", "muted", `🕒 ${when(ch.schedule)} · 🧩 ${(ch.plugins || []).join(", ") || "—"}`));
    else if (ch.schedule) c.append(el("p", "muted", `🕒 ${when(ch.schedule)}`));
    if (ch.goal && x.action === "change") c.append(el("p", "muted", `🎯 ${ch.goal}`));
    const row = el("div", "appr-actions");
    const ok = el("button", "approve", `✔ ${t("rt.apply")}`);
    const no = el("button", "", `✖ ${t("rt.dismiss")}`);
    const out = el("span", "muted");
    const act = (action) => async () => {
      ok.disabled = no.disabled = true;
      try { await call(`/v1/aurora/routines/advice/${x.id}/${action}`, { method: "POST" }); await Promise.all([this.refresh(), this.loadAdvice()]); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); ok.disabled = no.disabled = false; }
    };
    ok.addEventListener("click", act("apply"));
    no.addEventListener("click", act("dismiss"));
    row.append(ok, no, out);
    c.append(row);
    return c;
  },

  async refresh() {
    const [{ routines, suggestions, welcome }, plugins] = await Promise.all([call("/v1/aurora/routines"),
      call("/v1/aurora/plugins").catch(() => [])]);
    this.plugins = plugins;
    this.welcome.replaceChildren(...welcome.map((w) => el("p", "", w.text)));
    const add = this.tile("➕", t("rt.new_agent"), t("rt.new_hint"), "new");
    add.addEventListener("click", () => this.open(null));
    this.grid.replaceChildren(...routines.map((r) => {
      const b = this.tile(emoji(r), (r.title || "").replace(LEAD, ""), `${r.enabled ? (r.last_ok === false ? "❌" : "✅") : "⏸️"}${r.by === "aurora" ? " ✨" : ""} ${when(r.schedule)}`,
        r.enabled ? "on" : "off", r.icon ? null : this.picture(r.plugin));
      b.addEventListener("click", () => this.open(r));
      return b;
    }), add);
    const open = suggestions.filter((s) => !s.active);
    this.sugg.replaceChildren(...(open.length ? open.map((s) => {
      const title = typeof s.title === "object" ? (s.title.it || s.title.en) : s.title;
      const b = this.tile(emoji({ ...s, title }), title.replace(LEAD, ""), `${when(s.schedule)} · ${t("rt.switch_on")}`, "sugg", this.picture(s.plugin));
      b.addEventListener("click", async () => {
        b.disabled = true;
        try { await call("/v1/aurora/routines", { method: "POST", body: JSON.stringify({ suggestion: s.suggestion }) }); this.refresh(); }
        catch (e) { b.title = t("ev.error", { m: e.message }); b.disabled = false; }
      });
      return b;
    }) : [el("p", "muted", t("rt.no_sugg"))]));
  },

  picture(plugin) { return plugin ? this.plugins?.find((p) => p.name === plugin)?.icon || null : null; },

  tile(icon, name, state, cls, src = null) {
    const b = el("button", `plug-tile rt-tile ${cls}`);
    b.type = "button";
    if (src) { const img = el("img"); img.src = src; img.alt = ""; b.append(img); }
    else b.append(el("span", "rt-emoji", icon));
    b.append(el("span", "name", name), el("span", "state", state));
    b.title = name;
    return b;
  },

  // A routine's card in a window (like a plugin's): everything to change, run, clone, pause, remove.
  open(r) {
    const dlg = el("dialog", "modal plug-modal");
    const shut = () => { dlg.close(); dlg.remove(); this.refresh(); };
    const close = el("button", "icon close", "✕");
    close.addEventListener("click", shut);
    const agent = !r || r.kind === "agent";
    const head = el("div", "plug-head");
    const icon = el("input", "rt-icon");
    icon.value = r ? emoji(r) : "🤖";
    icon.maxLength = 8;
    icon.title = t("rt.icon");
    head.append(icon, el("h3", "", r ? r.title : t("rt.new_agent")), close);
    dlg.append(head);
    const form = el("div", "rt-form");
    const goal = el("textarea");
    goal.rows = 4;
    goal.placeholder = t("rt.goal_ph");
    goal.value = r?.goal || "";
    goal.disabled = !agent;
    if (!r) {                                          // ready-made agents: one tap fills the card
      const chips = el("div", "chips");
      for (const tp of TEMPLATES) {
        const c = el("button", "chip", `${tp.icon} ${t(`rt.tpl.${tp.key}`)}`);
        c.type = "button";
        c.addEventListener("click", () => {
          goal.value = t(`rt.tpl.${tp.key}.goal`);
          icon.value = tp.icon;
          memory.checked = tp.memory;
          plugs.querySelectorAll("input").forEach((i) => { i.checked = tp.plugins.includes(i.value); });
          sched.replaceWith(sched = scheduleEditor(tp.sched));
          goal.focus();
        });
        chips.append(c);
      }
      form.append(el("p", "muted", t("rt.tpl_hint")), chips);
    }
    form.append(r?.plugin ? el("p", "", `🧩 ${r.plugin}.${r.tool}`)
      : r?.kind === "story" ? el("p", "", t(`rt.story.${r.action || "make"}`)) : goal);
    if (r?.by === "aurora") form.append(el("p", "muted", `✨ ${t("rt.made_by_aurora")}`));
    let sched = scheduleEditor(r?.schedule || { every: "custom", times: ["08:00"], group: "all" });
    const notify = el("select");
    for (const v of ["always", "if_any", "if_new", "never"]) { const o = el("option", "", t(`rt.n.${v}`)); o.value = v; o.selected = (r?.notify || "if_any") === v; notify.append(o); }
    const schedRow = el("div", "ev");
    schedRow.append(sched, notify);
    form.append(schedRow);
    const memory = el("input"); memory.type = "checkbox"; memory.checked = r ? Boolean(r.memory) : true;
    const steps = el("input"); steps.type = "number"; steps.min = 3; steps.max = 60; steps.value = r?.steps || 15;
    const minutes = el("input"); minutes.type = "number"; minutes.min = 1; minutes.max = 60; minutes.value = r?.minutes || 10;
    const plugs = el("div", "rt-plugins");
    if (agent) {
      const lab = (input, key) => { const l = el("label", "rt-opt"); l.append(input, el("span", "", t(key))); return l; };
      const budget = el("div", "ev");
      budget.append(lab(memory, "rt.memory"), el("span", "muted", t("rt.steps")), steps, el("span", "muted", t("rt.minutes")), minutes);
      for (const p of (this.plugins || []).filter((x) => x.available)) {
        const cb = el("input"); cb.type = "checkbox"; cb.value = p.name; cb.checked = (r?.plugins || []).includes(p.name);
        const l = el("label", "rt-day"); l.append(cb, el("span", "", p.name)); plugs.append(l);
      }
      form.append(budget, el("p", "muted", t("rt.plugins_hint")), plugs);
    }
    const out = el("span", "muted");
    const bar = el("div", "appr-actions");
    const spec = () => {
      const s = { schedule: sched.value(), notify: notify.value, icon: icon.value.trim() || undefined };
      if (agent) {
        const chosen = [...plugs.querySelectorAll("input:checked")].map((i) => i.value);
        Object.assign(s, { goal: goal.value.trim(), memory: memory.checked, steps: Number(steps.value), minutes: Number(minutes.value),
          plugins: chosen.length ? chosen : undefined });
        if (!r) Object.assign(s, { kind: "agent", title: s.goal.slice(0, 80), event: "routine.done" });
      }
      return s;
    };
    const save = el("button", "primary", `💾 ${t(r ? "rt.save_all" : "rt.add")}`);
    save.addEventListener("click", async () => {
      try {
        if (r) await call(`/v1/aurora/routines/${r.id}`, { method: "PUT", body: JSON.stringify(spec()) });
        else { if (!goal.value.trim()) { goal.focus(); return; } await call("/v1/aurora/routines", { method: "POST", body: JSON.stringify(spec()) }); }
        shut();
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
    bar.append(save);
    if (r) {
      const now = el("button", "", t("rt.run_now"));
      now.addEventListener("click", async () => { now.disabled = true; await call(`/v1/aurora/routines/${r.id}/run`, { method: "POST", body: "{}" }); now.textContent = t("rt.started"); });
      const toggle = el("button", "", r.enabled ? `⏸️ ${t("rt.pause")}` : `▶️ ${t("rt.resume")}`);
      toggle.addEventListener("click", async () => { await call(`/v1/aurora/routines/${r.id}`, { method: "PUT", body: JSON.stringify({ enabled: !r.enabled }) }); shut(); });
      const copy = el("button", "", `⧉ ${t("rt.clone")}`);
      copy.addEventListener("click", async () => { const c = await call(`/v1/aurora/routines/${r.id}/clone`, { method: "POST" }); shut(); this.open(c); });
      const del = el("button", "danger", `🗑️ ${t("rt.remove")}`);
      del.addEventListener("click", async () => { if (confirm(t("rt.confirm_remove"))) { await call(`/v1/aurora/routines/${r.id}`, { method: "DELETE" }); shut(); } });
      bar.append(now, toggle, copy, del);
    }
    bar.append(out);
    form.append(bar);
    if (r?.last_run) {                                 // what it found last time
      const last = el("div", "rt-last");
      last.append(el("div", "muted", `${t("rt.last")} ${clock(r.last_run)} ${r.last_ok === false ? "❌" : r.last_ok ? "✅" : "⏳"}`));
      if (r.last_text) last.append(renderMarkdown(r.last_text));
      if (r.last_files?.length) {
        const row = el("div", "chips");
        for (const f of r.last_files) {
          const a = viewLink(el("a", "chip"), f.url, f.name, f.mime);
          a.append(el("span", "", "📄"), el("span", "", f.name));
          row.append(a);
        }
        last.append(row);
      }
      form.append(last);
    }
    dlg.append(form);
    document.body.append(dlg);
    dlg.showModal();
  },
};

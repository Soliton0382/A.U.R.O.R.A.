// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💶 Spese (owner, 1 Nov: «la possibilità di aggiungere le spese… gestire entrate stipendio e uscite fisse, e grafici
// che indicano un andamento con magari un obiettivo di risparmio mensile… utile, completa ma semplice»; «sotto sezioni
// cliccabili… nello stile delle altre pagine»). Four parts: the month at a glance, the movements, the fixed ones of
// every month, the goal and the budgets. Everything is also said to Aurora in the chat (the expenses plugin, the same
// file: fin_store).
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { categoryBars, yearChart } from "./expenses_chart.js";
import { pluginSlot } from "./plugin_slot.js";

const TABS = ["glance", "moves", "fixed", "goals"];
const ICON = { casa: "🏠", spesa: "🛒", bollette: "💡", trasporti: "🚆", auto: "🚗", salute: "🩺", svago: "🎉", ristoranti: "🍝",
  viaggi: "✈️", abbigliamento: "👕", tecnologia: "💻", abbonamenti: "🔁", regali: "🎁", tasse: "🧾", altro: "📦",
  stipendio: "💼", pensione: "🏦", rimborsi: "↩️", vendite: "🏷️" };
const thisMonth = () => new Date().toISOString().slice(0, 7);
const shift = (m, n) => { const d = new Date(`${m}-01T12:00:00`); d.setMonth(d.getMonth() + n); return d.toISOString().slice(0, 7); };

export default {
  id: "expenses",
  icon: "💶",
  title: "nav.expenses",
  plugin: "expenses",                 // in the menu only when that plugin is on

  mount(root) {
    useCss("/static/css/projects.css");
    useCss("/static/css/expenses.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.expenses"></h2><p class="muted" data-i18n="exp.hint"></p>
      <div class="prj-tabs">${TABS.map((k, i) => `<button type="button" class="cat-chip${i ? "" : " on"}" data-tab="${k}" data-i18n="exp.tab.${k}"></button>`).join("")}</div>
      <div class="exp-monthbar"><button type="button" class="exp-prev" aria-label="‹">‹</button><b class="exp-mname"></b><button type="button" class="exp-next" aria-label="›">›</button></div>
      ${TABS.map((k, i) => `<div class="exp-tab" data-tab="${k}"${i ? " hidden" : ""}></div>`).join("")}`;
    root.querySelector("h2")?.after(pluginSlot("expenses"));   // its plugin, configured here
    root.querySelectorAll(".prj-tabs button").forEach((b) => b.addEventListener("click", () => {
      root.querySelectorAll(".prj-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      root.querySelectorAll(".exp-tab").forEach((p) => { p.hidden = p.dataset.tab !== b.dataset.tab; });
    }));
    root.querySelector(".exp-prev").addEventListener("click", () => this.load(shift(this.month, -1)));
    root.querySelector(".exp-next").addEventListener("click", () => this.load(shift(this.month, 1)));
    apply(root);
    this.root = root;
  },

  async enter() { await this.load(this.month || thisMonth()); },

  fmt(cents, short = false) {
    const cur = this.v?.currency || "EUR";
    return new Intl.NumberFormat(lang.replace("_", "-"), { style: "currency", currency: cur,
      maximumFractionDigits: short ? 0 : 2, minimumFractionDigits: short ? 0 : 2, useGrouping: "always" }).format(cents / 100);
  },
  monthName(m, long = false) {
    return new Date(`${m}-01T12:00:00`).toLocaleDateString(lang.replace("_", "-"), long ? { month: "long", year: "numeric" } : { month: "short" });
  },
  label(c) { return `${ICON[c] || "📦"} ${t(`exp.cat.${c}`)}`; },

  async load(month) {
    this.month = month;
    try { this.v = await call(`/v1/aurora/expenses?month=${month}`); }
    catch (e) { this.root.querySelector(".exp-tab[data-tab=glance]").replaceChildren(el("p", "error", e.message)); return; }
    this.root.querySelector(".exp-mname").textContent = this.monthName(month, true);
    this.root.querySelector(".exp-next").disabled = month >= thisMonth();
    const tab = (k) => this.root.querySelector(`.exp-tab[data-tab=${k}]`);
    tab("glance").replaceChildren(...this.glance());
    tab("moves").replaceChildren(this.form(false), ...this.moves());
    tab("fixed").replaceChildren(...this.fixed(), this.form(true));
    tab("goals").replaceChildren(...this.goals());
  },

  async send(path, method, body) {
    try { await call(path, { method, body: body ? JSON.stringify(body) : undefined }); await this.load(this.month); }
    catch (e) { alert(e.message); }
  },

  // 📊 the month at a glance: three tiles, the goal's progress, the year and the categories
  glance() {
    const v = this.v, out = [];
    const tiles = el("div", "exp-tiles");
    const tile = (cls, label, cents, sub) => {
      const d = el("div", `exp-tile ${cls}`);
      d.append(el("span", "exp-tile-label", label), el("b", "exp-tile-val", this.fmt(cents)));
      if (sub) d.append(sub);
      return d;
    };
    const diff = v.spent_before ? Math.round((v.spent - v.spent_before) / v.spent_before * 100) : null;
    let goal = null;
    if (v.goal) {
      goal = el("div", "exp-progress");
      const pct = Math.max(0, Math.min(100, Math.round(v.saved / v.goal * 100)));
      const bar = el("div", "exp-progress-bar");
      bar.style.width = `${pct}%`;
      goal.append(el("div", "exp-progress-track"), el("span", "muted", t(v.saved >= v.goal ? "exp.goal_hit" : "exp.goal_of", { g: this.fmt(v.goal, true), p: pct })));
      goal.firstChild.append(bar);
    }
    tiles.append(tile("in", `${t("exp.in")}`, v.income),
      tile("out", t("exp.out"), v.spent, diff === null ? null : el("span", "muted", t("exp.vs_before", { d: `${diff > 0 ? "+" : ""}${diff}%` }))),
      tile(v.saved >= 0 ? "saved" : "saved neg", t("exp.saved"), v.saved, goal));
    out.push(tiles);
    if (!v.income && !v.spent) out.push(el("p", "muted", t("exp.empty")));
    const narrow = this.root.clientWidth < 560;
    out.push(el("h3", "setting-cat", t(narrow ? "exp.chart_half" : "exp.chart_year")), yearChart(narrow ? v.trend.slice(-6) : v.trend, v.goal, (c, s) => this.fmt(c, s), (m, l) => this.monthName(m, l), narrow));
    const cats = v.categories.filter((c) => c.cents || c.budget);
    if (cats.length) out.push(el("h3", "setting-cat", t("exp.by_cat")), categoryBars(cats, v.spent, (c) => this.fmt(c), (c) => this.label(c)));
    return out;
  },

  // ➕ the add form: a spending or an income; «ogni mese» makes it a fixed one from that day
  form(monthly) {
    const f = el("form", "exp-form");
    const today = new Date().toISOString().slice(0, 10);
    const day = this.month === thisMonth() ? today : `${this.month}-01`;
    f.innerHTML = `<div class="exp-kind"><button type="button" class="cat-chip on" data-kind="out">− ${t("exp.out_one")}</button><button type="button" class="cat-chip" data-kind="in">+ ${t("exp.in_one")}</button></div>
      <input name="amount" inputmode="decimal" required placeholder="${t("exp.amount")}">
      <input name="what" required placeholder="${t(monthly ? "exp.what_fixed" : "exp.what")}">
      <select name="category"></select>
      <input name="day" type="date" value="${day}"${monthly ? " hidden" : ""}>
      <label class="exp-dom"${monthly ? "" : " hidden"}>${t("exp.dom")} <input name="dom" type="number" min="1" max="31" value="${new Date().getDate()}"></label>
      <label class="exp-monthly"${monthly ? " hidden" : ""}><input type="checkbox" name="monthly"${monthly ? " checked" : ""}> 🔁 ${t("exp.monthly")}</label>
      <button type="submit">${t(monthly ? "exp.add_fixed" : "exp.add")}</button>`;
    let kind = "out";
    const fill = () => { f.category.replaceChildren(...this.v.choices[kind].map((c) => { const o = el("option", "", this.label(c)); o.value = c; return o; })); };
    f.querySelectorAll(".exp-kind button").forEach((b) => b.addEventListener("click", () => {
      kind = b.dataset.kind;
      f.querySelectorAll(".exp-kind button").forEach((x) => x.classList.toggle("on", x === b));
      fill();
    }));
    fill();
    f.monthly.addEventListener("change", () => {           // every month: a day of the month, not a date
      f.day.hidden = f.monthly.checked;
      f.querySelector(".exp-dom").hidden = !f.monthly.checked;
      if (f.monthly.checked) f.dom.value = Number(f.day.value.slice(8)) || 1;
    });
    f.addEventListener("submit", (ev) => {
      ev.preventDefault();
      this.send("/v1/aurora/expenses/moves", "POST", { kind, amount: f.amount.value, what: f.what.value, category: f.category.value,
        day: f.day.value, dom: f.dom.value, monthly: f.monthly.checked });
    });
    return f;
  },

  // 📋 the month's movements, newest first
  moves() {
    const v = this.v;
    if (!v.moves.length) return [el("p", "muted", t("exp.no_moves"))];
    const list = el("div", "exp-moves");
    for (const m of v.moves) {
      const row = el("div", `exp-move ${m.kind}`);
      const del = el("button", "exp-del", "🗑");
      del.type = "button";
      del.title = t("exp.delete");
      del.addEventListener("click", () => { if (confirm(t("exp.delete_q", { w: m.what }))) this.send(`/v1/aurora/expenses/moves/${m.kind}/${m.id}`, "DELETE"); });
      row.append(el("span", "exp-move-day", new Date(`${m.day}T12:00:00`).toLocaleDateString(lang.replace("_", "-"), { day: "numeric", month: "short" })),
        el("span", "exp-move-what", `${m.what}${m.fixed ? " 🔁" : ""}`), el("span", "exp-move-cat muted", this.label(m.category)),
        el("b", "exp-move-amt", `${m.kind === "in" ? "+" : "−"} ${this.fmt(m.cents)}`), del);
      list.append(row);
    }
    return [list];
  },

  // 🔁 the fixed ones: what comes in and goes out every month, and what is left for the rest
  fixed() {
    const v = this.v, out = [el("p", "muted", t("exp.fixed_hint"))];
    const sum = (k) => v.fixed.filter((x) => x.kind === k).reduce((a, x) => a + x.cents, 0);
    const left = sum("in") - sum("out");
    out.push(el("p", "exp-left", t("exp.fixed_left", { i: this.fmt(sum("in")), o: this.fmt(sum("out")), l: this.fmt(left) })));
    for (const k of ["in", "out"]) {
      const items = v.fixed.filter((x) => x.kind === k);
      out.push(el("h3", "setting-cat", t(k === "in" ? "exp.fixed_in" : "exp.fixed_out")));
      if (!items.length) { out.push(el("p", "muted", t("exp.none"))); continue; }
      const list = el("div", "exp-moves");
      for (const x of items) {
        const row = el("div", `exp-move ${k}`);
        const stop = el("button", "exp-del", "🛑");
        stop.type = "button";
        stop.title = t("exp.stop");
        stop.addEventListener("click", () => { if (confirm(t("exp.stop_q", { w: x.what }))) this.send(`/v1/aurora/expenses/fixed/${x.id}`, "DELETE"); });
        // the day and the amount changed in place, from this month on (this month's movement follows)
        const dom = el("input", "exp-fix-dom");
        Object.assign(dom, { type: "number", min: 1, max: 31, value: x.dom, title: t("exp.dom") });
        const amt = el("input", "exp-fix-amt");
        Object.assign(amt, { inputMode: "decimal", value: (x.cents / 100).toFixed(2).replace(".", ","), title: t("exp.amount") });
        const put = (body) => this.send(`/v1/aurora/expenses/fixed/${x.id}`, "PUT", body);
        dom.addEventListener("change", () => put({ dom: Number(dom.value) }));
        amt.addEventListener("change", () => put({ amount: amt.value }));
        const day = el("label", "exp-move-day");
        day.append(t("exp.on_day_short"), dom);
        row.append(day, el("span", "exp-move-what", x.what), el("span", "exp-move-cat muted", this.label(x.category)), amt, stop);
        list.append(row);
      }
      out.push(list);
    }
    out.push(el("h3", "setting-cat", t("exp.add_fixed")));
    return out;
  },

  // 🎯 the saving goal (with how the year went) and the budgets per category
  goals() {
    const v = this.v, out = [];
    const g = el("form", "exp-goalform");
    g.innerHTML = `<label>${t("exp.goal_label")} <input name="amount" inputmode="decimal" value="${v.goal ? (v.goal / 100).toFixed(0) : ""}" placeholder="0"></label><button type="submit">${t("exp.save")}</button>`;
    g.addEventListener("submit", (ev) => { ev.preventDefault(); this.send("/v1/aurora/expenses/goal", "PUT", { amount: g.amount.value || "0" }); });
    out.push(el("h3", "setting-cat", t("exp.goal")), el("p", "muted", t("exp.goal_hint")), g);
    const done = v.trend.filter((m) => m.income || m.spent);
    if (done.length) {
      const avg = Math.round(done.reduce((a, m) => a + m.saved, 0) / done.length);
      const hit = v.goal ? done.filter((m) => m.saved >= v.goal).length : null;
      out.push(el("p", "exp-left", t("exp.goal_year", { a: this.fmt(avg), n: done.length })
        + (hit === null ? "" : ` ${t("exp.goal_hits", { h: hit, n: done.length })}`)));
    }
    out.push(el("h3", "setting-cat", t("exp.budgets")), el("p", "muted", t("exp.budgets_hint")));
    const spent = Object.fromEntries(v.categories.map((c) => [c.category, c]));
    const list = el("div", "exp-budgets");
    for (const c of v.choices.out) {
      const row = el("form", "exp-budgetrow");
      const cur = spent[c];
      row.innerHTML = `<span>${this.label(c)}</span><span class="muted">${cur?.cents ? this.fmt(cur.cents) : "—"}</span>
        <input name="amount" inputmode="decimal" value="${cur?.budget ? (cur.budget / 100).toFixed(0) : ""}" placeholder="${t("exp.no_budget")}">`;
      row.amount.addEventListener("change", () => this.send("/v1/aurora/expenses/budget", "PUT", { category: c, amount: row.amount.value || "0" }));
      row.addEventListener("submit", (ev) => ev.preventDefault());
      list.append(row);
    }
    out.push(list);
    return out;
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧭 Autonomy (owner, 2026-10-05): how free Aurora is, area by area. Owner, 2026-10-15: «incasinata come era quella
// dei modelli… nel medesimo stile»: tabs as on the Models page — the choice first (four cards: what she does by
// herself, what she proposes, what she always asks), the areas in groups under «Su misura», then what she did and
// how her proposals went. A level is a set of settings: reading the page reads them, a click writes them.
import { call } from "../api.js";
import { el, info, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { apiBack } from "../restart.js";

useCss("/static/css/models_mode.css");

const ICON = { 0: "🔒", 1: "🤝", 2: "🚀" };
const AREA_ICON = { social: "📣", forge: "🧰", repairs: "🔧", security: "🛡️", updates: "⬆️", knowledge: "📚", inner: "💭",
  study: "🌙", shadow: "🌗", morning: "☀️", train: "🏋️", devices: "🏠", home: "💡",
  deduce: "💡", synapses: "🧠", review: "🔁", harvest: "🌾", projects: "🏗️", edge: "☁️" };
const TABS = ["choose", "custom", "done", "stats", "users"];
const CARDS = ["careful", "balanced", "free", "custom"];

async function restart(services) {
  if (services?.length) await call("/v1/aurora/services/restart", { method: "POST", body: JSON.stringify({ services }) }).catch(() => null);
}

const areaName = (id) => `${AREA_ICON[id] || "•"} ${t(`auto.area.${id}`)}`;

export default {
  id: "autonomy",
  icon: "🧭",
  title: "nav.autonomy",

  mount(root) {
    this.root = root;
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="auto.title"></h2><p class="muted" data-i18n="auto.hint"></p>
      <div class="prj-tabs md-tabs">${TABS.map((x, i) => `<button type="button" class="cat-chip${i ? "" : " on"}" data-tab="${x}" data-i18n="auto.tab.${x}"></button>`).join("")}</div>
      <div class="md-tab" data-tab="choose"><div class="auto-choice"></div></div>
      <div class="md-tab" data-tab="custom" hidden><div class="auto-areas"></div></div>
      <div class="md-tab" data-tab="done" hidden><div class="auto-days"></div></div>
      <div class="md-tab" data-tab="stats" hidden><p class="muted" data-i18n="auto.stats_hint"></p><div class="auto-stats"></div></div>
      <div class="md-tab" data-tab="users" hidden><div class="auto-users"></div></div>
      <p class="muted auto-out"></p>`;
    apply(root);
    this.q = (s) => root.querySelector(s);
    root.querySelectorAll(".md-tabs button").forEach((b) => b.addEventListener("click", () => this.show(b.dataset.tab)));
  },

  show(tab) {
    this.root.querySelectorAll(".md-tabs button").forEach((x) => x.classList.toggle("on", x.dataset.tab === tab));
    this.root.querySelectorAll(".md-tab").forEach((p) => { p.hidden = p.dataset.tab !== tab; });
  },

  async set(body) {
    const out = this.q(".auto-out");
    out.textContent = t("auto.saving");
    try {
      const r = await call("/v1/aurora/autonomy", { method: "PUT", body: JSON.stringify(body) });
      out.textContent = r.restart.length ? t("auto.saved_restart", { s: r.restart.join(", ") }) : t("auto.saved");
      await restart(r.restart);
      if (r.restart.includes("aurora-api")) await apiBack();   // the page reloads only once the API is back (the "" error)
      await this.enter();
      out.textContent = t("auto.saved");
    } catch (e) { out.textContent = t("ev.error", { m: e.message || t("auto.offline") }); }
  },

  // the four cards: a profile's levels on the areas shown, or today's for «custom»
  choice(v) {
    const shown = v.areas.map((a) => a.id);
    const levelsOf = (id) => Object.fromEntries(shown.map((a) => [a, id === "custom"
      ? v.areas.find((x) => x.id === a).level : v.profiles[id][a]]));
    const stat = (label, value, note) => {
      const d = el("span", "mch-stat");
      d.append(el("small", "", label), el("strong", "", String(value)), el("small", "", note));
      return d;
    };
    const panel = (title, ids) => {
      const d = el("div", "mch-panel");
      const ul = el("ul");
      ul.append(...(ids.length ? ids.map((a) => el("li", "", areaName(a))) : [el("li", "muted", "—")]));
      d.append(el("h4", "", title), ul);
      return d;
    };
    const box = el("div");
    let picked = v.profile;
    const draw = () => {
      const cards = el("div", "mch-cards");
      cards.append(...CARDS.map((id) => {
        const lv = levelsOf(id);
        const n = (k) => shown.filter((a) => lv[a] === k).length;
        const b = el("button", `mch-card${id === picked ? " on" : ""}`);
        b.type = "button";
        b.setAttribute("aria-pressed", String(id === picked));
        const head = el("span", "mch-head");
        head.append(el("strong", "", t(`auto.profile.${id}`)));
        if (id === "balanced") head.append(el("span", "mch-tag", t("auto.advised")));
        if (id === v.profile) head.append(el("span", "mch-now", `● ${t("mm.now")}`));
        const stats = el("span", "mch-stats");
        stats.append(stat(`🚀 ${t("auto.level.2")}`, n(2), t("auto.of_areas", { n: shown.length })),
          stat(`🔒 ${t("auto.level.0")}`, n(0), t("auto.of_areas", { n: shown.length })));
        b.append(head, el("span", "mch-line", t(`auto.card.${id}`)), stats);
        b.addEventListener("click", () => { picked = id; draw(); });
        return b;
      }));
      const lv = levelsOf(picked);
      const detail = el("div", "mch-detail");
      const guards = el("div", "mch-panel");
      guards.append(el("h4", "", t("auto.guards")), el("p", "", t("auto.guard_ethics")),
        el("p", v.exempt ? "" : "error", t(v.exempt ? "auto.exempt_on" : "auto.not_exempt")));
      detail.append(panel(t("auto.panel.alone"), shown.filter((a) => lv[a] === 2)),
        panel(t("auto.panel.proposes"), shown.filter((a) => lv[a] === 1)),
        panel(t("auto.panel.asks"), shown.filter((a) => lv[a] === 0)), guards);
      const bar = el("div", "mch-apply");
      const go = el("button", "approve", t(picked === "custom" ? "auto.open_custom" : picked === v.profile ? "auto.in_use" : "auto.use"));
      go.disabled = (picked === v.profile && picked !== "custom") || !(v.admin || v.may_choose);
      go.addEventListener("click", () => (picked === "custom" ? this.show("custom") : this.set({ profile: picked })));
      bar.append(el("span", "", t("auto.apply")), go);
      box.replaceChildren(cards, detail, bar);
    };
    draw();
    return box;
  },

  areaRow(a, user) {
    const row = el("div", "auto-area");
    const name = el("div", "auto-name");
    // ⓘ what each level of this area does (owner, 2026-10-06: "it is not clear which buttons can be clicked")
    const explain = a.levels.map((n) => `${ICON[n]} ${t(`auto.level.${n}`)}: ${t(`auto.what.${a.id}.${n}`)}`).join("\n");
    name.append(el("strong", "", areaName(a.id)), info(explain),
      el("span", "muted", a.level === null ? ` · ${t("auto.by_hand")}` : ""));
    const levels = el("div", "auto-levels");
    for (const n of a.levels) {                          // only the levels this area has: no button that cannot be pressed
      const b = el("button", a.level === n ? "approve" : "", `${ICON[n]} ${t(`auto.level.${n}`)}`);
      b.title = t(`auto.what.${a.id}.${n}`);
      b.disabled = !a.mine;
      b.addEventListener("click", () => this.set({ levels: { [a.id]: n }, ...(user ? { user } : {}) }));
      levels.append(b);
    }
    row.append(name, levels, el("p", "muted auto-now", a.level === null ? "" : t(`auto.what.${a.id}.${a.level}`)));
    return row;
  },

  // «Su misura»: the areas in their groups, then what she always does without changing anything
  groups(v) {
    const by = Object.fromEntries(v.areas.map((a) => [a.id, a]));
    const out = [];
    for (const [g, ids] of Object.entries(v.groups)) {
      const rows = ids.filter((id) => by[id]).map((id) => this.areaRow(by[id]));
      if (!rows.length) continue;
      const box = el("section", "mch-panel auto-group");
      box.append(el("h4", "", t(`auto.group.${g}`)), el("p", "muted", t(`auto.group_hint.${g}`)), ...rows);
      out.push(box);
    }
    if (v.admin) {
      const always = el("section", "mch-panel auto-group");
      const ul = el("ul");
      ul.append(...v.always.map((k) => el("li", "", t(`auto.always.${k}`))));
      always.append(el("h4", "", t("auto.always_title")), el("p", "muted", t("auto.always_hint")), ul);
      out.push(always);
    }
    if (!v.admin) out.push(el("p", "muted", t(v.may_choose ? "auto.user_note" : "auto.user_admin_decides")));
    return out;
  },

  days(list) {
    if (!list.length) return [el("p", "muted", t("auto.no_days"))];
    return list.map((d) => {
      const det = el("details", "report");
      const areas = Object.entries(d.areas).map(([a, n]) => `${AREA_ICON[a] || "•"} ${n}`).join("  ");
      det.append(el("summary", "", `${d.day} · ${t("auto.did", { n: d.count })} · ${areas}`));
      for (const it of d.items) {
        const when = new Date(it.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        det.append(el("p", "", `${when} ${AREA_ICON[it.area] || "•"} ${it.text}`));
      }
      return det;
    });
  },

  stats(st) {
    const tbl = el("table", "auto-table");
    const head = el("tr");
    for (const h of ["area", "proposed", "approved", "refused", "alone", "undone", "rate"]) head.append(el("th", "", t(`auto.col.${h}`)));
    tbl.append(head);
    // the areas with something to count first; the empty ones folded into one line
    const rows = Object.entries(st).filter(([, s]) => s.proposed || s.alone);
    for (const [a, s] of rows) {
      const r = el("tr");
      r.append(el("td", "", `${areaName(a)}${s.proved ? " ✅" : ""}`));
      for (const k of ["proposed", "approved", "refused", "alone", "undone"]) r.append(el("td", "", String(s[k] || 0)));
      r.append(el("td", "", s.rate === null ? "—" : `${Math.round(100 * s.rate)}%`));
      if (s.proved) r.title = t("auto.proved");
      tbl.append(r);
    }
    const quiet = Object.entries(st).filter(([, s]) => !s.proposed && !s.alone).map(([a]) => areaName(a));
    return [tbl, ...(quiet.length ? [el("p", "muted", t("auto.quiet", { a: quiet.join(" · ") }))] : [])];
  },

  users(v) {
    if (!v.users.length) return [el("p", "muted", t("auto.no_users"))];
    return v.users.map((u) => {
      const box = el("div", "appr-card");
      const may = el("input");
      may.type = "checkbox";
      may.checked = u.may_choose;
      may.addEventListener("change", async () => {
        await call("/v1/aurora/autonomy/may-choose", { method: "PUT", body: JSON.stringify({ user: u.name, allowed: may.checked }) });
      });
      const lbl = el("label", "", "");
      lbl.append(may, el("span", "", ` ${t("auto.may_choose")}`));
      const own = u.areas.filter((a) => a.scope === "user").map((a) => this.areaRow({ ...a, mine: true }, u.name));
      box.append(el("div", "appr-head", `👤 ${u.name} · ${t(`auto.profile.${u.profile}`)}`), lbl, ...own);
      return box;
    });
  },

  async enter() {
    let v;
    try { v = await call("/v1/aurora/autonomy"); } catch (e) { this.q(".auto-out").textContent = t("ev.error", { m: e.message }); return; }
    // a user sees the areas that are theirs; the machine's are the admin's (said once, not as grey buttons)
    if (!v.admin) v.areas = v.areas.filter((a) => a.mine || a.scope === "user");
    this.q(".auto-choice").replaceChildren(this.choice(v));
    this.q(".auto-areas").replaceChildren(...this.groups(v));
    this.q(".auto-days").replaceChildren(...this.days(v.days));
    for (const tab of ["stats", "users"]) this.root.querySelector(`.md-tabs [data-tab="${tab}"]`).hidden = !v.admin;
    if (!v.admin) return;
    this.q(".auto-stats").replaceChildren(...this.stats(v.stats));
    this.q(".auto-users").replaceChildren(...this.users(v));
  },
};

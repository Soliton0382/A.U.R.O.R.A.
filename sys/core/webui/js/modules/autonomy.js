// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧭 Autonomy (owner, 2026-10-05): how free Aurora is, area by area — ready profiles, three levels per area (🔒 ask,
// 🤝 propose, 🚀 by herself within limits), what she did by herself day by day, the statistics of her proposals, and
// for the admin each user's profile and whether they may choose it. A level is a set of settings: reading the page
// reads the settings, a click writes them (then the services that read them restart).
import { call } from "../api.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";

const ICON = { 0: "🔒", 1: "🤝", 2: "🚀" };
const AREA_ICON = { social: "📣", forge: "🧰", repairs: "🔧", security: "🛡️", updates: "⬆️", knowledge: "📚", inner: "💭" };

async function restart(services) {
  if (services?.length) await call("/v1/aurora/services/restart", { method: "POST", body: JSON.stringify({ services }) }).catch(() => null);
}

export default {
  id: "autonomy",
  icon: "🧭",
  title: "nav.autonomy",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="auto.title"></h2><p class="muted" data-i18n="auto.hint"></p>
      <p class="warn auto-exempt" hidden data-i18n="auto.not_exempt"></p>
      <h3 class="setting-cat" data-i18n="auto.profiles"></h3><div class="auto-profiles"></div>
      <h3 class="setting-cat" data-i18n="auto.areas"></h3><div class="auto-areas"></div><p class="muted auto-out"></p>
      <h3 class="setting-cat" data-i18n="auto.daily"></h3><div class="auto-days"></div>
      <div class="auto-admin" hidden>
        <h3 class="setting-cat" data-i18n="auto.stats"></h3><p class="muted" data-i18n="auto.stats_hint"></p><div class="auto-stats"></div>
        <h3 class="setting-cat" data-i18n="auto.users"></h3><div class="auto-users"></div>
      </div>`;
    apply(root);
    this.q = (s) => root.querySelector(s);
  },

  async set(body) {
    const out = this.q(".auto-out");
    out.textContent = t("auto.saving");
    try {
      const r = await call("/v1/aurora/autonomy", { method: "PUT", body: JSON.stringify(body) });
      out.textContent = r.restart.length ? t("auto.saved_restart", { s: r.restart.join(", ") }) : t("auto.saved");
      await restart(r.restart);
      setTimeout(() => this.enter(), r.restart.includes("aurora-api") ? 4000 : 300);
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
  },

  profiles(v, user) {
    return Object.keys(v.profiles).map((p) => {
      const b = el("button", v.profile === p ? "approve" : "", t(`auto.profile.${p}`));
      b.title = t(`auto.profile_hint.${p}`);
      b.disabled = !(v.admin || v.may_choose);
      b.addEventListener("click", () => this.set({ profile: p, ...(user ? { user } : {}) }));
      return b;
    });
  },

  areaRow(a, user) {
    const row = el("div", "auto-area");
    const name = el("div", "auto-name");
    name.append(el("strong", "", `${AREA_ICON[a.id] || "•"} ${t(`auto.area.${a.id}`)}`),
      el("span", "muted", a.level === null ? ` · ${t("auto.by_hand")}` : ""));
    const levels = el("div", "auto-levels");
    for (const n of [0, 1, 2]) {
      const b = el("button", a.level === n ? "approve" : "", `${ICON[n]} ${t(`auto.level.${n}`)}`);
      b.title = t(`auto.what.${a.id}.${n}`);
      b.disabled = !a.levels.includes(n) || !a.mine;
      if (!a.levels.includes(n)) b.classList.add("auto-none");
      b.addEventListener("click", () => this.set({ levels: { [a.id]: n }, ...(user ? { user } : {}) }));
      levels.append(b);
    }
    const now = a.level === null ? "" : t(`auto.what.${a.id}.${a.level}`);
    row.append(name, levels, el("p", "muted auto-now", now));
    return row;
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
    for (const [a, s] of Object.entries(st)) {
      const r = el("tr");
      r.append(el("td", "", `${AREA_ICON[a] || "•"} ${t(`auto.area.${a}`)}${s.proved ? " ✅" : ""}`));
      for (const k of ["proposed", "approved", "refused", "alone", "undone"]) r.append(el("td", "", String(s[k] || 0)));
      r.append(el("td", "", s.rate === null ? "—" : `${Math.round(100 * s.rate)}%`));
      if (s.proved) r.title = t("auto.proved");
      tbl.append(r);
    }
    return tbl;
  },

  async enter() {
    let v;
    try { v = await call("/v1/aurora/autonomy"); } catch (e) { this.q(".auto-out").textContent = t("ev.error", { m: e.message }); return; }
    this.q(".auto-exempt").hidden = v.exempt;
    this.q(".auto-profiles").replaceChildren(...this.profiles(v), el("span", "muted", v.profile === "custom" ? ` ${t("auto.custom")}` : ""));
    this.q(".auto-areas").replaceChildren(...v.areas.map((a) => this.areaRow(a)));
    this.q(".auto-days").replaceChildren(...this.days(v.days));
    this.q(".auto-admin").hidden = !v.admin;
    if (!v.admin) return;
    this.q(".auto-stats").replaceChildren(this.stats(v.stats));
    this.q(".auto-users").replaceChildren(...(v.users.length ? v.users.map((u) => {
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
    }) : [el("p", "muted", t("auto.no_users"))]));
  },
};

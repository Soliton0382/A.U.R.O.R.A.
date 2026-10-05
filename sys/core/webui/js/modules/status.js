// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Services, autonomic cycle, weather, vault.
import { call } from "../api.js";
import { backupRow } from "../backup.js";
import { clock, el } from "../dom.js";
import { apply, lang, t } from "../i18n.js";

const pill = (ok, text) => el("span", `pill ${ok ? "ok" : "bad"}`, text);

export default {
  id: "status",
  icon: "📊",
  title: "nav.status",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="status.title"></h2><div class="status"></div>`;
    apply(root);
    this.box = root.querySelector(".status");
  },

  async enter() {
    const [s, rem, health] = await Promise.all([call("/v1/aurora/status"), call("/v1/aurora/rem/state").catch(() => null),
      call("/v1/aurora/health").catch(() => null)]);
    const box = this.box;
    box.replaceChildren(el("h3", "setting-cat", t("status.services")));
    for (const i of health?.items || []) {
      const row = el("div", "ev");
      const p = el("span", `pill ${i.level === "ok" ? "ok" : i.level === "warn" ? "warn" : "bad"}`, t(`status.level.${i.level}`));
      row.append(p, el("strong", "", i.name), el("span", "", i.text));
      if (i.detail) row.append(el("span", "muted", i.detail));
      box.append(row);
    }
    if (health) box.append(el("div", "muted", t("status.checked", { at: clock(health.checked) })));
    // answered and declined questions on knowledge, 7 days (owner, 2026-10-05: honesty measured, not claimed)
    const ans = await call("/v1/aurora/answers/stats?days=7").catch(() => null);
    if (ans && ans.questions) box.append(el("p", "", t("status.answers", { q: ans.questions, a: ans.answered, d: ans.declined, p: ans.declined_pct })));
    const syn = await call("/v1/aurora/synapses").catch(() => null);     // links between domains (kno_synapse)
    if (syn) {
      const pairs = syn.pairs.map((x) => `${x.a} ↔ ${x.b} ${x.n}`).join(" · ");
      box.append(el("p", "", t("status.synapses", { n: syn.links, u: syn.used, d: syn.today }) + (syn.growing ? ` ${t("status.syn_growing")}` : "")),
        ...(pairs ? [el("p", "muted", pairs)] : []));
    }
    // the soak, measured by itself (owner, 2026-10-05): a line a day — memory per service, restarts, logs, swaps
    const soak = await call("/v1/aurora/soak?days=14").catch(() => []);
    if (soak.length) {
      box.append(el("h3", "setting-cat", t("status.soak", { n: soak.length })));
      const table = el("table", "table");
      const units = Object.keys(soak[soak.length - 1].services);
      const head = el("tr");
      for (const h of [t("status.soak_day"), ...units.map((u) => u.replace("aurora-", "")), t("status.soak_logs"), t("status.soak_swaps"), t("status.soak_failed"), t("status.soak_disk")]) head.append(el("th", "", h));
      table.append(head);
      for (const d of soak.slice().reverse()) {
        const tr = el("tr");
        tr.append(el("td", "", d.day), ...units.map((u) => {
          const s = d.services[u] || {};
          return el("td", s.restarts ? "warn" : "", s.mem_mib == null ? "—" : `${Math.round(s.mem_mib)} MB${s.restarts ? ` ↻${s.restarts}` : ""}`);
        }), el("td", "", `${d.logs_mb} MB`), el("td", "", String(d.gpu_swaps_24h)), el("td", d.routines_failed_24h ? "warn" : "", String(d.routines_failed_24h)), el("td", "", `${d.disk_free_gb} GB`));
        table.append(tr);
      }
      box.append(table);
    }
    const f = await call("/v1/aurora/features").catch(() => null);
    const b = await backupRow();                  // the owner's data: where it is copied, when, how many copies
    if (b) box.append(el("h3", "setting-cat", t("status.backup")), b);
    if (f) {                                       // what works here, and the command for what is missing
      box.append(el("h3", "setting-cat", t("status.features")));
      const code = lang.slice(0, 2);
      for (const x of Object.values(f.features)) {
        const row = el("div", "ev");
        row.append(el("span", "ic", x.ok ? "✅" : x.required ? "⛔" : "⚪"), el("strong", "", x.label[code] || x.label.en));
        if (!x.ok) {
          row.append(el("span", "muted", t("status.missing", { what: x.missing.join(", ") })));
          for (const c of x.fix) row.append(el("code", "", c));
        }
        box.append(row);
      }
      for (const p of f.config) box.append(el("p", "error", `⚠️ ${p}`));
    }
    if (rem) {
      box.append(el("h3", "setting-cat", t("status.rem")));
      const last = (k) => (rem.last[k] ? clock(rem.last[k]) : "—");
      box.append(el("div", "ev", t("status.rem.line", {
        idle: rem.idle_min === null ? "—" : Math.round(rem.idle_min), sessions: rem.sessions_to_consolidate,
        memory: last("session_memory"), thought: last("thought"), dream: last("dream") })));
      const w = rem.weather;
      box.append(el("h3", "setting-cat", t("status.weather")));
      box.append(el("div", "ev", w ? t("status.weather.line", { temp: w.temperature_c, hum: w.humidity_pct,
        clouds: w.clouds_pct, rain: w.rain_mm, wind: w.wind_kmh, cond: w.condition, src: w.provider })
        : t("status.weather.off")));
    }
    box.append(el("h3", "setting-cat", t("status.vault")));
    const entries = Object.entries(s.vault || {}).sort((a, b) => b[1] - a[1]);
    if (!entries.length) { box.append(el("p", "muted", t("status.empty"))); return; }
    const table = el("table", "table");
    const head = el("tr");
    head.append(el("th", "", t("status.domain")), el("th", "", t("status.solitons")));
    table.append(head);
    let total = 0;
    for (const [d, n] of entries) {
      total += n;
      const tr = el("tr");
      tr.append(el("td", "", d), el("td", "num", n.toLocaleString()));
      table.append(tr);
    }
    const tr = el("tr", "total");
    tr.append(el("td", "", t("status.total")), el("td", "num", total.toLocaleString()));
    table.append(tr);
    box.append(table);
  },
};

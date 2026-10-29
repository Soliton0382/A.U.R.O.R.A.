// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Services, autonomic cycle, weather, vault. One line of tiles with the counts first; below, each part closed unless it
// has something to see to (owner, 30 Oct: «la pagina stato, è incasinata» — eleven parts open one under the other,
// 4284 px, the vault's table alone 1439).
import { call } from "../api.js";
import { backupRow } from "../backup.js";
import { clock, el, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { moodRows, moodTitle } from "../mood.js";
import { pluginSlot } from "./plugin_slot.js";

const VAULT_TOP = 12;                              // the vault's largest domains shown; the rest on one line

// a part of the page: its title and its count, open when it asks to be looked at
function part(box, id, title, count, open, ...body) {
  const d = el("details", "status-sec");
  d.dataset.part = id;
  d.open = !!open;
  const s = el("summary");
  s.append(el("h3", "setting-cat", title));
  if (count) s.append(el("span", `pill ${count.level}`, count.text));
  d.append(s, ...body.filter(Boolean));
  box.append(d);
  return d;
}

const tally = (ok, n) => ({ level: ok === n ? "ok" : "warn", text: `${ok}/${n}` });

export default {
  id: "status",
  icon: "📊",
  title: "nav.status",

  mount(root) {
    useCss("/static/css/status.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="status.title"></h2><div class="status-tiles"></div><div class="status"></div>`;
    root.querySelector("h2")?.after(pluginSlot("status"));   // its plugins, configured here
    apply(root);
    this.tiles = root.querySelector(".status-tiles");
    this.box = root.querySelector(".status");
  },

  async enter() {
    const get = (path, none = null) => call(path).catch(() => none);
    const [s, rem, health, ans, syn, soak, f, b] = await Promise.all([call("/v1/aurora/status"), get("/v1/aurora/rem/state"),
      get("/v1/aurora/health"), get("/v1/aurora/answers/stats?days=7"), get("/v1/aurora/synapses"),
      get("/v1/aurora/soak?days=14", []), get("/v1/aurora/features"), backupRow()]);
    const box = this.box;
    const code = lang.slice(0, 2);
    const label = (x) => x.label[code] || x.label.en;
    const tiles = [];
    box.replaceChildren();

    const items = health?.items || [];
    const up = items.filter((i) => i.level === "ok").length;
    part(box, "services", t("status.services"), items.length && tally(up, items.length), up < items.length,
      ...items.map((i) => {
        const row = el("div", "ev");
        row.append(el("span", `pill ${i.level === "ok" ? "ok" : i.level === "warn" ? "warn" : "bad"}`, t(`status.level.${i.level}`)),
          el("strong", "", i.name), el("span", "", i.text));
        if (i.detail) row.append(el("span", "muted", i.detail));
        return row;
      }), health && el("div", "muted", t("status.checked", { at: clock(health.checked) })));
    if (items.length) tiles.push(["services", "⚙️", t("status.services"), `${up}/${items.length}`, up === items.length]);

    if (b) {                                       // the owner's data: where it is copied, when, how many copies
      const ok = b.querySelector(".ic")?.textContent === "✅";
      part(box, "backup", t("status.backup"), null, true, b);             // one line: always shown
      tiles.push(["backup", "💾", t("status.backup"), ok ? "✅" : "⚠️", ok]);
    }

    if (f) {                                       // what works here, and the command for what is missing
      const all = Object.values(f.features);
      const ok = all.filter((x) => x.ok).length;
      part(box, "features", t("status.features"), tally(ok, all.length), all.some((x) => !x.ok && x.required) || f.config.length,
        ...f.config.map((p) => el("p", "error", `⚠️ ${p}`)),
        ...all.map((x) => {
          const row = el("div", "ev");
          row.append(el("span", "ic", x.ok ? "✅" : x.required ? "⛔" : "⚪"), el("strong", "", label(x)));
          if (!x.ok) row.append(el("span", "muted", t("status.missing", { what: x.missing.join(", ") })), ...x.fix.map((c) => el("code", "", c)));
          return row;
        }));
      tiles.push(["features", "🧩", t("status.tile.features"), `${ok}/${all.length}`, ok === all.length]);
      // read live (sys_capabilities, owner 2026-10-06): plugins, connections, abilities — each with what is missing
      for (const [k, rows] of Object.entries(f.live || {})) {
        const n = rows.filter((x) => x.ok).length;
        const body = k === "plugins"                 // many: one line of chips, the missing keys on hover
          ? [el("div", "chips")]
          : rows.map((x) => {
            const row = el("div", "ev");
            row.append(el("span", "ic", x.ok ? "✅" : "⚪"), el("strong", "", label(x)), el("span", "muted", x.detail));
            if (!x.ok && x.fix) row.append(el("code", "", x.fix));
            return row;
          });
        if (k === "plugins") for (const x of rows) {
          const c = el("span", `chip ${x.ok ? "" : "off"}`, `${x.ok ? "✅" : "⚪"} ${label(x)}`);
          c.title = x.detail || "";
          body[0].append(c);
        }
        part(box, k, t(`status.live.${k}`, { ok: n, n: rows.length }), null, false, ...body);
        if (k !== "abilities") tiles.push([k, k === "plugins" ? "🔌" : "🔗", t(`status.tile.${k}`), `${n}/${rows.length}`, true]);
      }
    }

    if (rem?.mood?.on) part(box, "mood", `💗 ${moodTitle(rem.mood)}`, null, false, ...moodRows(rem.mood), el("div", "muted", t("mood.hint")));

    if (rem) {
      const last = (k) => (rem.last[k] ? clock(rem.last[k]) : "—");
      const w = rem.weather;
      part(box, "rem", t("status.rem"), null, false,
        el("div", "ev", t("status.rem.line", { idle: rem.idle_min === null ? "—" : Math.round(rem.idle_min),
          sessions: rem.sessions_to_consolidate, memory: last("session_memory"), thought: last("thought"), dream: last("dream") })),
        el("div", "ev", `${t("status.weather")}: ${w ? t("status.weather.line", { temp: w.temperature_c, hum: w.humidity_pct,
          clouds: w.clouds_pct, rain: w.rain_mm, wind: w.wind_kmh, cond: w.condition, src: w.provider }) : t("status.weather.off")}`));
    }

    // the soak, measured by itself (owner, 2026-10-05): a line a day — memory per service, restarts, logs, swaps
    if (soak.length) {
      const table = el("table", "table");
      const units = Object.keys(soak[soak.length - 1].services);
      const head = el("tr");
      for (const h of [t("status.soak_day"), ...units.map((u) => u.replace("aurora-", "")), t("status.soak_logs"), t("status.soak_swaps"), t("status.soak_failed"), t("status.soak_disk")]) head.append(el("th", "", h));
      table.append(head);
      for (const d of soak.slice().reverse()) {
        const tr = el("tr");
        tr.append(el("td", "", d.day), ...units.map((u) => {
          const x = d.services[u] || {};
          return el("td", x.restarts ? "warn" : "", x.mem_mib == null ? "—" : `${Math.round(x.mem_mib)} MB${x.restarts ? ` ↻${x.restarts}` : ""}`);
        }), el("td", "", `${d.logs_mb} MB`), el("td", "", String(d.gpu_swaps_24h)), el("td", d.routines_failed_24h ? "warn" : "", String(d.routines_failed_24h)), el("td", "", `${d.disk_free_gb} GB`));
        table.append(tr);
      }
      part(box, "soak", t("status.soak", { n: soak.length }), null, false, el("div", "status-scroll", table));
    }

    // what she knows: answered and declined questions (owner, 2026-10-05: honesty measured, not claimed), the links
    // between domains (kno_synapse), the vault by domain
    const entries = Object.entries(s.vault || {}).sort((a, x) => x[1] - a[1]);
    const total = entries.reduce((n, [, k]) => n + k, 0);
    const know = [];
    if (ans && ans.questions) know.push(el("p", "", t("status.answers", { q: ans.questions, a: ans.answered, d: ans.declined, p: ans.declined_pct })));
    if (syn) {
      const pairs = syn.pairs.map((x) => `${x.a} ↔ ${x.b} ${x.n}`).join(" · ");
      know.push(el("p", "", t("status.synapses", { n: syn.links, u: syn.used, d: syn.today }) + (syn.growing ? ` ${t("status.syn_growing")}` : "")));
      if (pairs) know.push(el("p", "muted", pairs));
    }
    if (!entries.length) know.push(el("p", "muted", t("status.empty")));
    else {
      const table = el("table", "table");
      const head = el("tr");
      head.append(el("th", "", t("status.domain")), el("th", "", t("status.solitons")));
      table.append(head);
      const row = (d, n, cls = "") => {
        const tr = el("tr", cls);
        tr.append(el("td", "", d), el("td", "num", n.toLocaleString()));
        table.append(tr);
      };
      for (const [d, n] of entries.slice(0, VAULT_TOP)) row(d, n);
      const rest = entries.slice(VAULT_TOP);
      if (rest.length) row(t("status.vault_more", { n: rest.length }), rest.reduce((n, [, k]) => n + k, 0), "muted");
      row(t("status.total"), total, "total");
      know.push(table);
    }
    part(box, "vault", t("status.knowledge"), { level: "ok", text: total.toLocaleString() }, false, ...know);
    tiles.push(["vault", "📚", t("status.solitons"), total.toLocaleString(), true]);

    // the tiles: each opens its part and brings it into view
    this.tiles.replaceChildren(...tiles.map(([id, icon, name, value, ok]) => {
      const b = el("button", `status-tile ${ok ? "" : "warn"}`);
      b.type = "button";
      b.append(el("span", "status-tile-label", `${icon} ${name}`), el("span", "status-tile-value", value));
      b.addEventListener("click", () => {
        const d = box.querySelector(`details[data-part="${id}"]`);
        if (d) { d.open = true; d.scrollIntoView({ behavior: "smooth", block: "start" }); }
      });
      return b;
    }));
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Registered devices and every .env value, with its explanation, editable.
import { call } from "../api.js";
import { el, info } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { restartPrompt } from "../restart.js";

const TRUE = ["1", "true", "yes", "on"];

// the areas of the settings' menu, each with its categories (a category the schema adds later goes to "system")
const AREAS = [
  ["ai", ["llm", "pipeline", "search", "embedder", "index", "memory", "rem", "autonomy", "agents"]],
  ["knowledge", ["vault", "acquire", "harvest", "attachments", "documents", "projects"]],
  ["people", ["interface", "users", "senses"]],
  ["safety", ["security", "compliance", "backup", "https"]],
  ["system", ["root", "layout", "network", "services", "logging", "plugins"]],
];

export default {
  id: "settings",
  icon: "⚙️",
  title: "nav.settings",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="devices.title"></h2>
      <p class="muted" data-i18n="devices.hint"></p>
      <div class="devices"></div>
      <h2 data-i18n="settings.title"></h2>
      <p class="muted" data-i18n="settings.hint"></p>
      <div class="settings-tools"><input class="settings-filter" type="search" data-i18n-placeholder="settings.filter">
        <div class="settings-nav"></div></div>
      <div class="settings"></div>
      <div class="settings-actions"><button class="save" data-i18n="settings.save"></button><span class="result muted"></span></div>
      <details class="report settings-danger"><summary data-i18n="settings.factory"></summary>
        <p class="muted" data-i18n="settings.factory_hint"></p>
        <label class="rt-opt"><input type="checkbox" class="keep-keys" checked><span data-i18n="settings.factory_keep"></span></label>
        <div class="appr-actions"><button class="danger factory-go" data-i18n="settings.factory_go"></button><span class="muted factory-out"></span></div>
        <p class="muted" data-i18n="settings.factory_mind"></p>
        <code class="factory-cmd">.venv/bin/python sys/core/script/sys_factory_reset.py --apply</code></details>`;
    apply(root);
    this.devices = root.querySelector(".devices");
    this.box = root.querySelector(".settings");
    this.nav = root.querySelector(".settings-nav");
    this.filter = root.querySelector(".settings-filter");
    this.filter.placeholder = t("settings.filter");
    this.filter.addEventListener("input", () => { if (this.filter.value) this.cat = ""; this.applyFilter(); });
    this.cat = "";
    this.original = {};
    const fout = root.querySelector(".factory-out");
    root.querySelector(".factory-go").addEventListener("click", async () => {      // back to the factory's settings
      if (!confirm(t("settings.factory_q"))) return;
      try {
        const r = await call("/v1/aurora/settings/factory", { method: "POST", body: JSON.stringify({ keep_keys: root.querySelector(".keep-keys").checked }) });
        fout.textContent = t("settings.factory_done", { n: r.changed.length, file: r.backup });
        await restartPrompt(r.restart);
        await this.loadSettings();
      } catch (e) { fout.textContent = t("ev.error", { m: e.message }); }
    });
    const out = root.querySelector(".result");
    root.querySelector(".save").addEventListener("click", async () => {
      const changes = {};
      this.box.querySelectorAll("[data-key]").forEach((i) => {
        if (i.dataset.secret ? i.value !== "" : i.value !== this.original[i.dataset.key]) changes[i.dataset.key] = i.value;
      });
      if (!Object.keys(changes).length) { out.textContent = t("settings.none"); return; }
      const put = (q = "") => call(`/v1/aurora/settings${q}`, { method: "PUT", body: JSON.stringify(changes) });
      try {
        let r;
        try { r = await put(); } catch (e) {
          // single ↔ multi (sys_users_mode): a refusal says why; going back to single lists who is deleted and asks
          let d = null;
          try { d = JSON.parse(e.message); } catch { /* not a structured refusal */ }
          if (e.status !== 409 || !d?.message) throw e;
          if (!d.plan?.length) throw new Error(d.message);
          const who = d.plan.map((u) => `• ${u.user}: ${u.items.reduce((n, i) => n + (i.files || 0), 0)} file`).join("\n");
          if (!confirm(t("settings.mode.purge", { who }))) { out.textContent = t("settings.none"); return; }
          r = await put("?confirm=purge");
        }
        out.textContent = t("settings.saved", { keys: r.changed.join(", "), services: r.restart.join(", ") || "—" });
        out.className = "result";
        await restartPrompt(r.restart);
        await this.loadSettings();
      } catch (e) {
        out.textContent = t("ev.error", { m: e.message });
        out.className = "result error";
      }
    });
  },

  async enter() { await Promise.all([this.loadDevices(), this.loadSettings()]); },

  async loadDevices() {
    const list = await call("/v1/aurora/devices");
    const table = el("table", "table");
    const head = el("tr");
    for (const k of ["devices.name", "devices.created", "devices.seen", ""]) head.append(el("th", "", k && t(k)));
    table.append(head);
    for (const d of list) {
      const tr = el("tr");
      const b = el("button", "", t(d.current ? "devices.logout" : "devices.revoke"));
      b.addEventListener("click", async () => {
        if (d.current) { await call("/v1/aurora/logout", { method: "POST" }); location.reload(); return; }
        await call(`/v1/aurora/devices/${d.id}`, { method: "DELETE" });
        this.loadDevices();
      });
      tr.append(el("td", "", `${d.name}${d.current ? " ★" : ""}`), el("td", "", d.created.replace("T", " ")),
        el("td", "", d.last_seen.replace("T", " ")), el("td"));
      tr.lastChild.append(b);
      table.append(tr);
    }
    this.devices.replaceChildren(table);
  },

  async loadSettings() {
    const { categories, settings } = await call("/v1/aurora/settings");
    const code = lang.slice(0, 2);
    this.box.replaceChildren();
    this.nav.replaceChildren();
    this.original = {};
    this.names = {};
    let lastCat = null;
    // one section per category, in the declared order: the schema grows in any order (a category could repeat)
    const order = Object.keys(categories);
    const rank = (c) => (order.indexOf(c) < 0 ? order.length : order.indexOf(c));
    settings.sort((a, b) => rank(a.category) - rank(b.category));
    // a plugin's settings are in its card (🧩 Plugins): here only the rest, a menu less crowded (owner, 2026-10-04)
    const inCards = [...new Set(settings.filter((s) => s.plugin).map((s) => s.plugin))].sort();
    if (inCards.length) this.box.append(el("p", "muted", t("settings.in_cards", { n: settings.filter((s) => s.plugin).length, list: inCards.join(", ") })));
    for (const s of settings.filter((x) => !x.plugin)) {
      if (s.category !== lastCat) {
        lastCat = s.category;
        const name = categories[s.category]?.[code] || s.category;
        const head = el("h3", "setting-cat", name);
        head.dataset.cat = s.category;
        this.box.append(head);
        this.names[s.category] = name;
      }
      // .env holds booleans as 1/0 or true/false: the select shows 1/0, so compare in that form
      if (s.type === "bool") s.value = TRUE.includes(String(s.value).toLowerCase()) ? "1" : "0";
      this.original[s.key] = s.value;
      const row = el("div", "setting");
      const label = el("div");
      label.append(el("code", "", s.key), info(s[code] || s.en), el("div", "ev-tag",
        `${s.recommended !== undefined && s.recommended !== "" ? "★ " + s.recommended : ""}${s.evidence ? " · " + t("settings.evidence", { e: s.evidence }) : ""}`));
      let input;
      if (s.type === "bool" || s.type === "enum") {
        input = el("select");
        for (const c of s.type === "bool" ? ["0", "1"] : s.choices) {
          const label = t(`choice.${s.key}.${c}`);           // a readable name when there is one
          const o = el("option", "", label.startsWith("choice.") ? c : label);
          o.value = c;
          input.append(o);
        }
      } else {
        input = el("input");
        if (s.type === "int") { input.type = "number"; if (s.min !== undefined) input.min = s.min; if (s.max !== undefined) input.max = s.max; }
        if (s.secret) { input.type = "password"; input.placeholder = t("settings.secret"); }
      }
      input.value = s.secret ? "" : s.value;
      input.dataset.key = s.key;
      input.dataset.secret = s.secret ? "1" : "";
      // the description behind its ⓘ (owner, 2026-10-06): half the page on a phone; the search still finds it
      const help = el("div", "help");
      if (s.services?.length) help.append(el("div", "", `⟳ ${s.services.join(", ")}`));
      row.append(label, input, help);
      row.dataset.cat = s.category;
      row.dataset.text = `${s.key} ${s[code] || s.en}`.toLowerCase();
      this.box.append(row);
    }
    this.menu();
    this.applyFilter();
  },

  // 🗂️ three levels (owner, 2026-10-06: on the phone the chips of 29 categories took half the screen): a button opens
  // the areas, an area its categories, a category shows only its settings; the search stays in sight
  menu() {
    const btn = el("button", "settings-menu-btn");
    btn.type = "button";
    const panel = el("div", "settings-menu hidden");
    const label = () => { btn.textContent = `🗂️ ${this.cat ? this.names[this.cat] : t("settings.all")} ▾`; };
    const pick = (cat) => { this.cat = cat; this.filter.value = ""; label(); panel.classList.add("hidden"); this.applyFilter(); };
    btn.addEventListener("click", () => panel.classList.toggle("hidden"));
    const all = el("button", "settings-menu-all", t("settings.all"));
    all.type = "button";
    all.addEventListener("click", () => pick(""));
    panel.append(all);
    const present = new Set(Object.keys(this.names));
    const placed = new Set();
    for (const [area, cats] of AREAS) {
      const here = (area === "system" ? [...cats, ...[...present].filter((c) => !AREAS.some(([, l]) => l.includes(c)))] : cats)
        .filter((c) => present.has(c) && !placed.has(c));
      if (!here.length) continue;
      here.forEach((c) => placed.add(c));
      const d = el("details", "settings-area");
      d.append(el("summary", "", `${t(`settings.area.${area}`)} · ${here.length}`));
      for (const c of here) {
        const b = el("button", "cat-chip", `${this.names[c]} (${this.box.querySelectorAll(`.setting[data-cat="${c}"]`).length})`);
        b.type = "button";
        b.addEventListener("click", () => pick(c));
        d.append(b);
      }
      panel.append(d);
    }
    label();
    this.nav.replaceChildren(btn, panel);
  },

  applyFilter() {
    const q = this.filter.value.trim().toLowerCase();
    const shown = new Set();
    this.box.querySelectorAll(".setting").forEach((r) => {
      const hit = (!q || r.dataset.text.includes(q)) && (q || !this.cat || r.dataset.cat === this.cat);
      r.classList.toggle("hidden", !hit);
      if (hit) shown.add(r.dataset.cat);
    });
    this.box.querySelectorAll(".setting-cat").forEach((h) => h.classList.toggle("hidden", !shown.has(h.dataset.cat)));
  },
};

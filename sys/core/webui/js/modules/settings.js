// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Registered devices and every .env value, with its explanation, editable.
import { call } from "../api.js";
import { el } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { restartPrompt } from "../restart.js";

const TRUE = ["1", "true", "yes", "on"];

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
      <div class="settings-actions"><button class="save" data-i18n="settings.save"></button><span class="result muted"></span></div>`;
    apply(root);
    this.devices = root.querySelector(".devices");
    this.box = root.querySelector(".settings");
    this.nav = root.querySelector(".settings-nav");
    this.filter = root.querySelector(".settings-filter");
    this.filter.placeholder = t("settings.filter");
    this.filter.addEventListener("input", () => this.applyFilter());
    this.original = {};
    const out = root.querySelector(".result");
    root.querySelector(".save").addEventListener("click", async () => {
      const changes = {};
      this.box.querySelectorAll("[data-key]").forEach((i) => {
        if (i.dataset.secret ? i.value !== "" : i.value !== this.original[i.dataset.key]) changes[i.dataset.key] = i.value;
      });
      if (!Object.keys(changes).length) { out.textContent = t("settings.none"); return; }
      try {
        const r = await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify(changes) });
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
    let lastCat = null;
    for (const s of settings) {
      if (s.category !== lastCat) {
        lastCat = s.category;
        const name = categories[s.category]?.[code] || s.category;
        const head = el("h3", "setting-cat", name);
        head.dataset.cat = s.category;
        this.box.append(head);
        const chip = el("button", "cat-chip", name);
        chip.type = "button";
        chip.addEventListener("click", () => { this.filter.value = ""; this.applyFilter(); head.scrollIntoView({ behavior: "smooth" }); });
        this.nav.append(chip);
      }
      // .env holds booleans as 1/0 or true/false: the select shows 1/0, so compare in that form
      if (s.type === "bool") s.value = TRUE.includes(String(s.value).toLowerCase()) ? "1" : "0";
      this.original[s.key] = s.value;
      const row = el("div", "setting");
      const label = el("div");
      label.append(el("code", "", s.key), el("div", "ev-tag",
        `${s.recommended !== undefined && s.recommended !== "" ? "★ " + s.recommended : ""}${s.evidence ? " · " + t("settings.evidence", { e: s.evidence }) : ""}`));
      let input;
      if (s.type === "bool" || s.type === "enum") {
        input = el("select");
        for (const c of s.type === "bool" ? ["0", "1"] : s.choices) input.append(el("option", "", c));
      } else {
        input = el("input");
        if (s.type === "int") { input.type = "number"; if (s.min !== undefined) input.min = s.min; if (s.max !== undefined) input.max = s.max; }
        if (s.secret) { input.type = "password"; input.placeholder = t("settings.secret"); }
      }
      input.value = s.secret ? "" : s.value;
      input.dataset.key = s.key;
      input.dataset.secret = s.secret ? "1" : "";
      const help = el("div", "help", s[code] || s.en);
      if (s.services?.length) help.append(el("div", "", `⟳ ${s.services.join(", ")}`));
      row.append(label, input, help);
      row.dataset.cat = s.category;
      row.dataset.text = `${s.key} ${s[code] || s.en}`.toLowerCase();
      this.box.append(row);
    }
    this.applyFilter();
  },

  applyFilter() {
    const q = this.filter.value.trim().toLowerCase();
    const shown = new Set();
    this.box.querySelectorAll(".setting").forEach((r) => {
      const hit = !q || r.dataset.text.includes(q);
      r.classList.toggle("hidden", !hit);
      if (hit) shown.add(r.dataset.cat);
    });
    this.box.querySelectorAll(".setting-cat").forEach((h) => h.classList.toggle("hidden", !shown.has(h.dataset.cat)));
  },
};

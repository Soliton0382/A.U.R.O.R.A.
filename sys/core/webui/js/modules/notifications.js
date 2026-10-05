// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Notifications: push on this device on/off, and which events notify on each channel (push, WebUI),
// with presets (suggested, all, none) or a custom choice, event by event.
import { call } from "../api.js";
import { el } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { pushOff, pushOn, pushState } from "../push.js";
import { bus } from "../bus.js";

const CHANNELS = ["push", "webui"];

export default {
  id: "notifications",
  icon: "🔔",
  title: "nav.notifications",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="notif.title"></h2>
      <h3 class="setting-cat" data-i18n="notif.history"></h3><p class="muted notif-delivery"></p><div class="notif-history"></div>
      <p class="muted" data-i18n="notif.hint"></p>
      <h3 class="setting-cat" data-i18n="notif.device"></h3>
      <div class="notif-device"></div>
      <h3 class="setting-cat" data-i18n="notif.which"></h3>
      <div class="notif-grid"></div>
      <div class="settings-actions"><button class="save" data-i18n="settings.save"></button> <span class="result muted"></span></div>`;
    apply(root);
    this.device = root.querySelector(".notif-device");
    this.history = root.querySelector(".notif-history");
    this.delivery = root.querySelector(".notif-delivery");
    this.grid = root.querySelector(".notif-grid");
    this.out = root.querySelector(".result");
    root.querySelector(".save").addEventListener("click", () => this.save());
  },

  async enter() { await Promise.all([this.showDevice(), this.showGrid(), this.showHistory(), this.showDelivery()]); },

  // how many pushes the devices said they received (M101): measured, not assumed
  async showDelivery() {
    let d = null;
    try { d = await call("/v1/aurora/push/delivery?days=7"); } catch { /* an API before the measure */ }
    this.delivery.textContent = d && d.accepted
      ? t("notif.delivery").replace("{c}", d.confirmed).replace("{a}", d.accepted).replace("{p}", Math.round(100 * d.rate))
      : "";
  },

  // every notification Aurora made (owner, 2026-10-05): newest first, a click opens its page
  async showHistory() {
    let items = [];
    try { items = await call("/v1/aurora/notifications/history?n=200"); } catch { /* an API before the history */ }
    this.history.replaceChildren(...(items.length ? items.map((n) => {
      const row = el("button", "ev notif-row");
      row.type = "button";
      const when = new Date(n.at * 1000);
      row.append(el("span", "muted", `${when.toLocaleDateString([], { day: "2-digit", month: "2-digit" })} ${when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`),
        el("strong", "", n.title), el("span", "", n.body || ""),
        el("span", "muted", n.channels.includes("push") ? "📱" : "🖥️"));
      if (n.view) row.addEventListener("click", () => bus.emit("show", { id: n.view }));
      return row;
    }) : [el("p", "muted", t("notif.history_none"))]));
  },

  async showDevice() {
    const st = await pushState();
    const box = this.device;
    box.replaceChildren(el("div", "ev", t(`notif.state.${st}`)));
    if (st === "unsupported" || st === "denied") return;
    const b = el("button", "", t(st === "on" ? "notif.off" : "notif.on"));
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { st === "on" ? await pushOff() : await pushOn(); } catch (e) { box.append(el("div", "ev error", e.message)); }
      bus.emit("push", {});
      await this.showDevice();
    });
    box.append(b);
  },

  async showGrid() {
    const n = await call("/v1/aurora/notifications");
    const code = lang.slice(0, 2);
    this.grid.replaceChildren();
    this.boxes = {};
    for (const ch of CHANNELS) {
      const col = el("div", "notif-col");
      col.append(el("h4", "", t(`notif.ch.${ch}`)));
      const preset = el("select");
      for (const p of ["suggested", "all", "none", "custom"]) {
        const o = el("option", "", t(`notif.preset.${p}`));
        o.value = p;
        preset.append(o);
      }
      col.append(preset);
      const checks = {};
      for (const k of n.kinds) {
        const row = el("label", "notif-row");
        const c = el("input");
        c.type = "checkbox";
        c.checked = n.prefs[ch].includes(k.id);
        c.addEventListener("change", () => { preset.value = this.presetOf(n.presets, checks); });
        checks[k.id] = c;
        row.append(c, el("span", "", k[code] || k.label));
        col.append(row);
      }
      preset.value = this.presetOf(n.presets, checks);
      preset.addEventListener("change", () => {
        if (preset.value === "custom") return;
        for (const [id, c] of Object.entries(checks)) c.checked = n.presets[preset.value].includes(id);
      });
      this.boxes[ch] = checks;
      this.grid.append(col);
    }
  },

  presetOf(presets, checks) {
    const on = Object.entries(checks).filter(([, c]) => c.checked).map(([id]) => id).sort().join(",");
    return Object.keys(presets).find((p) => [...presets[p]].sort().join(",") === on) || "custom";
  },

  async save() {
    const body = {};
    for (const ch of CHANNELS) body[ch] = Object.entries(this.boxes[ch]).filter(([, c]) => c.checked).map(([id]) => id);
    try {
      await call("/v1/aurora/notifications", { method: "PUT", body: JSON.stringify(body) });
      this.out.textContent = t("notif.saved");
    } catch (e) { this.out.textContent = t("ev.error", { m: e.message }); }
  },
};

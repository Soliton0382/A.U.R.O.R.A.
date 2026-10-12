// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🏠 Casa: the devices of Home Assistant (owner, 2026-10-12: «una pagina dedicata nel menù per home assistant quando
// risulta attivo… si possono gestire i device che espone»). Each device with its entities and their state, the simple
// commands (a switch, a button, a number), a camera's picture and what Aurora sees in it, the agents that watch it.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";

const TOGGLE = new Set(["switch", "light", "fan", "input_boolean"]);
const ON = new Set(["on", "open", "playing", "unlocked"]);

export default {
  id: "home",
  icon: "🏠",
  title: "nav.home",
  plugin: "homeassistant",            // in the menu only when that plugin is on

  mount(root, ctx) {
    this.ctx = ctx;
    root.classList.add("page");
    useCss("/static/css/home.css");
    root.innerHTML = `<h2 data-i18n="home.title"></h2><p class="muted" data-i18n="home.hint"></p>
      <div class="appr-actions"><button class="home-reload" data-i18n="home.reload"></button>
        <span class="muted home-out"></span></div><div class="home-devices"></div>`;
    apply(root);
    this.list = root.querySelector(".home-devices");
    this.out = root.querySelector(".home-out");
    root.querySelector(".home-reload").addEventListener("click", () => this.enter());
  },

  async enter() {
    this.out.textContent = t("home.loading");
    let r;
    try { r = await call("/v1/aurora/home/devices"); } catch (e) { this.out.textContent = t("ev.error", { m: e.message }); return; }
    this.allowed = r.allowed || {};
    this.out.textContent = t(`home.level.${r.level}`);
    this.list.replaceChildren(...(r.devices.length ? r.devices.map((d) => this.device(d)) : [el("p", "muted", t("home.none"))]));
  },

  device(d) {
    const card = el("section", "home-card");
    const head = el("div", "home-head");
    head.append(el("h3", "", d.name), el("span", "muted", [d.manufacturer, d.model].filter(Boolean).join(" · ")));
    card.append(head);
    const cams = d.entities.filter((e) => e.domain === "camera");
    for (const c of cams) card.append(this.camera(c));
    const rows = el("div", "home-entities");
    for (const e of d.entities.filter((x) => x.domain !== "camera")) rows.append(this.entity(e));
    card.append(rows);
    card.append(this.agents(d));
    return card;
  },

  entity(e) {
    const row = el("div", "home-entity");
    const state = el("span", "home-state", `${e.state}${e.unit ? ` ${e.unit}` : ""}`);
    row.append(el("span", "home-name", e.name || e.entity_id), state);
    const can = this.allowed[e.domain] || [];
    const run = async (service, data, btn) => {
      btn.disabled = true;
      try {
        await call("/v1/aurora/home/service", { method: "POST", body: JSON.stringify({ entity_id: e.entity_id, service, data }) });
        setTimeout(() => this.enter(), 1200);                    // the new state, once the device has answered
      } catch (err) { state.textContent = t("ev.error", { m: err.message }); btn.disabled = false; }
    };
    if (TOGGLE.has(e.domain) && can.includes("toggle")) {
      const b = el("button", ON.has(e.state) ? "approve" : "", ON.has(e.state) ? t("home.off") : t("home.on"));
      b.addEventListener("click", () => run(ON.has(e.state) ? "turn_off" : "turn_on", {}, b));
      row.append(b);
    } else if (e.domain === "button" && can.includes("press")) {
      const b = el("button", "", t("home.press"));
      b.addEventListener("click", () => run("press", {}, b));
      row.append(b);
    } else if (e.domain === "number" && can.includes("set_value")) {
      const box = el("input");
      box.type = "number";
      box.value = e.state;
      box.className = "home-number";
      const b = el("button", "", t("home.set"));
      b.addEventListener("click", () => run("set_value", { value: box.value }, b));
      row.append(box, b);
    }
    return row;
  },

  camera(c) {
    const wrap = el("div", "home-camera");
    const img = el("img", "home-shot");
    img.alt = c.name || c.entity_id;
    const words = el("p", "muted home-words");
    const shot = el("button", "", t("home.shot"));
    const look = el("button", "", t("home.look"));
    shot.addEventListener("click", () => { img.src = `/v1/aurora/home/camera/${encodeURIComponent(c.entity_id)}?t=${Date.now()}`; });
    look.addEventListener("click", async () => {
      look.disabled = true;
      words.textContent = t("home.looking");
      try {
        const r = await call("/v1/aurora/home/look", { method: "POST", body: JSON.stringify({ entity_id: c.entity_id }) });
        words.textContent = r.text;
      } catch (e) { words.textContent = t("ev.error", { m: e.message }); }
      look.disabled = false;
    });
    const bar = el("div", "appr-actions");
    bar.append(el("span", "home-name", c.name || c.entity_id), shot, look);
    wrap.append(bar, img, words);
    return wrap;
  },

  agents(d) {
    const box = el("div", "home-agents");
    box.append(el("h4", "", t("home.agents")));
    for (const a of d.agents) box.append(el("div", "home-agent", `${a.enabled ? "🟢" : "⏸️"} ${a.title}`));
    for (const p of d.proposals) box.append(el("div", "home-agent muted", `💡 ${p.title} — ${t("home.proposed")}`));
    if (!d.agents.length && !d.proposals.length) box.append(el("p", "muted", t("home.no_agents")));
    const bar = el("div", "appr-actions");
    const again = el("button", "", t("home.propose"));
    const open = el("button", "", t("home.open_routines"));
    const out = el("span", "muted");
    again.addEventListener("click", async () => {
      again.disabled = true;
      out.textContent = t("home.thinking");
      try {
        const r = await call(`/v1/aurora/home/agents/${encodeURIComponent(d.id)}`, { method: "POST" });
        out.textContent = t("home.proposals", { n: r.proposed });
        if (r.proposed) this.enter();
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
      again.disabled = false;
    });
    open.addEventListener("click", () => this.ctx?.show("routines"));
    bar.append(again, open, out);
    box.append(bar);
    return box;
  },
};

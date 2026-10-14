// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ☀️ Oggi, the first page of the Essenziale and Misto styles (ROADMAP 107): a box to ask, and a few big tiles — the
// day's agenda, the house's switches, what waits for you, last night's dream, and whether all is well. Each tile asks
// its own API and stays out when it has nothing (no calendar, no house, a user without the machine's health).
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";

const SWITCHES = new Set(["light", "switch", "fan", "input_boolean"]);

export default {
  id: "today",
  icon: "☀️",
  title: "nav.today",

  mount(root, ctx) {
    this.ctx = ctx;
    root.classList.add("page", "today");
    root.innerHTML = `<p class="muted td-date"></p><h2 class="td-hello"></h2>
      <form class="td-ask"><label class="sr-only" for="td-q" data-i18n="today.ask"></label>
      <input id="td-q" autocomplete="off"><button class="approve" data-i18n="today.ask_go"></button></form>
      <div class="td-tiles"></div>`;
    apply(root);
    const q = root.querySelector("#td-q");
    q.placeholder = t("today.ask");
    root.querySelector(".td-ask").addEventListener("submit", (e) => {
      e.preventDefault();
      if (q.value.trim()) { bus.emit("ask", { text: q.value.trim() }); q.value = ""; }
    });
    this.root = root;
    this.tiles = root.querySelector(".td-tiles");
  },

  async enter() {
    const now = new Date();
    this.root.querySelector(".td-date").textContent = now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
    const h = now.getHours();
    this.root.querySelector(".td-hello").textContent = t(h < 13 ? "today.morning" : h < 18 ? "today.afternoon" : "today.evening");
    const made = await Promise.all([this.agenda(), this.house(), this.waiting(), this.dream(), this.health()].map((p) => p.catch(() => null)));
    this.tiles.replaceChildren(...made.filter(Boolean));
  },

  tile(title, ...body) {
    const s = el("section", "td-tile");
    s.append(el("h3", "", title), ...body);
    return s;
  },

  link(label, view) {
    const b = el("button", "link", label);
    b.type = "button";
    b.addEventListener("click", () => this.ctx.show(view));
    return b;
  },

  async agenda() {
    const day = new Date().toISOString().slice(0, 10);
    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
    const c = await call(`/v1/aurora/calendar?start=${day}&end=${tomorrow}`);
    const items = [...c.events, ...(c.external || [])].sort((a, b) => String(a.start_iso || a.start).localeCompare(String(b.start_iso || b.start)));
    const list = el("div", "td-list");
    if (!items.length) list.append(el("p", "muted", t("today.free")));
    for (const e of items.slice(0, 5)) {
      const when = e.all_day ? t("today.all_day") : new Date(e.start_iso || e.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const row = el("div", "td-row");
      row.append(el("span", "muted", when), el("span", "", e.title || ""));
      list.append(row);
    }
    return this.tile(t("today.agenda"), list, this.link(t("today.open_calendar"), "calendar"));
  },

  async house() {
    const d = await call("/v1/aurora/home/devices");
    const ents = d.devices.flatMap((x) => x.entities).filter((e) => SWITCHES.has(e.domain) && ["on", "off"].includes(e.state)).slice(0, 4);
    if (!ents.length) return null;
    const grid = el("div", "td-switches");
    for (const e of ents) {
      const b = el("button", `td-switch${e.state === "on" ? " on" : ""}`);
      b.type = "button";
      b.setAttribute("aria-pressed", String(e.state === "on"));
      const draw = () => b.replaceChildren(el("span", "", e.name), el("small", "", t(e.state === "on" ? "today.on" : "today.off")));
      draw();
      b.addEventListener("click", async () => {
        b.disabled = true;
        try {
          await call("/v1/aurora/home/service", { method: "POST", body: JSON.stringify({ entity_id: e.entity_id, service: "toggle" }) });
          e.state = e.state === "on" ? "off" : "on";
          b.classList.toggle("on", e.state === "on");
          b.setAttribute("aria-pressed", String(e.state === "on"));
          draw();
        } catch (err) { alert(err.message); }
        b.disabled = false;
      });
      grid.append(b);
    }
    return this.tile(t("today.house"), grid, this.link(t("today.open_house"), "home"));
  },

  async waiting() {
    const list = await call("/v1/aurora/approvals?status=pending");
    if (!list.length) return null;
    return this.tile(t("today.waiting"), el("p", "", t("today.waiting_n", { n: list.length })), this.link(t("today.decide"), "approvals"));
  },

  async dream() {
    const r = await call("/v1/aurora/dreams?n=1");
    const d = r.dreams[0];
    if (!d) return null;
    const s = el("section", "td-tile td-dream");
    if (d.image) { const img = el("img"); img.src = d.image; img.alt = d.image_prompt || t("dreams.painting"); img.loading = "lazy"; s.append(img); }
    const first = (d.text.match(/^.{20,160}?[.!?…](\s|$)/) || [d.text.slice(0, 140)])[0];
    s.append(el("h3", "", t("today.dream")), el("p", "", first.trim()), this.link(t("today.all_dreams"), "dreams"));
    return s;
  },

  async health() {
    const h = await call("/v1/aurora/health");
    const bad = (h.items || []).filter((x) => x.level !== "ok");
    if (!bad.length) return this.tile(t("today.all_well"), el("p", "muted", t("today.all_well_text")));
    const list = el("ul", "td-bad");
    list.append(...bad.slice(0, 4).map((x) => el("li", x.level === "error" ? "error" : "", `${x.name}: ${x.text}`)));
    return this.tile(t("today.attention"), list, this.link(t("today.open_status"), "status"));
  },
};

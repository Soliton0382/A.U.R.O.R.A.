// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ☀️ Oggi, the first page of every style (ROADMAP 107; Completo too since 17 Oct): a box to ask, and a few big tiles — the
// day's agenda, the house's switches, what waits for you, last night's dream, and whether all is well. Each tile asks
// its own API and stays out when it has nothing (no calendar, no house, a user without the machine's health). The
// tiles are each person's to show, hide and move (today_edit.js; owner, 19 Oct: «un insieme di widget che uno può
// personalizzare»), with what to photograph tonight when astro is on and the day's numbers.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { setTilePrefs, tilePrefs } from "../style.js";
import astro from "./astro.js";
import { editTiles, shown } from "./today_edit.js";
import { pageTile } from "./today_pages.js";

const SWITCHES = new Set(["light", "switch", "fan", "input_boolean"]);
// the headlines' speed, pixels a second: three to try (owner, 2026-10-20: «va piano… un pulsante… tipo 3 velocità»),
// the choice kept on this device
const NEWS_SPEEDS = [["🐢", 300], ["🚶", 600], ["🐇", 1000]];   // owner, 20 Oct: «andrebbero aumentate»
const NEWS_KEY = "aurora.news_speed";
const newsSpeed = () => { try { return Math.min(2, Math.max(0, Number(localStorage.getItem(NEWS_KEY) ?? 1))); } catch { return 1; } };
// every tile in its first order; each is a method below of the same name ("news" is the headlines' strip); the pages
// added are "page:<id>" (today_pages.js)
export const TILES = ["news", "agenda", "sky", "research", "house", "waiting", "publications", "stats", "dream", "health"];

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
      <div class="td-news" hidden></div><div class="td-tiles"></div>
      <p class="td-foot"><button type="button" class="link td-edit-go"></button></p>`;
    apply(root);
    const q = root.querySelector("#td-q");
    q.placeholder = t("today.ask");
    root.querySelector(".td-ask").addEventListener("submit", (e) => {
      e.preventDefault();
      if (q.value.trim()) { bus.emit("ask", { text: q.value.trim() }); q.value = ""; }
    });
    this.root = root;
    this.tiles = root.querySelector(".td-tiles");
    const go = root.querySelector(".td-edit-go");
    go.textContent = `✏️ ${t("today.edit")}`;
    go.addEventListener("click", () => {
      go.hidden = true;
      editTiles(this.tiles, TILES, tilePrefs(), (v) => {
        if (v) setTilePrefs(v);
        go.hidden = false;
        this.enter();
      });
    });
  },

  async enter() {
    const now = new Date();
    this.root.querySelector(".td-date").textContent = now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
    const h = now.getHours();
    const hello = this.root.querySelector(".td-hello");
    const word = t(h < 13 ? "today.morning" : h < 18 ? "today.afternoon" : "today.evening").replace(/\.$/, "");
    hello.textContent = `${word}.`;
    // the person's name and a sign of the day: the weather at home, else the hour (owner, 26 Oct)
    call("/v1/aurora/today/hello").then((g) => {
      hello.textContent = `${word}${g.person ? `, ${g.person}` : ""} ${g.emoji}`;
      hello.title = g.temperature_c != null ? `${Math.round(g.temperature_c)} °C` : "";
    }).catch(() => {});
    const ids = shown(TILES, tilePrefs());
    if (ids.includes("news")) this.news().catch(() => {});  // at once, not after the slowest tile (owner, 17 Oct)
    else this.root.querySelector(".td-news").hidden = true;
    // a hidden place a tile, in the person's order: each tile takes its own as soon as it answers, the slow ones
    // (tonight's sky) never holding the others back
    const run = (this.run || 0) + 1;
    this.run = run;
    const slots = ids.filter((id) => id !== "news").map((id) => { const s = el("div", "td-slot"); s.dataset.tile = id; return s; });
    this.tiles.replaceChildren(...slots);
    await Promise.all(slots.map(async (slot) => {
      const id = slot.dataset.tile;
      const made = await (id.startsWith("page:") ? pageTile(id.slice(5), this.ctx) : this[id]()).catch(() => null);
      if (this.run !== run) return;                       // the page was drawn again meanwhile
      if (made) slot.replaceWith(made); else slot.remove();
    }));
  },

  // what to photograph tonight, when astro is on (owner, 19 Oct: «nella schermata oggi magari il suggerimento su cosa
  // fotografare»): the three best objects with usable hours, else the best if the sky opens; the full list in Astro
  async sky() {
    const plugins = await call("/v1/aurora/plugins");
    if (!plugins.some((p) => p.name === "astro" && p.enabled && p.available)) return null;
    const d = await call("/v1/aurora/astro/sky?limit=10");
    const all = d.targets || [];
    if (d.error || !all.length) return null;
    const clear = all.filter((r) => !r.if_clear);
    const pick = (clear.length ? clear : all).slice(0, 3);
    const list = el("div", "td-sky");
    for (const r of pick) {
      const row = el("div", "td-sky-row");
      if (r.thumb) {
        const im = el("img", "td-sky-pic");
        im.src = `/v1/aurora/astro/sky/thumb?object=${encodeURIComponent(r.name)}`;
        im.alt = "";
        im.loading = "lazy";
        row.append(im);
      } else row.append(el("span", "td-sky-pic", "🔭"));
      const names = (r.common || []).slice(0, 1).join("");
      const what = el("div", "");
      what.append(el("strong", "", `${r.name}${names ? ` · ${names}` : ""}`),
        el("small", "muted", `${r.if_clear ? "☁️ " : ""}${r.hours} h${r.from ? ` · ${r.from}–${r.to}` : ""} · ${r.type || ""}`));
      row.append(what);
      list.append(row);
    }
    const s = this.tile(`🌌 ${t("today.sky")}`, list);
    if (!clear.length) s.append(el("p", "muted", t("today.sky_clouds")));
    const open = el("button", "link", t("today.sky_open"));
    open.type = "button";
    open.addEventListener("click", async () => { await this.ctx.show("astro"); astro.tab("sky"); });
    s.append(open);
    return s;
  },

  // 📚 the owner's works and how much they are read (the publications plugin; owner, 26 Oct): the totals, the change
  // since yesterday, the three newest; out when the plugin is off or has no ORCID
  async publications() {
    const { items } = await call("/v1/aurora/today/publications");
    if (!items.length) return null;
    const sum = (k, f = (w) => w[k]) => items.reduce((n, w) => n + (f(w) || 0), 0);
    const plus = (n) => (n > 0 ? ` (+${n})` : "");
    const grid = el("div", "td-stats");
    for (const [icon, key, k] of [["👁️", "today.pub_views", "views"], ["⬇️", "today.pub_downloads", "downloads"]]) {
      const b = el("div", "td-stat");
      b.append(el("strong", "", `${icon} ${sum(k).toLocaleString()}${plus(sum(k, (w) => (w.day || {})[k]))}`),
        el("small", "muted", t(key)));
      grid.append(b);
    }
    const list = el("div", "td-list");
    for (const w of items.slice(0, 3)) {
      const a = el("a", "", w.title);
      a.href = w.url;
      a.target = "_blank";
      a.rel = "noopener";
      const row = el("div", "");
      row.append(a, el("small", "muted", ` · 👁️ ${w.views}${plus((w.day || {}).views)} · ⬇️ ${w.downloads}${plus((w.day || {}).downloads)}`));
      list.append(row);
    }
    const all = el("button", "link", t("today.pub_all"));        // every work, with its full numbers
    all.type = "button";
    all.addEventListener("click", async () => {
      await this.ctx.show("projects");
      (await import("./projects.js")).default.tab("papers");
    });
    return this.tile(`📚 ${t("today.publications")}`, grid, list, all);
  },

  // the day's numbers (Utilizzo): questions, the agent's runs, the cloud's calls, the tools
  async stats() {
    const r = await call("/v1/aurora/usage?days=1");
    const s = r.totals;
    if (!s) return null;
    const grid = el("div", "td-stats");
    for (const [icon, key, n] of [["💬", "usage.questions", s.questions], ["🤖", "usage.agent", s.agent_runs],
      ["☁️", "usage.cloud", s.cloud_calls], ["🧰", "usage.tools", s.tool_calls]]) {
      const b = el("div", "td-stat");
      b.append(el("strong", "", `${icon} ${Number(n || 0).toLocaleString()}`), el("small", "muted", t(key)));
      grid.append(b);
    }
    return this.tile(t("today.stats"), grid, this.link(t("today.open_usage"), "usage"));
  },

  // the day's headlines in a strip that scrolls (owner, 2026-10-16: «in scorrimento… aggiornate ogni 3 ore»);
  // paused under the pointer or a finger, a plain list for who asks the system for less motion
  async news() {
    const d = await call("/v1/aurora/today/news");
    const box = this.root.querySelector(".td-news");
    if (!d.items.length) { box.hidden = true; return; }
    const track = el("div", "td-news-track");
    const items = d.items.map((n) => {
      const a = el("a", "td-news-item", n.title);
      a.href = n.link;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.title = `${n.source} · ${n.when}\n${n.summary}`;
      a.prepend(el("small", "muted", `${n.source} · `));
      return a;
    });
    track.append(...items, ...items.map((x) => { const c = x.cloneNode(true); c.setAttribute("aria-hidden", "true"); c.tabIndex = -1; return c; }));

    const view = el("div", "td-news-view");             // the strip ends at the label: the label stays clean
    view.append(track);
    const speed = el("button", "td-news-speed");
    const pace = () => {
      const [icon, base] = NEWS_SPEEDS[newsSpeed()];
      // the speeds are a wide screen's: a phone's strip is a third as wide, the same pixels a second crossed it
      // in half a second (owner, 2026-10-20, the PWA: «ancora illeggibile») — scaled to the strip's own width
      const px = Math.round(base * Math.max(0.35, Math.min(1.3, view.clientWidth / 900)));
      speed.textContent = icon;
      speed.title = t("today.news_speed", { px });
      track.style.setProperty("--td-news-s", `${Math.max(3, track.scrollWidth / 2 / px).toFixed(1)}s`);   // no floor that flattens the fast one
      track.style.animation = "none";                   // started again: the new duration taken on every browser
      void track.offsetWidth;
      track.style.animation = "";
    };
    speed.addEventListener("click", () => {
      speed.blur();
      try { localStorage.setItem(NEWS_KEY, String((newsSpeed() + 1) % NEWS_SPEEDS.length)); } catch { /* not kept */ }
      pace();
    });
    const label = el("span", "td-news-label", "📰 ");
    label.append(el("span", "td-news-word", t("today.news")));
    box.replaceChildren(label, speed, view);
    box.hidden = false;
    // a steady speed whatever the number of headlines (owner, 2026-10-16: 16 in 112 s «sembrano ferme», then «leggermente
    // più veloci», «ancora un pochino»; 17 Oct at 170 px/s «ancora troppo lente»): ~250 px a second
    requestAnimationFrame(pace);
  },

  // the last report of the research routines, with its PDF (owner, 2026-10-16: «le novità della ricerca… in Oggi»)
  async research() {
    const d = await call("/v1/aurora/today/research");
    const r = d.items[0];
    if (!r) return null;
    const first = r.text.split(/\n+/).filter((x) => x.trim()).slice(0, 3).join(" ").slice(0, 320);
    const body = [el("p", "", first + (r.text.length > first.length ? "…" : ""))];
    if (r.pdf) {
      const a = el("a", "link", `📄 ${t("today.research_pdf")}`);
      a.href = r.pdf.url;
      a.target = "_blank";
      body.push(a);
    }
    return this.tile(r.title || t("today.research"), ...body, this.link(t("today.all_reports"), "reports"));
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

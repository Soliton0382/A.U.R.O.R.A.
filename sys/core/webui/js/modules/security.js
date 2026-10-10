// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Firewall incidents: severity, public registry data about the source network, Aurora's report
// with the defensive actions she recommends; the owner closes them. Four tabs (owner, 2026-10-06: "the page loads
// embarrassingly slowly"): each loads its data when first opened — the checks (4.5 s) and the outbound (4.8 s) no
// longer hold the incidents; the closed incidents (most of the 344 KB) only on request. Defence and map:
// security_defence.js; checks and outbound: security_watch.js.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { defence } from "./security_defence.js";
import { watch } from "./security_watch.js";
import { autonomySlot } from "./autonomy_box.js";

const TABS = ["incidents", "defence", "watch", "out"];

const SEV = { high: "bad", medium: "warn", low: "ok" };

// each tab is a page of its own in the menu's security area (owner, 2026-10-08: «sotto menù specifici… così teniamo
// le cose separate e pulite»): the same code, one tab shown, its tab bar hidden
export function page(tab, meta) { const { title } = meta; return {
  ...meta,
  plugin: "security",                 // in the menu only when that plugin is on (social: any platform connected)

  mount(root) {
    this.root = root;
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="sec.title"></h2><p class="muted" data-i18n="sec.hint"></p>
      <div class="prj-tabs">${TABS.map((x, i) => `<button type="button" class="cat-chip${i ? "" : " on"}" data-tab="${x}" data-i18n="sec.tab.${x}"></button>`).join("")}</div>
      <div class="sec-tab" data-tab="incidents">
        <details class="report sec-score-box"><summary data-i18n="sec.score"></summary><div class="sec-score"></div></details>
        <h3 class="setting-cat" data-i18n="sec.open"></h3><div class="open"></div>
        <h3 class="setting-cat"><span data-i18n="sec.closed"></span> <button class="sec-show-closed" data-i18n="sec.show_closed"></button> <button class="sec-archive" hidden></button></h3>
        <div class="closed"></div></div>
      <div class="sec-tab" data-tab="defence" hidden>
        <h3 class="setting-cat" data-i18n="sec.defence"></h3><div class="sec-defence"></div>
        <h3 class="setting-cat" data-i18n="sec.map"></h3><p class="muted" data-i18n="sec.map_hint"></p><div class="sec-map"></div></div>
      <div class="sec-tab" data-tab="watch" hidden>
        <h3 class="setting-cat" data-i18n="sec.watch"></h3><p class="muted sec-watch-hint"></p>
        <div class="appr-actions"><button class="sec-learn" data-i18n="sec.learn"></button><span class="muted sec-learn-out"></span></div>
        <div class="sec-rules"></div><details class="report"><summary data-i18n="sec.traffic"></summary><div class="sec-groups"></div></details></div>
      <div class="sec-tab" data-tab="out" hidden>
        <h3 class="setting-cat" data-i18n="sec.out"></h3><p class="muted" data-i18n="sec.out_hint"></p><div class="sec-out"></div></div>`;
    root.querySelector(".prj-tabs").hidden = true;
    root.querySelectorAll(".sec-tab").forEach((p) => { p.hidden = p.dataset.tab !== tab; });
    root.querySelector("h2").dataset.i18n = title;
    root.querySelector("h2").after(autonomySlot("security"));
    apply(root);
    this.loaded = new Set();
    this.tab = tab;
    root.querySelectorAll(".prj-tabs button").forEach((b) => b.addEventListener("click", () => {
      root.querySelectorAll(".prj-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      root.querySelectorAll(".sec-tab").forEach((p) => { p.hidden = p.dataset.tab !== b.dataset.tab; });
      this.tab = b.dataset.tab;
      this.show(this.tab);
    }));
    const showClosed = root.querySelector(".sec-show-closed");
    showClosed.addEventListener("click", () => { showClosed.hidden = true; this.loadClosed(); });
    this.open = root.querySelector(".open");
    this.defence = root.querySelector(".sec-defence");
    this.map = root.querySelector(".sec-map");
    this.host = root.querySelector(".sec-host");
    this.names = {};
    this.outbound = root.querySelector(".sec-out");
    this.closed = root.querySelector(".closed");
    this.archive = root.querySelector(".sec-archive");
    this.rules = root.querySelector(".sec-rules");
    this.groups = root.querySelector(".sec-groups");
    this.watchHint = root.querySelector(".sec-watch-hint");
    const learn = root.querySelector(".sec-learn"), out = root.querySelector(".sec-learn-out");
    learn.addEventListener("click", async () => {                // the documentation and the traffic: proposals
      learn.disabled = true;
      out.textContent = t("sec.learning");
      try { const r = await call("/v1/aurora/security/learn", { method: "POST" }); out.textContent = t("sec.learned", { n: r.proposed, g: r.groups }); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); }
      learn.disabled = false;
      this.loadProfile();
    });
    this.archive.addEventListener("click", async () => {      // tidy the page: archived, still in the reports
      this.archive.disabled = true;
      await call("/v1/aurora/incidents/archive-closed", { method: "POST" }).catch(() => null);
      this.archive.disabled = false;
      this.enter();
    });
  },

  card(i) {
    const c = el("details", "report");
    c.open = i.status === "open";
    const head = el("summary");
    head.append(el("span", `pill ${SEV[i.severity] || "warn"}`, t(`sec.sev.${i.severity}`)),
      el("span", "", ` ${i.kind.startsWith("rule:") ? (i.detail?.title || i.kind) : t(`sec.kind.${i.kind}`)} · ${this.who(i.source)}${i.internal ? " (" + t("sec.internal") + ")" : ""} · `
        + `${i.count} ${t("sec.events")}${i.repeats ? ` · ${t("sec.repeats", { n: i.repeats })}` : ""}${i.known ? " · 🏠" : ""} · ${clock(i.received)}`));
    c.append(head);
    if (i.intel) for (const [k, v] of Object.entries(i.intel)) c.append(el("div", "muted", `${k}: ${v}`));
    c.append(i.report ? renderMarkdown(i.report) : el("p", "muted", t("sec.pending")));
    if (i.samples?.length) {
      const d = el("details");
      d.append(el("summary", "", t("sec.samples")), el("pre", "", i.samples.join("\n")));
      c.append(d);
    }
    if (i.detail?.action) c.append(el("p", "", `💡 ${i.detail.action}`));
    if (i.defence) c.append(el("p", i.defence === "blocked" ? "ok" : "muted", i.defence === "blocked"
      ? `🛡️ ${t("sec.def_blocked", { until: new Date(i.blocked_until * 1000).toLocaleString() })}` : `🛡️ ${t("sec.def_not")}: ${i.defence}`));
    if (this.blocked.has(i.source)) c.append(el("p", "ok", `🛡️ ${t("sec.already_blocked")}`));
    // the owner's click is the consent; never offered for an address at home (the owner's devices, C174)
    else if (this.fwApi && !i.internal && /^\d+\.\d+\.\d+\.\d+$/.test(i.source)) {
      // a CDN's or a cloud's shared address (C190): the owner may block it, warned first
      if (i.shared) c.append(el("p", "warn", `⚠️ ${t("sec.shared", { who: i.shared })}`));
      const block = el("button", "danger", `⛔ ${t("sec.block", { ip: i.source })}`);
      block.addEventListener("click", async () => {
        if (!confirm(t("sec.block_q", { ip: i.source, group: this.group }) + (i.shared ? `\n\n⚠️ ${t("sec.shared", { who: i.shared })}` : ""))) return;
        try {
          await call("/v1/aurora/security/block", { method: "POST", body: JSON.stringify({ ip: i.source, reason: `${i.kind} ${i.id}`, incident: i.id }) });
          this.blocked.add(i.source);
          const undo = el("button", "", `↩️ ${t("sec.undo", { ip: i.source })}`);    // changed my mind: one click back
          undo.addEventListener("click", async () => {
            try { await call("/v1/aurora/security/block", { method: "POST", body: JSON.stringify({ ip: i.source, unblock: true }) });
              undo.replaceWith(el("span", "ok", t("sec.undone", { ip: i.source }))); this.loadDefence(); }
            catch (e) { alert(e.message); }
          });
          block.replaceWith(undo);
          c.querySelector(".sec-close")?.remove();            // closed with the block: it moves to the closed ones
          c.append(el("p", "ok", t("sec.blocked_closed")));
          this.loadDefence();
        }
        catch (e) { alert(e.message); }
      });
      c.append(block);
    }
    for (const ip of [i.internal ? null : i.source, i.destination]) {   // 🌍 the visual traceroute (security_trace.js)
      if (!ip || !/^[0-9a-f.:]+$/i.test(ip) || /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.)/.test(ip)) continue;
      const geo = el("button", "", t("sec.geolocate", { ip }));
      geo.addEventListener("click", () => { bus.emit("trace", { ip }); bus.emit("show", { id: "sectrace" }); });
      c.append(geo);
    }
    if (i.destination) {                              // a device at home reaching a threat feed's address (M161)
      c.append(el("p", "warn", t("sec.dest", { ip: i.destination, name: i.destination_name || "—",
        who: i.destination_provider || "—", feed: i.destination_feed || "—",
        lists: (i.destination_lists || []).map((x) => x.list || x.name || "").join(", ") || t("sec.dest_none") })));
    }
    c.append(this.verdict(i));                       // the owner's judgement: the scorecard counts it (roadmap 81)
    if (i.status === "open") {
      const b = el("button", "sec-close", `✔ ${t("sec.close")}`);
      b.addEventListener("click", async () => { await call(`/v1/aurora/incidents/${i.id}/close`, { method: "POST" }); this.enter(); });
      c.append(b);
    }
    return c;
  },

  verdict(i) {
    const row = el("div", "appr-actions");
    row.append(el("span", "muted", t("sec.verdict_q")));
    for (const [v, icon] of [["right", "👍"], ["overrated", "📉"], ["false_alarm", "👎"], ["unsure", "🤔"]]) {
      const b = el("button", i.verdict === v ? "approve" : "", `${icon} ${t(`sec.v.${v}`)}`);
      b.addEventListener("click", async () => {
        await call(`/v1/aurora/incidents/${i.id}/verdict`, { method: "POST", body: JSON.stringify({ verdict: v }) });
        i.verdict = v;
        row.replaceWith(this.verdict(i));
        this.loadScore();
      });
      row.append(b);
    }
    return row;
  },

  async loadScore() {
    const box = this.root.querySelector(".sec-score");
    let s;
    try { s = await call("/v1/aurora/security/scorecard"); } catch { return; }
    const pct = (x) => (x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`);
    box.replaceChildren(el("p", s.ready ? "ok" : "warn", s.ready ? t("sec.ready") : t("sec.not_ready")));
    s.weeks.forEach((w, k) => {
      const p = el("p", "");
      p.textContent = t("sec.week", { k: k === 0 ? t("sec.this_week") : t("sec.last_week"), n: w.incidents, r: w.reviewed,
        share: pct(w.reviewed_share), prec: pct(w.precision), right: w.right, over: w.overrated, fa: w.false_alarm, blind: w.blind_min, loud: w.loud, quiet: w.quiet });
      box.append(p);
      for (const why of w.short) box.append(el("div", "muted", `• ${why}`));
    });
  },

  // "NAS (192.0.2.10)" when the firewall knows the address (sec_netmap, owner 2026-10-06)
  who(ip) { return this.names[ip] ? `${this.names[ip]} (${ip})` : ip; },

  ...defence,
  ...watch,

  // a tab's data, the first time it is shown (and again when the page is entered while it is the open one)
  async show(tab, again = false) {
    if (this.loaded.has(tab) && !again) return;
    this.loaded.add(tab);
    if (tab === "incidents") { await this.loadOpen(); this.loadScore(); }
    if (tab === "defence") { await this.loadDefence(); await this.loadMap(); }   // Aurora's own machine: 🔥 its page
    if (tab === "watch") { this.rules.replaceChildren(el("p", "muted", "…")); await this.loadProfile(); }
    if (tab === "out") { this.outbound.replaceChildren(el("p", "muted", "…")); await this.loadOutbound(); }
  },

  async loadOpen() {
    const open = await call("/v1/aurora/incidents?status=open");
    this.open.replaceChildren(...(open.length ? open.map((i) => this.card(i)) : [el("p", "muted", t("sec.none"))]));
  },

  async loadClosed() {
    const closed = (await call("/v1/aurora/incidents?status=closed")).filter((i) => i.status !== "open");
    this.closed.replaceChildren(...closed.slice(0, 30).map((i) => this.card(i)));
    this.archive.hidden = closed.length === 0;
    this.archive.textContent = t("sec.archive", { n: closed.length });
  },

  async enter() {
    // the names, the firewall's API and the group first (9 + 11 ms): the incidents' cards use them
    const [m, d] = await Promise.all([call("/v1/aurora/security/netmap").catch(() => ({})),
      call("/v1/aurora/security/defence").catch(() => ({}))]);
    this.names = m.names || {};
    this.fwApi = Boolean(m.configured);
    this.blocked = new Set((d.active || []).map((b) => b.ip));
    this.group = d.group;
    this.loaded.clear();
    await this.show(this.tab, true);
  },
}; }

export default page("incidents", { id: "security", icon: "🚨", title: "nav.sec.incidents" });

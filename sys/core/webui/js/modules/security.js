// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Firewall incidents: severity, public registry data about the source network, Aurora's report
// with the defensive actions she recommends; the owner closes them. Four tabs (owner, 2026-10-06: "the page loads
// embarrassingly slowly"): each loads its data when first opened — the checks (4.5 s) and the outbound (4.8 s) no
// longer hold the incidents; the closed incidents (most of the 344 KB) only on request. Defence and map:
// security_defence.js; checks and outbound: security_watch.js.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { defence } from "./security_defence.js";
import { watch } from "./security_watch.js";

const TABS = ["incidents", "defence", "watch", "out"];

const SEV = { high: "bad", medium: "warn", low: "ok" };

export default {
  id: "security",
  icon: "🛡️",
  title: "nav.security",
  plugin: "security",                 // in the menu only when that plugin is on (social: any platform connected)

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="sec.title"></h2><p class="muted" data-i18n="sec.hint"></p>
      <div class="prj-tabs">${TABS.map((x, i) => `<button type="button" class="cat-chip${i ? "" : " on"}" data-tab="${x}" data-i18n="sec.tab.${x}"></button>`).join("")}</div>
      <div class="sec-tab" data-tab="incidents">
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
    apply(root);
    this.loaded = new Set();
    this.tab = "incidents";
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
        + `${i.count} ${t("sec.events")} · ${clock(i.received)}`));
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
    if (this.fwApi && /^\d+\.\d+\.\d+\.\d+$/.test(i.source)) {   // the owner's click is the consent
      const block = el("button", "danger", `⛔ ${t("sec.block", { ip: i.source })}`);
      block.addEventListener("click", async () => {
        if (!confirm(t("sec.block_q", { ip: i.source, group: this.group }))) return;
        try {
          await call("/v1/aurora/security/block", { method: "POST", body: JSON.stringify({ ip: i.source, reason: `${i.kind} ${i.id}` }) });
          const undo = el("button", "", `↩️ ${t("sec.undo", { ip: i.source })}`);    // changed my mind: one click back
          undo.addEventListener("click", async () => {
            try { await call("/v1/aurora/security/block", { method: "POST", body: JSON.stringify({ ip: i.source, unblock: true }) });
              undo.replaceWith(el("span", "ok", t("sec.undone", { ip: i.source }))); this.loadDefence(); }
            catch (e) { alert(e.message); }
          });
          block.replaceWith(undo);
          this.loadDefence();
        }
        catch (e) { alert(e.message); }
      });
      c.append(block);
    }
    if (i.status === "open") {
      const b = el("button", "", `✔ ${t("sec.close")}`);
      b.addEventListener("click", async () => { await call(`/v1/aurora/incidents/${i.id}/close`, { method: "POST" }); this.enter(); });
      c.append(b);
    }
    return c;
  },

  // "NAS (192.0.2.10)" when the firewall knows the address (sec_netmap, owner 2026-10-06)
  who(ip) { return this.names[ip] ? `${this.names[ip]} (${ip})` : ip; },

  ...defence,
  ...watch,

  // a tab's data, the first time it is shown (and again when the page is entered while it is the open one)
  async show(tab, again = false) {
    if (this.loaded.has(tab) && !again) return;
    this.loaded.add(tab);
    if (tab === "incidents") await this.loadOpen();
    if (tab === "defence") { await this.loadDefence(); await this.loadMap(); }
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
    this.group = d.group;
    this.loaded.clear();
    await this.show(this.tab, true);
  },
};

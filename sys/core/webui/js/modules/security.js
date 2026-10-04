// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Firewall incidents: severity, public registry data about the source network, Aurora's report
// with the defensive actions she recommends; the owner closes them.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

const SEV = { high: "bad", medium: "warn", low: "ok" };

export default {
  id: "security",
  icon: "🛡️",
  title: "nav.security",
  plugin: "security",                 // in the menu only when that plugin is on (social: any platform connected)

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="sec.title"></h2><p class="muted" data-i18n="sec.hint"></p>
      <h3 class="setting-cat" data-i18n="sec.open"></h3><div class="open"></div>
      <h3 class="setting-cat" data-i18n="sec.watch"></h3><p class="muted sec-watch-hint"></p>
      <div class="appr-actions"><button class="sec-learn" data-i18n="sec.learn"></button><span class="muted sec-learn-out"></span></div>
      <div class="sec-rules"></div><details class="report"><summary data-i18n="sec.traffic"></summary><div class="sec-groups"></div></details>
      <h3 class="setting-cat"><span data-i18n="sec.closed"></span> <button class="sec-archive" hidden></button></h3>
      <div class="closed"></div>`;
    apply(root);
    this.open = root.querySelector(".open");
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
      el("span", "", ` ${i.kind.startsWith("rule:") ? (i.detail?.title || i.kind) : t(`sec.kind.${i.kind}`)} · ${i.source}${i.internal ? " (" + t("sec.internal") + ")" : ""} · `
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
    if (this.xg && /^\d+\.\d+\.\d+\.\d+$/.test(i.source)) {   // the owner's click is the consent
      const block = el("button", "danger", `⛔ ${t("sec.block", { ip: i.source })}`);
      block.addEventListener("click", async () => {
        if (!confirm(t("sec.block_q", { ip: i.source, group: this.group }))) return;
        try { await call("/v1/aurora/security/block", { method: "POST", body: JSON.stringify({ ip: i.source, reason: `${i.kind} ${i.id}` }) }); alert(t("sec.blocked", { ip: i.source })); }
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

  // what to watch: Aurora's proposals from the documentation and the traffic, each switched on by the owner
  async loadProfile() {
    let p;
    try { p = await call("/v1/aurora/security/profile"); } catch { this.watchHint.textContent = ""; return; }
    this.xg = p.xg;
    this.group = p.group;
    this.watchHint.textContent = t("sec.watch_hint", { doc: p.doc });
    this.rules.replaceChildren(...(p.rules.length ? p.rules.map((r) => {
      const row = el("label", "plug-field plug-check");
      const box = el("input");
      box.type = "checkbox";
      box.checked = r.on;
      box.addEventListener("change", async () => {
        try { await call("/v1/aurora/security/rules", { method: "PUT", body: JSON.stringify({ on: { [r.id]: box.checked } }) }); }
        catch (e) { box.checked = !box.checked; alert(e.message); }
      });
      const text = el("span");
      const tried = r.tried ? ` · ${t("sec.tried", { i: r.tried.incidents, s: r.tried.sources, h: r.tried.hours })}` : "";
      text.append(el("strong", "", r.title), el("div", "muted", `${r.why} · ${t("sec.rule_n", { n: r.threshold, m: r.window_min })}${tried}`),
        el("div", "muted", `💡 ${r.action}`));
      row.append(box, text);
      return row;
    }) : [el("p", "muted", t("sec.no_rules"))]));
    const table = el("table", "table");
    for (const g of p.groups.slice(0, 20)) {
      const tr = el("tr");
      tr.append(el("td", "", String(g.count)), el("td", "", Object.values(g.group).join(" · ")), el("td", "muted", g.log_id));
      table.append(tr);
    }
    this.groups.replaceChildren(table);
  },

  async enter() {
    await this.loadProfile();
    const all = await call("/v1/aurora/incidents");
    const open = all.filter((i) => i.status === "open"), closed = all.filter((i) => i.status !== "open").slice(0, 30);
    this.open.replaceChildren(...(open.length ? open.map((i) => this.card(i)) : [el("p", "muted", t("sec.none"))]));
    this.closed.replaceChildren(...closed.map((i) => this.card(i)));
    const nClosed = all.filter((i) => i.status !== "open").length;
    this.archive.hidden = nClosed === 0;
    this.archive.textContent = t("sec.archive", { n: nClosed });
  },
};

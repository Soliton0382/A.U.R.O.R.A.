// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Firewall incidents: severity, public registry data about the source network, Aurora's report
// with the defensive actions she recommends; the owner closes them.
import { call } from "../api.js";
import { bus } from "../bus.js";
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
      <h3 class="setting-cat" data-i18n="sec.defence"></h3><div class="sec-defence"></div>
      <h3 class="setting-cat" data-i18n="sec.open"></h3><div class="open"></div>
      <h3 class="setting-cat" data-i18n="sec.watch"></h3><p class="muted sec-watch-hint"></p>
      <div class="appr-actions"><button class="sec-learn" data-i18n="sec.learn"></button><span class="muted sec-learn-out"></span></div>
      <div class="sec-rules"></div><details class="report"><summary data-i18n="sec.traffic"></summary><div class="sec-groups"></div></details>
      <h3 class="setting-cat"><span data-i18n="sec.closed"></span> <button class="sec-archive" hidden></button></h3>
      <div class="closed"></div>`;
    apply(root);
    this.open = root.querySelector(".open");
    this.defence = root.querySelector(".sec-defence");
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
    if (i.defence) c.append(el("p", i.defence === "blocked" ? "ok" : "muted", i.defence === "blocked"
      ? `🛡️ ${t("sec.def_blocked", { until: new Date(i.blocked_until * 1000).toLocaleString() })}` : `🛡️ ${t("sec.def_not")}: ${i.defence}`));
    if (this.fwApi && /^\d+\.\d+\.\d+\.\d+$/.test(i.source)) {   // the owner's click is the consent
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
    this.fwApi = p.firewall_api;
    this.group = p.group;
    this.watchHint.textContent = t("sec.watch_hint", { doc: p.doc });
    // each check with its state; the boxes only select, the buttons below act on the selection (owner, 2026-10-05)
    const boxes = [];
    const rows = p.rules.map((r) => {
      const row = el("label", "plug-field plug-check sec-rule");
      const box = el("input");
      box.type = "checkbox";
      box.value = r.id;
      boxes.push(box);
      const tried = r.tried ? ` · ${t("sec.tried", { i: r.tried.incidents, s: r.tried.sources, h: r.tried.hours })}` : "";
      const text = el("span");
      text.append(el("span", `pill ${r.on ? "ok" : ""}`, r.on ? t("sec.on") : t("sec.off")), el("strong", "", ` ${r.title}`),
        el("div", "muted", `${r.why} · ${t("sec.rule_n", { n: r.threshold, m: r.window_min })}${tried}`),
        el("div", "muted", `💡 ${r.action}`));
      row.append(box, text);
      return row;
    });
    const out = el("span", "muted");
    const act = async (what) => {
      const ids = boxes.filter((b) => b.checked).map((b) => b.value);
      if (!ids.length) { out.textContent = t("sec.pick_first"); return; }
      if (what === "drop" && !confirm(t("sec.remove_q", { n: ids.length }))) return;
      const body = what === "drop" ? { remove: ids } : { on: Object.fromEntries(ids.map((i) => [i, what === "on"])) };
      try { await call("/v1/aurora/security/rules", { method: "PUT", body: JSON.stringify(body) }); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); return; }
      this.loadProfile();
    };
    const bar = el("div", "appr-actions");
    const pickAll = el("button", "", t("sec.select_all"));
    pickAll.addEventListener("click", () => { const v = !boxes.every((b) => b.checked); boxes.forEach((b) => { b.checked = v; }); });
    const turnOn = el("button", "approve", `🟢 ${t("sec.turn_on")}`), turnOff = el("button", "", `⚪ ${t("sec.turn_off")}`),
      dropBtn = el("button", "danger", `🗑️ ${t("sec.remove")}`);
    turnOn.addEventListener("click", () => act("on"));
    turnOff.addEventListener("click", () => act("off"));
    dropBtn.addEventListener("click", () => act("drop"));
    bar.append(pickAll, turnOn, turnOff, dropBtn, out);
    const active = p.rules.filter((r) => r.on).length;
    this.rules.replaceChildren(...(p.rules.length
      ? [el("p", "muted", t("sec.active_n", { n: active, of: p.rules.length })), ...rows, bar]
      : [el("p", "muted", t("sec.no_rules"))]));
    const table = el("table", "table");
    for (const g of p.groups.slice(0, 20)) {
      const tr = el("tr");
      tr.append(el("td", "", String(g.count)), el("td", "", Object.values(g.group).join(" · ")), el("td", "muted", g.log_id));
      table.append(tr);
    }
    this.groups.replaceChildren(table);
  },

  // autonomous defence (owner, 2026-10-05): the mode, today's blocks, the active ones with "lift now", the history
  async loadDefence() {
    let d;
    try { d = await call("/v1/aurora/security/defence"); } catch { this.defence.replaceChildren(); return; }
    const head = el("p", "", `${t(`sec.def_mode.${d.mode}`)} · ${t("sec.def_today", { n: d.today, max: d.max_per_day })} · `
      + t("sec.def_limits", { h: d.hours, sev: t(`sec.sev.${d.min_severity}`) }));
    const go = el("button", "", `🧭 ${t("sec.def_change")}`);
    go.addEventListener("click", () => bus.emit("show", { id: "autonomy" }));
    const prot = el("p", "muted", d.protected.length ? t("sec.def_protected", { list: d.protected.join(", ") }) : t("sec.def_no_protected"));
    const act = d.active.map((b) => {
      const r = el("div", "ev");
      const lift = el("button", "", t("sec.def_lift"));
      lift.addEventListener("click", async () => {
        lift.disabled = true;
        try { await call("/v1/aurora/security/defence/release", { method: "POST", body: JSON.stringify({ ip: b.ip }) }); this.loadDefence(); }
        catch (e) { alert(e.message); lift.disabled = false; }
      });
      r.append(el("strong", "", `⛔ ${b.ip}`), el("span", "muted", ` ${b.kind} · ${t("sec.def_until", { until: new Date(b.until * 1000).toLocaleString() })} `), lift);
      return r;
    });
    const hist = el("details", "report");
    hist.append(el("summary", "", t("sec.def_history", { n: d.history.length })),
      ...d.history.map((b) => el("p", "", `${new Date(b.at * 1000).toLocaleString()} · ${b.ip} · ${b.kind} · `
        + (b.released ? t("sec.def_released", { by: t(`sec.def_by.${b.released_by}`) }) : t("sec.def_active")))));
    this.defence.replaceChildren(head, prot, ...(d.configured ? [] : [el("p", "warn", t("sec.def_no_api"))]), ...act, go, hist);
  },

  async enter() {
    this.loadDefence();
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

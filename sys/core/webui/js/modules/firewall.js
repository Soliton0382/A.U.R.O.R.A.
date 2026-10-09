// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧱 Firewall (owner, 2026-10-07/08): the audit of the configuration, Aurora's changes — planned, applied by the owner's
// click on «Applica» (the approval, like ⛔ on an incident), undone with «Annulla» — the forms to publish a server and to
// quarantine a device, the switch of the writes, the firewall's manual searched on this machine.
import { call } from "../api.js";
import { el, external } from "../dom.js";
import { apply, t } from "../i18n.js";
import { apiBack } from "../restart.js";
import { autonomySlot } from "./autonomy_box.js";

const ICON = { high: "🔴", medium: "🟠", low: "🟡" };
const STATE = { planned: "📝", applied: "✅", undone: "↩️", reverted: "↩️", failed: "❌", discarded: "🗑️" };

export default {
  id: "firewall",
  icon: "🧱",
  title: "nav.sec.firewall",
  plugin: "security",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.sec.firewall"></h2><p class="muted" data-i18n="fw.hint"></p>
      <div class="appr-actions fw-write"></div>
      <h3 class="setting-cat" data-i18n="fw.ask"></h3>
      <textarea class="fw-ask" rows="3" data-i18n-placeholder="fw.ask_ph"></textarea>
      <div class="appr-actions"><button class="approve fw-ask-go" data-i18n="fw.ask_go"></button><span class="muted fw-ask-out"></span></div>
      <h3 class="setting-cat"><span data-i18n="fw.changes"></span></h3><div class="fw-changes"></div>
      <h3 class="setting-cat"><span data-i18n="fw.audit"></span> <button class="fw-again" data-i18n="ciso.again"></button></h3><div class="fw-audit"></div>
      <details class="report"><summary data-i18n="fw.publish"></summary>
        <div class="appr-actions"><input class="fw-p-name" placeholder="Nextcloud"><input class="fw-p-host" placeholder="192.0.2.10">
        <input class="fw-p-ports" placeholder="443/tcp"><input class="fw-p-src" data-i18n-placeholder="fw.sources">
        <button class="fw-p-go" data-i18n="fw.plan"></button></div><p class="muted" data-i18n="fw.publish_hint"></p></details>
      <details class="report"><summary data-i18n="fw.quarantine"></summary>
        <div class="appr-actions"><input class="fw-q-ip" placeholder="192.0.2.20"><input class="fw-q-why" data-i18n-placeholder="fw.why">
        <button class="fw-q-go" data-i18n="fw.plan"></button><button class="fw-q-end" data-i18n="fw.release"></button></div></details>
      <details class="report"><summary data-i18n="fw.docs"></summary>
        <div class="appr-actions"><input class="fw-d-q" data-i18n-placeholder="fw.docs_q"><button class="fw-d-go">🔎</button>
        <span class="muted fw-d-stats"></span></div><div class="fw-d-hits"></div></details>`;
    root.querySelector("h2").after(autonomySlot("security"));
    apply(root);
    this.q = (s) => root.querySelector(s);
    this.q(".fw-again").addEventListener("click", () => this.loadAudit(true));
    this.q(".fw-p-go").addEventListener("click", () => this.plan({ kind: "publish", name: this.v(".fw-p-name"),
      host: this.v(".fw-p-host"), ports: this.v(".fw-p-ports"), sources: this.v(".fw-p-src") }));
    this.q(".fw-q-go").addEventListener("click", () => this.plan({ kind: "quarantine", ip: this.v(".fw-q-ip"), reason: this.v(".fw-q-why") }));
    this.q(".fw-q-end").addEventListener("click", () => this.plan({ kind: "release", ip: this.v(".fw-q-ip") }));
    this.q(".fw-ask-go").addEventListener("click", () => this.ask(this.v(".fw-ask")));
    const search = () => this.docs(this.v(".fw-d-q"));
    this.q(".fw-d-go").addEventListener("click", search);
    this.q(".fw-d-q").addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });
  },

  v(s) { return this.q(s).value.trim(); },

  // the owner's words → a plan by the local model, checked by the code; questions when the request is unclear
  async ask(text) {
    const out = this.q(".fw-ask-out"), go = this.q(".fw-ask-go");
    if (!text) return;
    go.disabled = true;
    out.textContent = t("fw.ask_wait");
    const t0 = Date.now();
    try {
      const r = await call("/v1/aurora/security/changes/ask", { method: "POST", body: JSON.stringify({ text }) });
      const s = Math.round((Date.now() - t0) / 1000);
      if (r.need === "origin") this.askOrigin(out, r);           // the owner's own countries, never Aurora's choice
      else if (r.questions) out.textContent = `❓ ${r.questions.join(" · ")}`;
      else { out.textContent = t("fw.ask_done", { s }); await this.loadChanges(); }
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    go.disabled = false;
  },

  // «limit the origin»: which countries or addresses is the owner's answer (C241: a list was invented)
  askOrigin(out, r) {
    const box = el("input");
    box.placeholder = "Italy";
    const go = el("button", "approve", t("fw.origin_go"));
    go.addEventListener("click", () => {
      const v = box.value.trim();
      if (v) this.ask(`${r.request}\n${t("fw.origin_given")}: ${v}`);
    });
    out.replaceChildren(el("p", "", `❓ ${r.questions.join(" ")}`), box, go, ...(r.notes || []).map((n) => el("p", "muted", n)));
  },

  // a finding of the audit handed to the request field (owner, 2026-10-08: «si troverebbe ad ogni suggerimento?»)
  askFor(f) {
    const box = this.q(".fw-ask");
    box.value = t("fw.ask_fix", { what: f.title, why: f.why, fix: f.fix });
    box.scrollIntoView({ behavior: "smooth", block: "center" });
    this.ask(box.value);
  },

  async enter() { await Promise.all([this.loadChanges(), this.loadAudit(false), this.docs("")]); },

  async plan(body) {
    try { await call("/v1/aurora/security/changes/plan", { method: "POST", body: JSON.stringify(body) }); await this.loadChanges(); }
    catch (e) { alert(e.message); }
  },

  writeSwitch(on) {
    const box = this.q(".fw-write");
    const b = el("button", on ? "" : "approve", on ? `🔒 ${t("fw.write_off")}` : `✍️ ${t("fw.write_on")}`);
    b.addEventListener("click", async () => {
      if (!on && !confirm(t("fw.write_q"))) return;
      try {
        const r = await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify({ AURORA_FIREWALL_WRITE: on ? "0" : "1" }) });
        if (r.restart?.length) {
          await call("/v1/aurora/services/restart", { method: "POST", body: JSON.stringify({ services: r.restart }) }).catch(() => null);
          if (r.restart.includes("aurora-api")) await apiBack();
        }
        await this.loadChanges();
      } catch (e) { alert(e.message); }
    });
    box.replaceChildren(el("span", `pill ${on ? "ok" : "warn"}`, on ? t("fw.write_is_on") : t("fw.write_is_off")), b);
  },

  async loadChanges() {
    const c = await call("/v1/aurora/security/changes").catch(() => ({ write: false, items: [] }));
    this.writeSwitch(c.write);
    const box = this.q(".fw-changes");
    box.replaceChildren(...(c.items.length ? c.items.map((ch) => this.change(ch, c.write)) : [el("p", "muted", t("fw.no_changes"))]));
  },

  change(ch, write) {
    const d = el("details", "report");
    d.open = ch.status === "planned";
    d.append(el("summary", "", `${STATE[ch.status] || "•"} ${ch.title} · ${t(`fw.state.${ch.status}`)}`));
    d.append(el("p", "muted", ch.why || ""));
    const steps = el("ol");
    for (const s of ch.steps) {
      const li = el("li", "", s.why);
      if (s.changes?.length) {                       // what an update changes, field by field — not the XML (C241)
        const tb = el("table", "fw-diff");
        tb.append(el("tr", "", ""));
        tb.lastChild.append(el("th", "", t("fw.field")), el("th", "", t("fw.before")), el("th", "", t("fw.after")));
        for (const c of s.changes) {
          const tr = el("tr");
          tr.append(el("td", "", c.field.split("/").pop()), el("td", "", c.before || "—"), el("td", "", c.after || "—"));
          tb.append(tr);
        }
        li.append(tb);
      }
      if (s.kept?.length) li.append(el("p", "muted", t("fw.kept", { f: s.kept.join(", ") })));
      steps.append(li);
    }
    d.append(steps);
    for (const n of ch.notes || []) d.append(el("p", "warn", `⚠️ ${n}`));
    for (const p of ch.problems || []) d.append(el("p", "bad", p));
    const act = (label, action, cls, ask) => {
      const b = el("button", cls, label);
      b.disabled = !write;
      b.title = write ? "" : t("fw.write_is_off");
      b.addEventListener("click", async () => {
        if (!confirm(ask)) return;
        b.disabled = true;
        try { await call(`/v1/aurora/security/changes/${ch.id}/${action}`, { method: "POST" }); }
        catch (e) { alert(e.message); }
        await this.loadChanges();
        this.loadAudit(true);
      });
      return b;
    };
    if (ch.status === "planned") {
      d.append(act(`✔ ${t("fw.apply")}`, "apply", "approve", t("fw.apply_q", { title: ch.title })));
      const drop = el("button", "", `🗑️ ${t("fw.discard")}`);      // a plan not wanted: never applied, kept in the record
      drop.addEventListener("click", async () => {
        try { await call(`/v1/aurora/security/changes/${ch.id}/discard`, { method: "POST" }); } catch (e) { alert(e.message); }
        this.loadChanges();
      });
      d.append(drop);
    }
    if (ch.status === "applied" && ch.steps.some((s) => s.undo)) d.append(act(`↩️ ${t("fw.revert")}`, "revert", "", t("fw.revert_q", { title: ch.title })));
    return d;
  },

  async loadAudit(again) {
    const box = this.q(".fw-audit");
    box.replaceChildren(el("p", "muted", t("ciso.reading")));
    try {
      const a = await call(`/v1/aurora/security/audit?again=${again}`);
      box.replaceChildren(...a.findings.map((f) => {
        const d = el("details", "report");
        d.open = f.severity !== "low";                                 // what needs doing is shown, its buttons too
        d.append(el("summary", "", `${ICON[f.severity]} ${f.title}`), el("p", "", f.why), el("p", "muted", `➜ ${f.fix}`));
        const ask = el("button", "", `✨ ${t("fw.ask_aurora")}`);
        ask.addEventListener("click", () => this.askFor(f));
        d.append(ask);
        // the fix Aurora can make: the IPS policy (the rule's own when it has one) and the log
        const policy = f.ips && f.ips !== "None" ? f.ips : f.ips_policy;
        if (f.rule && policy && (f.ips === "None" || !f.log)) {
          const b = el("button", "approve", `🛡️ ${t("fw.harden", { p: policy })}`);
          b.addEventListener("click", () => this.plan({ kind: "harden", rule: f.rule, ips: policy, log: true }));
          d.append(b);
        }
        return d;
      }), ...(Object.keys(a.errors || {}).length ? [el("p", "warn", `${t("fw.unread")}: ${Object.keys(a.errors).join(", ")}`)] : []));
      if (!a.findings.length) box.append(el("p", "ok", t("fw.clean")));
    } catch (e) { box.replaceChildren(el("p", "bad", t("ev.error", { m: e.message }))); }
  },

  async docs(q) {
    const r = await call(`/v1/aurora/security/docs?q=${encodeURIComponent(q)}`).catch(() => null);
    if (!r) return;
    const st = r.stats;
    this.q(".fw-d-stats").textContent = st.passages ? t("fw.docs_stats", { p: Object.values(st.pages).reduce((a, b) => a + b, 0), n: st.passages })
      : t("fw.docs_none");
    this.q(".fw-d-hits").replaceChildren(...r.hits.map((h) => {
      const d = el("details", "report");
      const a = external(el("a", "", h.title || h.url), h.url);
      const s = el("summary", "", `[${h.kind}] `);
      s.append(a);
      d.append(s, el("pre", "", h.text));
      return d;
    }));
  },
};

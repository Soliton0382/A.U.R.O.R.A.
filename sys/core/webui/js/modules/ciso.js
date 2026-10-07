// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧭 CISO (owner, 2026-10-07/08: «una vera capacità di cyber sicurezza a livello CISO»; «sotto menù specifici»): the
// register of open risks (configuration and activity), the suspects with their playbook — each step says who does
// it — and the threat hunt of the last hours. Read only: a quarantine is prepared here and applied in 🧱 Firewall.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { autonomySlot } from "./autonomy_box.js";

const ICON = { high: "🔴", medium: "🟠", low: "🟡" };

export default {
  id: "ciso",
  icon: "🧭",
  title: "nav.sec.ciso",
  plugin: "security",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.sec.ciso"></h2><p class="muted" data-i18n="ciso.hint"></p>
      <div class="appr-actions"><select class="ciso-hours"><option value="6">6 h</option><option value="24" selected>24 h</option>
      <option value="72">72 h</option></select><button class="ciso-again" data-i18n="ciso.again"></button><span class="muted ciso-state"></span></div>
      <h3 class="setting-cat" data-i18n="ciso.risks"></h3><div class="ciso-risks"></div>
      <h3 class="setting-cat" data-i18n="ciso.suspects"></h3><div class="ciso-groups"></div>
      <h3 class="setting-cat" data-i18n="ciso.hunt"></h3><div class="ciso-hunt"></div>`;
    root.querySelector("h2").after(autonomySlot("security"));
    apply(root);
    this.q = (s) => root.querySelector(s);
    this.q(".ciso-again").addEventListener("click", () => this.load(true));
    this.q(".ciso-hours").addEventListener("change", () => this.load(false));
  },

  async enter() { await this.load(false); },

  async load(again) {
    const hours = this.q(".ciso-hours").value;
    this.q(".ciso-state").textContent = t("ciso.reading");
    try {
      const [p, h] = await Promise.all([call(`/v1/aurora/security/posture?hours=${hours}&again=${again}`),
        call(`/v1/aurora/security/hunt?hours=${hours}`)]);
      this.risks(p);
      this.groups(p.groups);
      this.hunt(h);
      this.q(".ciso-state").textContent = t("ciso.read", { n: h.lines, h: h.hours, s: h.seconds })
        + (p.audit_error ? ` · ⚠️ ${p.audit_error}` : "");
    } catch (e) { this.q(".ciso-state").textContent = t("ev.error", { m: e.message }); }
  },

  risks(p) {
    const box = this.q(".ciso-risks");
    box.replaceChildren(...(p.risks.length ? p.risks.map((r) => {
      const row = el("div", "report");
      row.append(el("strong", "", `${ICON[r.severity] || "•"} ${r.what}`), el("p", "muted", `➜ ${r.fix} · ${r.from}`));
      return row;
    }) : [el("p", "ok", t("ciso.no_risks"))]));
  },

  groups(groups) {
    const box = this.q(".ciso-groups");
    box.replaceChildren(...(groups.length ? groups.map((g) => {
      const d = el("details", "report");
      d.open = g.severity === "high";
      d.append(el("summary", "", `${ICON[g.severity] || "•"} ${g.playbook?.title || ""}: ${g.label}`));
      const signals = el("ul");
      for (const s of g.signals.slice(0, 8)) signals.append(el("li", "", `${ICON[s.severity] || "•"} ${s.title} (${s.from})`));
      const steps = el("ol");
      for (const s of g.playbook?.steps || []) steps.append(el("li", "", `${s.what} — ${s.who}`));
      d.append(signals, el("p", "", t("ciso.todo")), steps);
      if (g.internal && g.scenario !== "check") d.append(this.quarantine(g.who, g.playbook?.title || ""));
      return d;
    }) : [el("p", "ok", t("ciso.no_suspects"))]));
  },

  hunt(h) {
    const box = this.q(".ciso-hunt");
    box.replaceChildren(...(h.findings.length ? h.findings.map((f) => {
      const d = el("details", "report");
      d.append(el("summary", "", `${ICON[f.severity] || "•"} ${f.title}`), el("p", "", f.why), el("p", "muted", `➜ ${f.fix}`));
      return d;
    }) : [el("p", "ok", t("ciso.no_findings"))]));
  },

  // the playbook's first step for a device: the quarantine planned here, applied (or not) in 🧱 Firewall
  quarantine(ip, why) {
    const b = el("button", "danger", `🧪 ${t("ciso.quarantine", { ip })}`);
    b.addEventListener("click", async () => {
      try {
        await call("/v1/aurora/security/changes/plan", { method: "POST", body: JSON.stringify({ kind: "quarantine", ip, reason: why }) });
        bus.emit("show", { id: "firewall" });
      } catch (e) { alert(e.message); }
    });
    return b;
  },
};

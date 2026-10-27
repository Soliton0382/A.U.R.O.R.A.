// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🌐 Aurora's ways out, a page of the security area (owner, 2026-10-27: «un menù apposito per questo tipo di
// controllo… una pagina apposta per il monitoraggio di uscita di aurora con widget nella pagina oggi»): who decides
// (the «security» area of 🤖 Autonomy), the three guards — the local model watched, the deny list, the services' ways
// out learnt (sec_egress, sec_egress_watch) —, today's numbers, every service's networks, and the latest incidents.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { autonomySlot } from "./autonomy_box.js";

const MARK = { denied: "🚫", legit: "✓" };

export default {
  id: "secegress",
  icon: "🌐",
  title: "nav.sec.egress",

  mount(root, ctx) {
    this.ctx = ctx;
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.sec.egress"></h2><p class="muted" data-i18n="egress.hint"></p>
      <div class="td-stats eg-guards"></div>
      <h3 class="setting-cat" data-i18n="egress.services"></h3><p class="muted eg-state"></p><div class="eg-services"></div>
      <h3 class="setting-cat" data-i18n="egress.incidents"></h3><div class="eg-incidents"></div>
      <details class="report"><summary data-i18n="egress.rules"></summary><div class="eg-rules"></div></details>`;
    root.querySelector("h2").after(autonomySlot("security"));
    apply(root);
    this.root = root;
  },

  async enter() {
    let r;
    try { r = await call("/v1/aurora/security/egress"); }
    catch (e) { this.root.querySelector(".eg-guards").replaceChildren(el("p", "warn", e.message)); return; }
    const stat = (big, label, cls = "") => { const b = el("div", `td-stat ${cls}`); b.append(el("strong", "", big), el("small", "muted", label)); return b; };
    this.root.querySelector(".eg-guards").replaceChildren(
      stat(r.model.processes ? "👁️ ✓" : "👁️ —", t(r.model.processes ? "egress.model_on" : "egress.model_off")),
      stat(`🚫 ${r.deny.asns.length}`, t("egress.deny", { n: r.deny.prefixes })),
      stat(r.learning ? "📚" : "🌐 ✓", r.learning ? t("egress.learning", { until: new Date(r.learn_until * 1000).toLocaleDateString() }) : t("egress.watching")),
      stat(`${r.today.networks}`, t("egress.today_networks", { s: r.today.services.length })),
      stat(`${r.today.new}`, t("egress.today_new"), r.today.new ? "warn" : ""),
      stat(`${r.incidents.open}`, t("egress.open"), r.incidents.open ? "warn" : ""));
    this.root.querySelector(".eg-state").textContent = r.learning
      ? t("egress.state_learning", { until: new Date(r.learn_until * 1000).toLocaleDateString() })
      : t("egress.state_watching", { mb: Math.round(r.rule.upload_bytes / 2 ** 20), x: r.rule.factor });
    const services = this.root.querySelector(".eg-services");
    const names = Object.keys(r.services).sort();
    services.replaceChildren(...(names.length ? names.map((svc) => this.service(svc, r.services[svc])) : [el("p", "muted", t("egress.none"))]));
    const list = this.root.querySelector(".eg-incidents");
    const go = el("button", "link", t("egress.open_incidents"));
    go.addEventListener("click", () => this.ctx.show("security"));
    list.replaceChildren(...(r.incidents.latest.length ? r.incidents.latest.map((i) => el("div", i.status === "open" ? "warn" : "muted",
      `${i.severity === "high" ? "🔴" : i.severity === "medium" ? "🟡" : "⚪"} ${t(`sec.kind.${i.kind}`)} · ${i.title} · ${clock(i.received)}${i.decided ? ` · ${i.decided}` : ""}`))
      : [el("p", "ok", t("egress.no_incidents"))]), go);
    this.root.querySelector(".eg-rules").replaceChildren(
      el("p", "", t("egress.rule_model", { s: r.rule.sample_s })),
      el("p", "", t("egress.rule_deny", { asns: r.deny.asns.map((a) => `AS${a}`).join(", ") || "—" })),
      el("p", "", t("egress.rule_learn", { d: r.rule.learn_days, mb: Math.round(r.rule.upload_bytes / 2 ** 20), x: r.rule.factor })));
  },

  service(svc, nets) {
    const d = el("details", "report");
    const fresh = nets.filter((n) => !n.learning && !n.answer).length;
    d.append(el("summary", "", `${svc.replace(".service", "")} · ${t("egress.n", { n: nets.length })}${fresh ? ` · 🆕 ${fresh}` : ""}`));
    const table = el("table", "sec-rules-table");
    const head = el("tr");
    for (const k of ["egress.col_net", "egress.col_seen", "egress.col_sent", "egress.col_last"]) head.append(el("th", "", t(k)));
    table.append(head);
    for (const n of nets.slice(0, 60)) {
      const tr = el("tr");
      const mark = MARK[n.answer] || (n.learning ? "📚" : "🆕");
      tr.append(el("td", "", `${mark} ${n.key} ${n.holder || ""}`), el("td", "", String(n.seen)),
        el("td", "", `${Math.round((n.max_sent || 0) / 1024)} KB`), el("td", "muted", new Date(n.last * 1000).toLocaleString()));
      table.append(tr);
    }
    d.append(table);
    return d;
  },
};

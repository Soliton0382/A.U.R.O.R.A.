// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔥 Aurora's firewall (owner, 2026-10-08: «un menù a parte per il firewall di Aurora con la sua gestione, simile ad un
// mini CISO»): her own machine — what listens on it and who can reach it, the addresses her firewall keeps off (lift
// them, or keep one off by hand), the decoys, the incidents about her machine.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { autonomySlot } from "./autonomy_box.js";

const ICON = { high: "🔴", medium: "🟠", low: "🟡" };
const KIND = { expected: "✅", exposed: "🟡", client: "↗️", local: "🏠" };

export default {
  id: "aurorafw",
  icon: "🔥",
  title: "nav.sec.aurorafw",
  plugin: "security",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.sec.aurorafw"></h2><p class="muted" data-i18n="afw.hint"></p>
      <div class="afw-state"></div>
      <h3 class="setting-cat" data-i18n="afw.findings"></h3><div class="afw-findings"></div>
      <h3 class="setting-cat" data-i18n="afw.blocks"></h3><div class="afw-blocks"></div>
      <div class="appr-actions"><input class="afw-ip" placeholder="203.0.113.7"><input class="afw-why" data-i18n-placeholder="fw.why">
        <select class="afw-hours"><option value="1">1 h</option><option value="24" selected>24 h</option><option value="168">7 d</option></select>
        <button class="danger afw-block" data-i18n="afw.block"></button></div>
      <h3 class="setting-cat" data-i18n="afw.doors"></h3><div class="afw-doors"></div>
      <h3 class="setting-cat" data-i18n="afw.incidents"></h3><div class="afw-incidents"></div>`;
    root.querySelector("h2").after(autonomySlot("security"));
    apply(root);
    this.q = (s) => root.querySelector(s);
    this.q(".afw-block").addEventListener("click", async () => {
      const ip = this.q(".afw-ip").value.trim();
      if (!ip || !confirm(t("afw.block_q", { ip }))) return;
      try {
        const r = await call("/v1/aurora/security/aurora/block", { method: "POST",
          body: JSON.stringify({ ip, why: this.q(".afw-why").value.trim(), hours: this.q(".afw-hours").value }) });
        if (!r.ok) alert(r.why);
      } catch (e) { alert(e.message); }
      this.enter();
    });
  },

  async enter() {
    let h;
    try { h = await call("/v1/aurora/security/aurora"); }
    catch (e) { this.q(".afw-state").replaceChildren(el("p", "bad", t("ev.error", { m: e.message }))); return; }
    const fw = h.hostfw;
    const state = [];
    if (!fw.installed) state.push(el("p", "warn", t("sec.host_install")), el("code", "", "sudo bash sys/deploy/nft/install.sh"));
    else state.push(el("p", fw.on ? "ok" : "warn", fw.on ? t("afw.on", { n: fw.active.length }) : t("afw.off")));
    state.push(el("p", "muted", h.decoys.length ? t("sec.decoys", { p: h.decoys.join(", ") }) : t("sec.no_decoys")));
    const c = h.audit.counts;
    state.push(el("p", "muted", t("afw.counts", { e: c.expected, x: c.exposed, l: c.local, c: c.client })));
    this.q(".afw-state").replaceChildren(...state);

    const f = h.audit.findings;
    this.q(".afw-findings").replaceChildren(...(f.length ? f.map((x) => {
      const d = el("div", "report");
      d.append(el("strong", "", `${ICON[x.severity]} ${x.title}`), el("p", "", x.why), el("p", "muted", `➜ ${x.fix}`));
      return d;
    }) : [el("p", "ok", t("fw.clean"))]));

    this.q(".afw-blocks").replaceChildren(...(fw.active.length ? fw.active.map((b) => {
      const r = el("div", "ev");
      const lift = el("button", "", `↩️ ${t("sec.def_lift")}`);
      lift.addEventListener("click", async () => {
        lift.disabled = true;
        await call("/v1/aurora/security/host/unblock", { method: "POST", body: JSON.stringify({ ip: b.ip }) }).catch(() => null);
        this.enter();
      });
      r.append(el("strong", "", `🧱 ${b.ip}`), el("span", "muted", ` ${b.why} · ${t("sec.def_until", { until: new Date(b.until * 1000).toLocaleString() })} `), lift);
      return r;
    }) : [el("p", "muted", t("afw.no_blocks"))]));

    const doors = h.audit.sockets.filter((s) => s.kind !== "local");
    const local = h.audit.sockets.filter((s) => s.kind === "local");
    const table = el("div");
    for (const s of doors) table.append(el("div", "ev", `${KIND[s.kind] || "•"} ${s.proto} ${s.address} — ${s.what}`));
    const more = el("details");
    more.append(el("summary", "", t("afw.local", { n: local.length })), ...local.map((s) => el("div", "muted", `🏠 ${s.proto} ${s.address} ${s.process || ""}`)));
    this.q(".afw-doors").replaceChildren(table, more);

    this.q(".afw-incidents").replaceChildren(...(h.incidents.length ? h.incidents.map((i) =>
      el("div", "ev", `${ICON[i.severity] || "•"} ${t(`sec.kind.${i.kind}`)} · ${i.source} · ${clock(i.received)} · ${i.status}`))
      : [el("p", "ok", t("afw.no_incidents"))]));
  },
};

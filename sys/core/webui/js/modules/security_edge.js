// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ☁️ Cloudflare, a page of the security area (owner, 2026-10-16: «lo metterei direttamente come una pagina in
// sicurezza dove possiamo anche decidere cosa può fare in autonomia Aurora… cosa ha bloccato, rimozioni»): what Aurora
// may do by herself (the «edge» area of 🤖 Autonomy), the plugin's settings, the tunnel, the blocks active with
// «Sblocca», the ones lifted and by whom, and who the origin refused through Cloudflare with «Blocca».
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { autonomySlot } from "./autonomy_box.js";
import { pluginSlot } from "./plugin_slot.js";

export default {
  id: "edge",
  icon: "☁️",
  title: "nav.sec.edge",
  plugin: "cloudflare",                // in the menu only when that plugin is on

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.sec.edge"></h2><p class="muted" data-i18n="edge.hint"></p>
      <h3 class="setting-cat" data-i18n="edge.active"></h3><div class="edge-active"></div>
      <h3 class="setting-cat"><span data-i18n="edge.culprits"></span> <button class="edge-read" data-i18n="edge.read"></button></h3>
      <div class="edge-culprits"></div>
      <h3 class="setting-cat" data-i18n="edge.history"></h3><div class="edge-history"></div>
      <details class="report"><summary data-i18n="edge.tunnel"></summary><pre class="edge-tunnel"></pre></details>`;
    root.querySelector("h2").after(autonomySlot("edge"), pluginSlot("edge"));
    apply(root);
    this.root = root;
    root.querySelector(".edge-read").addEventListener("click", () => this.culprits());
  },

  async enter() {
    let d;
    try { d = await call("/v1/aurora/security/edge"); } catch (e) { this.root.querySelector(".edge-active").textContent = e.message; return; }
    this.root.querySelector(".edge-tunnel").textContent = d.tunnel;
    const active = this.root.querySelector(".edge-active");
    active.replaceChildren(...(d.active.length ? d.active.map((b) => this.row(b, true)) : [el("p", "muted", t("edge.none"))]));
    const gone = d.history.filter((b) => b.released);
    this.root.querySelector(".edge-history").replaceChildren(...(gone.length ? gone.slice(0, 30).map((b) => this.row(b, false))
      : [el("p", "muted", t("edge.no_history"))]));
  },

  row(b, active) {
    const r = el("div", "acc-row");
    const who = b.auto ? `✨ ${t("edge.by_aurora")}` : `👤 ${t("edge.by_owner")}`;
    const when = active ? t("edge.until", { at: clock(b.until) }) : t("edge.lifted", { at: clock(b.released), by: b.released_by || "?" });
    r.append(el("strong", "", b.ip), el("span", "muted", `${who} · ${b.reason || ""} · ${when}`));
    if (active) {
      const off = el("button", "", `🔓 ${t("edge.unblock")}`);
      off.addEventListener("click", async () => {
        if (!confirm(t("edge.unblock_q", { ip: b.ip }))) return;
        try { await call("/v1/aurora/security/edge/unblock", { method: "POST", body: JSON.stringify({ ip: b.ip }) }); this.enter(); }
        catch (e) { alert(e.message); }
      });
      r.append(off);
    }
    return r;
  },

  async culprits() {
    const box = this.root.querySelector(".edge-culprits");
    box.replaceChildren(el("p", "muted", "…"));
    let d;
    try { d = await call("/v1/aurora/security/edge/culprits?hours=24"); } catch (e) { box.replaceChildren(el("p", "error", e.message)); return; }
    if (!d.culprits.length) { box.replaceChildren(el("p", "muted", t("edge.no_culprits"))); return; }
    box.replaceChildren(...d.culprits.map((c) => {
      const r = el("div", "acc-row");
      r.append(el("strong", "", c.ip), el("span", "muted", `${c.requests} · ${c.hosts.join(", ")} · ${c.paths.join(" ")} — ${c.looks}`));
      const go = el("button", "danger", `⛔ ${t("edge.block")}`);
      go.addEventListener("click", async () => {
        if (!confirm(t("edge.block_q", { ip: c.ip }))) return;
        try {
          await call("/v1/aurora/security/edge/block", { method: "POST", body: JSON.stringify({ ip: c.ip, reason: c.looks, hours: 24 }) });
          this.enter();
          go.disabled = true;
        } catch (e) { alert(e.message); }
      });
      r.append(go);
      return r;
    }));
  },
};

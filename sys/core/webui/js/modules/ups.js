// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔋 UPS in ⚙️ Sistema (owner, 2026-10-28: «l'opzione ups dove le modifico? non c'è una entry nel menù sistema?»): the
// last read of the UPS (mains or battery, charge, runtime, load, which server) every 15 s while the page is open, and
// its settings in a box (sys_ups); the power-off needs the polkit rule, installed again with sudo once.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { settingsForm } from "./settings_form.js";

const KEYS = ["AURORA_UPS_MODE", "AURORA_UPS_SERVERS", "AURORA_UPS_NAME", "AURORA_UPS_USER", "AURORA_UPS_PASSWORD",
  "AURORA_UPS_SHUTDOWN_CHARGE", "AURORA_UPS_SHUTDOWN_RUNTIME_S", "AURORA_UPS_FIREWALL_OFF"];
const RULE = ".venv/bin/python sys/core/script/sys_install_services.py && sudo bash sys/deploy/systemd/install.sh";

export default {
  id: "ups",
  icon: "🔋",
  title: "nav.ups",
  adminOnly: true,

  mount(root) {
    this.root = root;
    root.classList.add("page");
    useCss("/static/css/ups.css");
    root.innerHTML = `<h2 data-i18n="nav.ups"></h2><p class="muted" data-i18n="ups.hint"></p>
      <div class="ups-now"></div><div class="ups-settings"></div>
      <p class="muted ups-rule"><span data-i18n="ups.rule"></span> <code></code></p>`;
    root.querySelector(".ups-rule code").textContent = RULE;
    apply(root);
    settingsForm(KEYS, { title: `⚙️ ${t("ups.settings")}`, onSaved: () => this.enter() })
      .then((f) => root.querySelector(".ups-settings").append(f))
      .catch((e) => root.querySelector(".ups-settings").append(el("p", "error", e.message)));
  },

  async enter() {
    clearTimeout(this.timer);
    const box = this.root.querySelector(".ups-now");
    let s;
    try { s = await call("/v1/aurora/ups"); }
    catch (e) { box.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
    if (s.mode === "off" || !s.servers) box.replaceChildren(el("p", "muted", t("ups.off")));
    else if (!s.at) box.replaceChildren(el("p", "muted", t("ups.waiting")));
    else if (!s.reachable) box.replaceChildren(el("p", "warn", `⚠️ ${t("ups.unreachable")}: ${s.error || ""}`));
    else {
      const v = s.vars || {};
      const state = s.low ? ["low", "🪫", t("ups.low")] : s.on_battery ? ["battery", "🔋", t("ups.battery")] : ["mains", "🔌", t("ups.mains")];
      const card = el("div", `ups-card ups-${state[0]}`);
      const big = el("div", "ups-big");
      big.append(el("span", "ups-icon", state[1]), el("span", "ups-state", state[2]));
      const charge = s.charge ?? null;
      const bar = el("div", "ups-bar");
      const fill = el("div", "ups-fill");
      fill.style.width = `${Math.max(0, Math.min(100, charge ?? 0))}%`;
      bar.append(fill);
      const rows = el("dl", "ups-rows");
      for (const [k, val] of [[t("ups.charge"), charge != null ? `${charge.toFixed(0)} %` : "—"],
        [t("ups.runtime"), s.runtime != null ? `${Math.round(s.runtime / 60)} min` : "—"],
        [t("ups.load"), v["ups.load"] ? `${v["ups.load"]} %` : "—"],
        [t("ups.input"), v["input.voltage"] ? `${v["input.voltage"]} V` : "—"],
        [t("ups.model"), (v["ups.model"] || v["device.model"] || "—").trim()],
        [t("ups.server"), s.server || "—"],
        [t("ups.read"), new Date(s.at * 1000).toLocaleTimeString()]]) rows.append(el("dt", "", k), el("dd", "", val));
      card.append(big, bar, rows);
      if (s.why?.length) card.append(el("p", "warn", s.why.join(", ")));
      box.replaceChildren(card);
    }
    this.timer = setTimeout(() => { if (this.root?.isConnected) this.enter(); }, 15000);
  },
};

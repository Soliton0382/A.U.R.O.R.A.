// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Security → 🔎 Checks and 📤 Outbound: what to watch (proposals from the documentation and the traffic) and what left
// this machine (methods of the security page, split from security.js on 2026-10-06).
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

export const watch = {
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

  // what left this machine (owner, 2026-10-05): measured from the traces, today and the last 7 days
  async loadOutbound() {
    const rows = [];
    for (const days of [1, 7]) {
      let o;
      try { o = await call(`/v1/aurora/security/outbound?days=${days}`); } catch { this.outbound.replaceChildren(); return; }
      const masked = Object.entries(o.cloud.masked).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${t(`social.kind.${k}`)} ${n}`).join(", ");
      const steps = Object.entries(o.cloud.by_step).map(([k, n]) => `${k} ${n}`).join(", ");
      const fw = Object.entries(o.firewall).map(([k, n]) => `${t(`sec.out_fw.${k}`)} ${n}`).join(", ");
      const d = el("details", "report");
      d.open = days === 1;
      d.append(el("summary", "", t(days === 1 ? "sec.out_today" : "sec.out_week")),
        el("p", "", `☁️ ${t("sec.out_cloud", { n: o.cloud.calls })}${steps ? ` (${steps})` : ""}`),
        el("p", "muted", `🎭 ${t("sec.out_masked")}: ${masked || "—"}`),
        el("p", o.cloud.pictures ? "warn" : "muted", `🖼️ ${t("sec.out_pictures", { n: o.cloud.pictures })}`),
        el("p", "", `📣 ${t("sec.out_posts", { n: o.posts.length })}${o.posts.length ? ": " + o.posts.slice(0, 5).map((p) => `${p.title} (${t(`sec.out_by.${p.by}`)})`).join(", ") : ""}`),
        el("p", "", `🔔 ${t("sec.out_push", { n: o.push.sent })}`),
        el("p", "", `🧱 ${t("sec.out_fw")}: ${fw || "—"}`));
      rows.push(d);
    }
    this.outbound.replaceChildren(...rows);
  },
};

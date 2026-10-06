// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Security → 🔎 Checks and 📤 Outbound: what to watch (proposals from the documentation and the traffic) and what left
// this machine (methods of the security page, split from security.js on 2026-10-06).
import { call } from "../api.js";
import { el, info } from "../dom.js";
import { t } from "../i18n.js";

export const watch = {
  // what to watch: Aurora's proposals from the documentation and the traffic, each switched on by the owner
  async loadProfile() {
    let p;
    try { p = await call("/v1/aurora/security/profile?traffic=0"); } catch { this.watchHint.textContent = ""; return; }
    this.fwApi = p.firewall_api;
    this.group = p.group;
    this.watchHint.textContent = t("sec.watch_hint", { doc: p.doc });
    // each check in a table of three columns (owner, 2026-10-06: the list broke the layout on the PC): the tick, the
    // check with its state and an ⓘ for why, then its threshold and what to do; the buttons below act on the ticks
    const boxes = [];
    const table = el("table", "sec-rules-table");
    const head = el("tr");
    const all = el("input"); all.type = "checkbox"; all.title = t("sec.select_all");
    all.addEventListener("change", () => boxes.forEach((b) => { b.checked = all.checked; }));
    const th0 = el("th"); th0.append(all);
    head.append(th0, el("th", "", t("sec.col.check")), el("th", "", t("sec.col.when")));
    table.append(head);
    for (const r of p.rules) {
      const tr = el("tr", r.on ? "on" : "");
      const box = el("input"); box.type = "checkbox"; box.value = r.id; boxes.push(box);
      const c0 = el("td"); c0.append(box);
      const c1 = el("td");
      c1.append(el("span", `pill ${r.on ? "ok" : ""}`, r.on ? t("sec.on") : t("sec.off")), el("strong", "", ` ${r.title}`), info(r.why));
      const tried = r.tried ? ` · ${t("sec.tried", { i: r.tried.incidents, s: r.tried.sources, h: r.tried.hours })}` : "";
      const c2 = el("td", "muted");
      c2.append(el("div", "", `${t("sec.rule_n", { n: r.threshold, m: r.window_min })}${tried}`), el("div", "", `💡 ${r.action}`));
      tr.append(c0, c1, c2);
      tr.addEventListener("click", (ev) => { if (ev.target === tr || ev.target === c2) box.checked = !box.checked; });
      table.append(tr);
    }
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
    const turnOn = el("button", "approve", `🟢 ${t("sec.turn_on")}`), turnOff = el("button", "", `⚪ ${t("sec.turn_off")}`),
      dropBtn = el("button", "danger", `🗑️ ${t("sec.remove")}`);
    turnOn.addEventListener("click", () => act("on"));
    turnOff.addEventListener("click", () => act("off"));
    dropBtn.addEventListener("click", () => act("drop"));
    bar.append(turnOn, turnOff, dropBtn, out);
    const active = p.rules.filter((r) => r.on).length;
    this.rules.replaceChildren(...(p.rules.length
      ? [el("p", "muted", t("sec.active_n", { n: active, of: p.rules.length })), table, bar]
      : [el("p", "muted", t("sec.no_rules"))]));
    // the traffic of the last 24 h only when its section is opened (it takes seconds to read)
    const det = this.groups.closest("details");
    if (det && !det.dataset.lazy) {
      det.dataset.lazy = "1";
      det.addEventListener("toggle", () => { if (det.open) this.loadTraffic(); });
    }
  },

  async loadTraffic() {
    this.groups.replaceChildren(el("p", "muted", "…"));
    let p;
    try { p = await call("/v1/aurora/security/profile?traffic=1"); } catch (e) { this.groups.replaceChildren(el("p", "muted", t("ev.error", { m: e.message }))); return; }
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

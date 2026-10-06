// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Security → 🛡️ Defence: the autonomous defence and the network as the firewall sees it (methods of the security
// page, split from security.js on 2026-10-06: the page loaded everything at once).
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { openMap } from "./security_map.js";

export const defence = {
  // the network as the firewall sees it: counts, what the last look changed, a search, "look again"
  async loadMap() {
    let m;
    try { m = await call("/v1/aurora/security/netmap"); } catch { this.map.replaceChildren(); return; }
    this.names = m.names || {};
    if (!m.configured) { this.map.replaceChildren(el("p", "warn", t("sec.def_no_api"))); return; }
    const line = el("p", "", m.at ? t("sec.map_counts", { when: new Date(m.at * 1000).toLocaleString(), d: m.devices, h: m.hosts,
      g: m.groups, i: m.interfaces, z: m.zones, r: m.reserved }) : t("sec.map_none"));
    const c = m.changes, said = [];
    if (c && !c.first) {
      for (const k of ["new", "gone", "moved"]) if (c[k]?.length) said.push(el("p", k === "new" ? "warn" : "", `${t(`sec.map_${k}`)}: ${c[k].join(", ")}`));
      if (!said.length) said.push(el("p", "muted", t("sec.map_same")));
    }
    const look = el("button", "", `🔄 ${t("sec.map_refresh")}`), out = el("span", "muted");
    look.addEventListener("click", async () => {
      look.disabled = true; out.textContent = "…";
      try { await call("/v1/aurora/security/netmap/refresh", { method: "POST" }); this.loadMap(); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); look.disabled = false; }
    });
    const q = el("input"); q.placeholder = t("sec.map_find"); const found = el("div");
    q.addEventListener("change", async () => {
      const r = await call(`/v1/aurora/security/netmap/find?q=${encodeURIComponent(q.value)}`).catch(() => ({ lines: [] }));
      found.replaceChildren(...(r.lines.length ? r.lines.map((x) => el("div", "", x)) : [el("p", "muted", t("sec.map_nothing"))]));
    });
    const draw = el("button", "primary", `🗺️ ${t("sec.map_show")}`);
    draw.disabled = !m.at;
    draw.addEventListener("click", () => openMap());
    const bar = el("div", "appr-actions");
    bar.append(draw, look, q, out);
    this.map.replaceChildren(line, ...said, bar, found);
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
      lift.textContent = `↩️ ${t("sec.undo", { ip: b.ip })}`;
      r.append(el("strong", "", `⛔ ${this.who(b.ip)}`), el("span", "muted", b.auto
        ? ` ${b.kind} · ${t("sec.def_until", { until: new Date(b.until * 1000).toLocaleString() })} ` : ` ${t("sec.def_manual")} · ${b.reason || ""} `), lift);
      return r;
    });
    const hist = el("details", "report");
    hist.append(el("summary", "", t("sec.def_history", { n: d.history.length })),
      ...d.history.map((b) => el("p", "", `${new Date(b.at * 1000).toLocaleString()} · ${this.who(b.ip)} · ${b.kind} · `
        + (b.released ? t("sec.def_released", { by: t(`sec.def_by.${b.released_by}`) }) : t("sec.def_active")))));
    // the firewall's side, said only once its API is set: the group Aurora fills and the drop rule the owner makes
    const fw = [];
    if (d.configured) {
      const box = el("details", "report");
      box.append(el("summary", "", `🧱 ${t("sec.fw_setup")}`), el("p", "", t("sec.fw_names", { group: d.group, rule: d.rule })));
      const test = el("button", "", `🔌 ${t("sec.fw_test")}`), res = el("span", "muted");
      test.addEventListener("click", async () => {
        res.textContent = "…";
        try { const r = await call("/v1/aurora/security/firewall/test", { method: "POST" });
          res.textContent = r.group_exists ? t("sec.fw_ok", { group: d.group }) : t("sec.fw_nogroup", { group: d.group }); }
        catch (e) { res.textContent = t("ev.error", { m: e.message }); }
      });
      box.append(test, res);
      fw.push(box);
    } else fw.push(el("p", "warn", t("sec.def_no_api")));
    this.defence.replaceChildren(head, prot, ...fw, ...act, go, hist);
  },
};

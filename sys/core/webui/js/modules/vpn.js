// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔒 The VPN of Aurora's own internet (net_vpn, api/vpn), the admin's (it is the machine's traffic). Three tabs
// (owner, 30 Oct: «configurazione completa… anche per le richieste dns… molto personalizzabile ma semplice… separa
// internamente le vpn caricate con le configurazioni da fare con relative recommended»):
//   🔌 Connection: the state, the switch, the profiles as tiles (the default ticked; the last used becomes it), the
//      .ovpn imported several at once, the provider's account;
//   ⚙️ Settings: what passes through the tunnel, the DNS, the domains kept on the normal network, the kill switch, the
//      change of profile by itself — each with its «recommended», and all back to the recommended at once;
//   ℹ️ How it works.
import { call } from "../api.js";
import { clock, el, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";

const PHASE = { off: "⚪", connecting: "⏳", retrying: "🔁", up: "🟢", failed: "🔴", unprotected: "🟠" };
const TABS = ["conn", "conf", "how"];
const rec = () => el("span", "pill ok", t("vpn.recommended"));
const size = (b) => (b == null ? "—" : b < 1e6 ? `${(b / 1e3).toFixed(0)} kB` : b < 1e9 ? `${(b / 1e6).toFixed(1)} MB` : `${(b / 1e9).toFixed(2)} GB`);
const span = (s) => { const m = Math.floor(s / 60); return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`; };

export default {
  id: "vpn",
  icon: "🔒",
  title: "nav.vpn",
  adminOnly: true,

  mount(root) {
    useCss("/static/css/vpn.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.vpn"></h2><p class="muted" data-i18n="vpn.lead"></p>
      <div class="vpn-tabs">${TABS.map((x, i) => `<button type="button" class="cat-chip${i ? "" : " on"}" data-tab="${x}" data-i18n="vpn.tab.${x}"></button>`).join("")}</div>
      <section data-pane="conn">
        <div class="vpn-state"></div>
        <h3 class="setting-cat" data-i18n="vpn.stats"></h3><div class="vpn-stats"></div>
        <h3 class="setting-cat" data-i18n="vpn.profiles"></h3><div class="vpn-grid"></div>
        <div class="vpn-import"><label class="vpn-file"><span data-i18n="vpn.import"></span><input type="file" accept=".ovpn,.conf" multiple hidden></label>
          <span class="muted vpn-import-out"></span></div>
        <h3 class="setting-cat" data-i18n="vpn.account"></h3><p class="muted vpn-account-state"></p>
        <form class="vpn-account appr-actions"><input name="user" autocomplete="off" data-i18n-placeholder="vpn.user">
          <input name="password" type="password" autocomplete="new-password" data-i18n-placeholder="vpn.password">
          <button type="submit" data-i18n="vpn.save"></button><span class="muted vpn-account-out"></span></form>
      </section>
      <section data-pane="conf" hidden>
        <div class="appr-actions"><button type="button" class="vpn-reset" data-i18n="vpn.reset"></button><span class="muted vpn-conf-out"></span></div>
        <h3 class="setting-cat" data-i18n="vpn.through"></h3><p class="muted" data-i18n="vpn.through_hint"></p><div class="vpn-through"></div>
        <h3 class="setting-cat" data-i18n="vpn.dns"></h3><p class="muted" data-i18n="vpn.dns_hint"></p><div class="vpn-dns"></div>
        <h3 class="setting-cat" data-i18n="vpn.split"></h3><p class="muted" data-i18n="vpn.split_hint"></p><div class="vpn-split"></div>
        <h3 class="setting-cat" data-i18n="vpn.behaviour"></h3><div class="vpn-behaviour"></div>
      </section>
      <section data-pane="how" hidden><p data-i18n="vpn.how_text"></p><p class="muted" data-i18n="vpn.how_dns"></p></section>`;
    apply(root);
    this.root = root;
    for (const b of root.querySelectorAll(".vpn-tabs button")) {
      b.addEventListener("click", () => {
        root.querySelectorAll(".vpn-tabs button").forEach((x) => x.classList.toggle("on", x === b));
        root.querySelectorAll("section[data-pane]").forEach((s) => { s.hidden = s.dataset.pane !== b.dataset.tab; });
      });
    }
    const file = root.querySelector(".vpn-file input");
    const iout = root.querySelector(".vpn-import-out");
    file.addEventListener("change", async () => {
      const said = [];
      for (const f of file.files) {
        try {
          const r = await call("/v1/aurora/vpn/profiles", { method: "POST", body: JSON.stringify({ name: f.name, text: await f.text() }) });
          const d = r.profile.dropped;
          said.push(`✅ ${r.profile.name}${d.length ? ` (${t("vpn.dropped", { n: d.length })}: ${d.join(" · ")})` : ""}`);
        } catch (e) { said.push(`❌ ${f.name}: ${e.message}`); }
      }
      iout.textContent = said.join("  ");
      file.value = "";
      this.enter();
    });
    const acc = root.querySelector(".vpn-account");
    acc.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const out = root.querySelector(".vpn-account-out");
      try {
        await call("/v1/aurora/vpn/account", { method: "POST", body: JSON.stringify({ user: acc.user.value, password: acc.password.value }) });
        acc.user.value = acc.password.value = "";
        out.textContent = t("vpn.saved");
        this.enter();
      } catch (e) { out.textContent = e.message; }
    });
    root.querySelector(".vpn-reset").addEventListener("click", () => this.send("/v1/aurora/vpn/recommended", {}));
  },

  // a change of the settings: sent, the page drawn again with what the server keeps, an error said beside the button
  async send(path, body) {
    const out = this.root.querySelector(".vpn-conf-out");
    try { this.draw(await call(path, { method: "POST", body: JSON.stringify(body) })); out.textContent = t("vpn.saved_short"); }
    catch (e) { out.textContent = e.message; this.enter(); }
  },

  async want(body) {
    try { this.draw(await call("/v1/aurora/vpn/want", { method: "POST", body: JSON.stringify(body) })); } catch (e) { alert(e.message); }
    setTimeout(() => this.enter(), 3000);                 // the unit follows within seconds
  },

  async enter() {
    this.draw(await call("/v1/aurora/vpn"));
    clearInterval(this.poll);
    this.poll = setInterval(() => {
      if (document.getElementById("view-vpn")?.classList.contains("hidden")) clearInterval(this.poll);
      else call("/v1/aurora/vpn").then((v) => this.drawState(v)).catch(() => {});
    }, 5000);
  },

  draw(v) {
    this.drawState(v);
    this.drawConf(v);
  },

  drawState(v) {
    const { prefs: p, state: s, profiles } = v;
    const name = (id) => profiles.find((x) => x.id === id)?.name || "—";
    const phase = p.on ? s.phase || "connecting" : "off";
    const head = el("div", `vpn-head ${phase}`);
    head.append(el("span", "vpn-dot", PHASE[phase] || "⚪"), el("strong", "", t(`vpn.phase.${phase}`, { p: name(s.profile) })),
      el("span", "muted", phase === "up" && s.since ? t("vpn.since", { at: clock(s.since) }) : s.error || ""));
    const sw = el("button", p.on ? "" : "primary", p.on ? t("vpn.turn_off") : t("vpn.turn_on"));
    sw.disabled = !p.on && (!profiles.length || !p.account);
    sw.addEventListener("click", () => this.want({ on: !p.on }));
    const ip = el("button", "", t("vpn.ip"));
    const ipOut = el("span", "muted");
    ip.addEventListener("click", async () => {
      ipOut.textContent = "…";
      const r = await call("/v1/aurora/vpn/ip").catch((e) => ({ error: e.message }));
      ipOut.textContent = r.ip ? t("vpn.ip_is", { ip: r.ip }) : t("vpn.ip_none", { e: r.error || "" });
    });
    const bar = el("div", "appr-actions");
    bar.append(sw, ip, ipOut);
    const parts = [head, bar];
    if (!profiles.length || !p.account) parts.push(el("p", "warn", t("vpn.missing")));
    if (p.on && phase === "failed") {                     // every profile failed: the owner decides (owner, 30 Oct)
      const ask = el("div", "vpn-ask");
      const go = el("button", "", t("vpn.unprotected_go"));
      go.addEventListener("click", () => { if (confirm(t("vpn.unprotected_q"))) this.want({ unprotected: true }); });
      ask.append(el("p", "", t("vpn.failed_text", { n: (s.tried || []).length })), go);
      parts.push(ask);
    }
    if (p.on && p.unprotected) {
      const back = el("button", "", t("vpn.unprotected_stop"));
      back.addEventListener("click", () => this.want({ unprotected: false }));
      parts.push(el("p", "warn", t("vpn.unprotected_on")), back);
    }
    this.root.querySelector(".vpn-state").replaceChildren(...parts);
    // 📊 the statistics (owner, 30 Oct): this connection's time and traffic, the connections and resets since the
    // unit started, the last and the next reset
    const live = phase === "up";
    const tile = (icon, label, value) => {
      const x = el("div", "vpn-stat");
      x.append(el("span", "vpn-stat-label", `${icon} ${label}`), el("span", "vpn-stat-value", value));
      return x;
    };
    this.root.querySelector(".vpn-stats").replaceChildren(
      tile("⏱️", t("vpn.st.up"), live && s.since ? span(Date.now() / 1000 - s.since) : "—"),
      tile("⬇️", t("vpn.st.in"), live ? size(s.bytes_in) : "—"),
      tile("⬆️", t("vpn.st.out"), live ? size(s.bytes_out) : "—"),
      tile("🔁", t("vpn.st.conn"), String(s.connections ?? 0)),
      tile("♻️", t("vpn.st.reset"), s.last_reset ? clock(s.last_reset) : "—"),
      tile("⏭️", t("vpn.st.next"), live && s.next_reset ? clock(s.next_reset) : p.reset_h ? "—" : t("vpn.st.never")));
    this.root.querySelector(".vpn-account-state").textContent = p.account ? t("vpn.account_set") : t("vpn.account_none");
    this.root.querySelector(".vpn-grid").replaceChildren(...(profiles.length ? profiles.map((x) => {
      const tile = el("div", `vpn-tile${s.profile === x.id && phase === "up" ? " up" : ""}${p.default === x.id ? " def" : ""}`);
      const pick = el("label", "vpn-def");
      const r = el("input");
      r.type = "radio";
      r.name = "vpn-default";
      r.checked = p.default === x.id;
      r.addEventListener("change", async () => this.draw(await call("/v1/aurora/vpn/default", { method: "POST", body: JSON.stringify({ id: x.id }) })));
      pick.append(r, el("span", "", t("vpn.default")));
      const use = el("button", "", `▶ ${t("vpn.use")}`);
      use.addEventListener("click", () => this.want({ use: x.id }));
      const del = el("button", "", "🗑️");
      del.title = t("vpn.delete");
      del.addEventListener("click", async () => { if (confirm(t("vpn.delete_q", { n: x.name }))) this.draw(await call(`/v1/aurora/vpn/profiles/${x.id}`, { method: "DELETE" })); });
      const tools = el("div", "vpn-tools");
      tools.append(use, del);
      tile.append(el("span", "vpn-name", x.name), el("span", "vpn-server muted", x.server),
        el("span", "muted vpn-last", p.last === x.id ? t("vpn.last") : ""), pick, tools);
      return tile;
    }) : [el("p", "muted", t("vpn.none"))]));
  },

  drawConf(v) {
    const { prefs: p } = v;
    const R = v.recommended || {};
    const code = lang.slice(0, 2);
    const check = (label, on, change, recommended) => {
      const l = el("label", "vpn-check");
      const b = el("input");
      b.type = "checkbox";
      b.checked = on;
      b.addEventListener("change", () => change(b.checked));
      l.append(b, el("span", "", label), ...(recommended ? [rec()] : []));
      return l;
    };
    // what passes through: one service a line
    const through = (v.choices || []).map((c) => check(c[code] || c.en, (p.through || []).includes(c.id), (on) => {
      const units = (v.choices || []).map((x) => x.id).filter((id) => (id === c.id ? on : (p.through || []).includes(id)));
      this.send("/v1/aurora/vpn/through", { units });
    }, c.recommended));
    this.root.querySelector(".vpn-through").replaceChildren(...through);
    // the DNS: the provider's (pushed by the tunnel) or the owner's servers, asked through the tunnel either way
    const dns = el("div", "vpn-dns-box");
    for (const mode of ["provider", "custom"]) {
      const l = el("label", "vpn-check");
      const r = el("input");
      r.type = "radio";
      r.name = "vpn-dns";
      r.checked = p.dns === mode;
      r.addEventListener("change", () => {
        if (mode === "custom" && !(p.dns_servers || []).length) { servers.focus(); return; }
        this.send("/v1/aurora/vpn/options", { dns: mode });
      });
      l.append(r, el("span", "", t(`vpn.dns.${mode}`)), ...(R.dns === mode ? [rec()] : []));
      dns.append(l);
    }
    const form = el("form", "appr-actions");
    const servers = el("input");
    servers.value = (p.dns_servers || []).join(", ");
    servers.placeholder = t("vpn.dns_ph");
    const save = el("button", "", t("vpn.save"));
    save.type = "submit";
    form.append(servers, save);
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const list = servers.value.split(/[,;\s]+/).filter(Boolean);
      this.send("/v1/aurora/vpn/options", list.length ? { dns: "custom", dns_servers: list } : { dns: "provider", dns_servers: [] });
    });
    dns.append(form);
    this.root.querySelector(".vpn-dns").replaceChildren(dns);
    // the domains kept on the normal network: a chip each, the suggested ones offered
    const box = el("div", "vpn-split-box");
    const list = el("div", "chips vpn-chips");
    for (const d of p.split || []) {
      const c = el("button", "chip", `🏠 ${d} ✕`);
      c.type = "button";
      c.title = t("vpn.split_remove");
      c.addEventListener("click", () => this.send("/v1/aurora/vpn/split", { domains: (p.split || []).filter((x) => x !== d) }));
      list.append(c);
    }
    for (const d of v.suggested_split || []) {
      const c = el("button", "chip vpn-suggest", `➕ ${d}`);
      c.type = "button";
      c.append(rec());
      c.addEventListener("click", () => this.send("/v1/aurora/vpn/split", { domains: [...(p.split || []), d] }));
      list.append(c);
    }
    const add = el("form", "appr-actions");
    const dom = el("input");
    dom.placeholder = t("vpn.split_ph");
    const go = el("button", "", t("vpn.split_add"));
    go.type = "submit";
    add.append(dom, go);
    add.addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (dom.value.trim()) this.send("/v1/aurora/vpn/split", { domains: [...(p.split || []), dom.value.trim()] });
    });
    box.append(list, add);
    this.root.querySelector(".vpn-split").replaceChildren(box);
    // how it behaves when the tunnel falls
    this.root.querySelector(".vpn-behaviour").replaceChildren(
      check(t("vpn.killswitch"), p.killswitch, (on) => this.send("/v1/aurora/vpn/options", { killswitch: on }), R.killswitch === true),
      el("p", "muted vpn-sub", t("vpn.killswitch_hint")),
      check(t("vpn.failover"), p.failover, (on) => this.send("/v1/aurora/vpn/options", { failover: on }), R.failover === true),
      el("p", "muted vpn-sub", t("vpn.failover_hint")), this.resetRow(p, R), el("p", "muted vpn-sub", t("vpn.keepalive")));
  },

  // the connection made again every so many hours (owner, 30 Oct: «un timer per il reset connessione… ogni 2 ore»)
  resetRow(p, R) {
    const f = el("form", "vpn-check vpn-reset-row");
    const h = el("input");
    h.type = "number";
    h.min = "0";
    h.max = "48";
    h.value = String(p.reset_h ?? 2);
    const save = el("button", "", t("vpn.save"));
    save.type = "submit";
    f.append(el("span", "", t("vpn.reset_every")), h, el("span", "", t("vpn.hours")), save, ...(Number(p.reset_h) === R.reset_h ? [rec()] : []));
    f.addEventListener("submit", (ev) => { ev.preventDefault(); this.send("/v1/aurora/vpn/options", { reset_h: Number(h.value) }); });
    return f;
  },
};

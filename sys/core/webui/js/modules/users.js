// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 👥 Users: my account (password, the Authenticator's QR) for everyone; the admin's users (create, reset, delete with
// the list of what goes). The mode single / multi is in Settings → Users, with its explanation.
import { call } from "../api.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { qrSvg } from "../qr.js";
import { bus } from "../bus.js";

export default {
  id: "users",
  icon: "👥",
  title: "nav.users",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="users.title"></h2><p class="muted" data-i18n="users.hint"></p>
      <h3 class="setting-cat" data-i18n="users.me"></h3><div class="me"></div>
      <div class="admin hidden"><h3 class="setting-cat" data-i18n="users.all"></h3><div class="list"></div>
        <h3 class="setting-cat" data-i18n="perm.title"></h3><p class="muted" data-i18n="perm.hint"></p><div class="perm"></div>
        <form class="import add"><input name="person" data-i18n-placeholder="users.person" required>
          <input name="name" autocapitalize="none" autocomplete="off" spellcheck="false" data-i18n-placeholder="users.name" required>
          <input name="password" type="password" autocomplete="new-password" data-i18n-placeholder="users.password" required>
          <button type="submit" data-i18n="users.add"></button></form><p class="result add-out"></p></div>`;
    apply(root);
    this.meBox = root.querySelector(".me");
    this.adminBox = root.querySelector(".admin");
    this.list = root.querySelector(".list");
    const out = root.querySelector(".add-out");
    const uname = root.querySelector(".add input[name=name]");
    uname.addEventListener("input", () => { uname.value = uname.value.toLowerCase().replace(/\s+/g, ""); });
    root.querySelector(".add").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = ev.target;
      try {
        await call("/v1/aurora/users", { method: "POST", body: JSON.stringify({ name: f.name.value.trim(), person: f.person.value.trim(), password: f.password.value }) });
        const added = f.name.value.trim();
        out.textContent = t("users.added", { name: added });
        out.className = "result add-out";
        f.reset();
        await this.loadUsers(added);
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); out.className = "result add-out error"; }
    });
  },

  // ⚙️ my preferences (owner, 2026-10-06: a user does not enter the Settings): what is theirs and not in a plugin's card
  async preferences(box) {
    let r;
    try { r = await call("/v1/aurora/settings"); } catch { return; }
    const code = (document.documentElement.lang || "it").slice(0, 2);
    const mine = r.settings.filter((s) => s.scope === "user" && !s.plugin && !s.secret);
    if (!mine.length) return;
    const d = el("details", "report");
    d.append(el("summary", "", `⚙️ ${t("users.prefs")}`));
    const inputs = mine.map((s) => {
      const row = el("label", "plug-field");
      let i;
      if (s.type === "bool" || s.type === "enum") {
        i = el("select");
        for (const c of s.type === "bool" ? ["0", "1"] : s.choices) {
          const lab = t(`choice.${s.key}.${c}`);
          const o = el("option", "", lab.startsWith("choice.") ? c : lab); o.value = c; i.append(o);
        }
        i.value = s.type === "bool" ? (["1", "true", "yes", "on"].includes(String(s.value).toLowerCase()) ? "1" : "0") : s.value;
      } else { i = el("input"); i.value = s.value ?? ""; }
      i.dataset.key = s.key;
      i.dataset.was = i.value;
      row.append(el("span", "", s[code] || s.en), i);
      return row;
    });
    const out = el("span", "muted");
    const save = el("button", "", t("settings.save"));
    save.addEventListener("click", async () => {
      const changes = {};
      d.querySelectorAll("[data-key]").forEach((i) => { if (i.value !== i.dataset.was) changes[i.dataset.key] = i.value; });
      if (!Object.keys(changes).length) { out.textContent = t("settings.none"); return; }
      try { await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify(changes) }); out.textContent = `✅ ${t("users.prefs_saved")}`; }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
    d.append(...inputs, save, out);
    box.append(d);
  },

  async enter() {
    const me = await call("/v1/aurora/me");
    this.renderMe(me);
    this.adminBox.classList.toggle("hidden", !me.admin);
    if (me.admin) await this.loadUsers();
  },

  renderMe(me) {
    const box = this.meBox;
    box.replaceChildren(el("p", "", t("users.me_line", { name: me.name || "—", role: t(`users.role.${me.admin ? "admin" : "user"}`),
      mode: me.mode })), el("p", "muted", `${me.has_password ? "✅" : "⚠️"} ${t("users.has_password")} · ${me.totp_on ? "✅" : "⚠️"} ${t("users.totp")}`));
    if (!me.name) { box.append(el("p", "muted", t("users.no_users"))); return; }
    if (!me.admin) this.preferences(box);              // a user: their own preferences here, not in ⚙️ Settings
    const pw = el("form", "import");
    const old = el("input"); old.type = "password"; old.placeholder = t("users.old"); old.autocomplete = "current-password";
    const neu = el("input"); neu.type = "password"; neu.placeholder = t("users.new"); neu.autocomplete = "new-password"; neu.required = true;
    const save = el("button", "", t("users.set_password")); save.type = "submit";
    const res = el("p", "result");
    if (!me.has_password) old.hidden = true;
    pw.append(old, neu, save);
    pw.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await call("/v1/aurora/me/password", { method: "POST", body: JSON.stringify({ old: old.value, new: neu.value }) });
        res.textContent = t("users.password_ok"); res.className = "result"; old.value = neu.value = "";
        this.renderMe(await call("/v1/aurora/me"));
        bus.emit("me-changed");
      } catch (e) { res.textContent = t("ev.error", { m: e.message }); res.className = "result error"; }
    });
    const totp = el("button", "", t(me.totp_on ? "users.totp_again" : "users.totp_link"));
    totp.type = "button";
    const enrol = el("div", "enrol");
    totp.addEventListener("click", async () => {
      let ask = {};
      if (me.totp_on) {                                  // C440: the password and the current code before a new one
        const pw = prompt(t("users.totp_pw"));
        if (!pw) return;
        const cur = prompt(t("users.totp_current"));
        if (!cur) return;
        ask = { password: pw, current: cur.trim() };
      }
      let r;
      try { r = await call("/v1/aurora/me/totp", { method: "POST", body: JSON.stringify(ask) }); }
      catch (e) { enrol.replaceChildren(el("p", "result error", t("ev.error", { m: e.message }))); return; }
      const code = el("input"); code.inputMode = "numeric"; code.maxLength = 6; code.placeholder = t("login.code");
      const ok = el("button", "", t("users.totp_confirm")); ok.type = "button";
      const msg = el("p", "result");
      ok.addEventListener("click", async () => {
        try {
          await call("/v1/aurora/me/totp", { method: "POST", body: JSON.stringify({ code: code.value.trim() }) });
          enrol.replaceChildren(el("p", "result", t("users.totp_ok")));
          this.renderMe(await call("/v1/aurora/me"));
          bus.emit("me-changed");
        } catch (e) { msg.textContent = t("ev.error", { m: e.message }); msg.className = "result error"; }
      });
      enrol.replaceChildren(el("p", "", t("login.enroll")), qrSvg(r.uri),
        el("p", "muted", `${t("login.secret")} ${r.secret}`), code, ok, msg);
    });
    box.append(pw, res, totp, enrol, el("h4", "", `🔑 ${t("users.keys")}`), this.keysBox = el("div", "keys"));
    this.loadKeys();
    if (!me.admin || me.assist) { box.append(this.assistBox = el("div", "assist")); this.loadAssist(); }
  },

  // 🛟 Assistance (sys_assist): the disclaimer is the consent; a window of hours, revocable; every step of the admin listed
  async loadAssist() {
    const box = this.assistBox;
    let a;
    try { a = await call("/v1/aurora/assist"); } catch (e) { box.replaceChildren(el("p", "result error", e.message)); return; }
    const when = (s) => new Date(s * 1000).toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    box.replaceChildren(el("h4", "", `🛟 ${t("assist.title")}`), el("p", "muted", t("assist.disclaimer")));
    if (a.grant) {
      box.append(el("p", a.inside ? "warn" : "", t(a.inside ? "assist.inside" : "assist.open", { until: when(a.grant.until) })));
      if (!a.session) {
        const stop = el("button", "danger", t("assist.revoke"));
        stop.type = "button";
        stop.addEventListener("click", async () => { await call("/v1/aurora/assist/revoke", { method: "POST", body: "{}" }); this.loadAssist(); });
        box.append(stop);
      }
    } else if (!a.session) {
      const hours = el("select");
      for (const h of a.windows) { const o = el("option", "", t("assist.hours", { h })); o.value = h; hours.append(o); }
      const go = el("button", "approve", t("assist.grant"));
      go.type = "button";
      go.addEventListener("click", async () => {
        try { await call("/v1/aurora/assist/grant", { method: "POST", body: JSON.stringify({ hours: Number(hours.value) }) }); }
        catch (e) { alert(e.message); }
        this.loadAssist();
      });
      const row = el("div", "appr-actions");
      row.append(hours, go);
      box.append(row);
    }
    const what = (s) => (["grant", "revoke", "enter", "end"].includes(s.what) ? t(`assist.step.${s.what}`, { path: s.path }) : `${s.what} ${s.path}`);
    const d = el("details");
    d.append(el("summary", "", t("assist.log", { n: a.log.length })),
      ...(a.log.length ? a.log.map((s) => el("div", "ev", `${when(s.at)} · ${s.by} · ${what(s)}`)) : [el("p", "muted", t("assist.log_none"))]));
    box.append(d);
  },

  // the user's own API keys: one per program (Chatbox, LibreChat...), each working as this user, revocable
  async loadKeys(justMade = null) {
    const box = this.keysBox;
    const k = await call("/v1/aurora/me/keys");
    box.replaceChildren(el("p", "muted", t("users.keys_hint", { url: k.base_url, model: k.model })));
    for (const key of k.keys) {
      const row = el("div", "ev");
      const del = el("button", "", t("users.revoke"));
      del.addEventListener("click", async () => {
        if (!confirm(t("users.revoke_q", { name: key.name }))) return;
        await call(`/v1/aurora/me/keys/${key.id}`, { method: "DELETE" });
        this.loadKeys();
      });
      row.append(el("strong", "", key.name), el("span", "muted", t("users.key_seen", { at: key.last_seen || "—" })), del);
      box.append(row);
    }
    const form = el("form", "import");
    const name = el("input"); name.placeholder = t("users.key_name"); name.required = true;
    const add = el("button", "", t("users.key_new")); add.type = "submit";
    const shown = el("div", "result");
    form.append(name, add);
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const r = await call("/v1/aurora/me/keys", { method: "POST", body: JSON.stringify({ name: name.value.trim() }) });
      this.loadKeys(r.key);                          // the list again, with the new key shown once below it
    });
    if (justMade) shown.append(el("p", "", t("users.key_once")), el("code", "", justMade));
    box.append(form, shown);
  },

  // added: the user just created — the list is above the form, off a phone's screen: scrolled to and lit (owner, 17 Oct:
  // «la pagina non si è ricaricata per mostrarmi il nuovo utente»)
  async loadUsers(added = null) {
    const { users, admin } = await call("/v1/aurora/users");
    const table = el("table", "table");
    const head = el("tr");
    for (const k of ["users.name", "users.role", "users.totp", "users.files", "users.devices", "users.cloud", "users.conduct", ""]) head.append(el("th", "", k && t(k)));
    table.append(head);
    for (const u of users) {
      const tr = el("tr");
      const acts = el("td");
      if (u.name !== admin) {
        const pw = el("button", "", t("users.reset_password"));
        pw.addEventListener("click", async () => {
          const p = prompt(t("users.new_password_for", { name: u.name }));
          if (p) { try { await call(`/v1/aurora/users/${encodeURIComponent(u.name)}/password`, { method: "POST", body: JSON.stringify({ password: p }) }); } catch (e) { alert(e.message); } }
        });
        const tt = el("button", "", t("users.reset_totp"));
        tt.addEventListener("click", async () => {
          if (confirm(t("users.reset_totp_q", { name: u.name }))) { await call(`/v1/aurora/users/${encodeURIComponent(u.name)}/totp-reset`, { method: "POST", body: "{}" }); this.loadUsers(); }
        });
        const del = el("button", "danger", t("users.delete"));
        del.addEventListener("click", async () => {
          const url = `/v1/aurora/users/${encodeURIComponent(u.name)}`;
          try { await call(url, { method: "DELETE" }); } catch (e) {
            let d = null;
            try { d = JSON.parse(e.message); } catch { /* not the list */ }
            if (e.status !== 409 || !d?.plan) { alert(e.message); return; }
            const files = d.plan[0].items.reduce((n, i) => n + (i.files || 0), 0);
            if (!confirm(t("users.delete_q", { name: u.name, files }))) return;
            try { await call(`${url}?confirm=purge`, { method: "DELETE" }); } catch (e2) { alert(e2.message); }
          }
          this.loadUsers();
        });
        acts.append(pw, tt, del);
        if (u.assist) {                                // 🛟 the user opened the assistance: the admin may enter
          const go = el("button", "approve", t("assist.enter"));
          go.title = t("assist.enter_until", { until: new Date(u.assist.until * 1000).toLocaleString() });
          go.addEventListener("click", async () => {
            try { await call("/v1/aurora/assist/enter", { method: "POST", body: JSON.stringify({ user: u.name }) }); location.reload(); }
            catch (e) { alert(e.message); }
          });
          acts.prepend(go);
        }
      }
      tr.append(el("td", "", u.name), el("td", "", t(`users.role.${u.role}`)), el("td", "", u.totp_on ? "✅" : "—"),
        el("td", "", String(u.files)), el("td", "", String(u.devices)), this.cloudCell(u, admin), this.conductCell(u.conduct), acts);
      table.append(tr);
      if (u.name === added) tr.classList.add("just-added");
    }
    this.list.replaceChildren(table);
    table.querySelector(".just-added")?.scrollIntoView({ behavior: "smooth", block: "center" });
    this.loadPerms();
  },

  // 📋 the behaviour card (kno_anger.card): the last 30 days' offences, apologies and cool-downs, each day on a click
  conductCell(c) {
    const td = el("td");
    if (!c || !c.days.length) { td.append(el("span", "muted", t("users.conduct_none"))); return td; }
    const d = el("details");
    d.append(el("summary", c.offence ? "warn" : "", `😠 ${c.offence} · 🙂 ${c.apology} · ⏸️ ${c.cool}`));
    for (const r of c.days) d.append(el("div", "muted", `${r.day}: 😠 ${r.offence} · 🙂 ${r.apology} · ⏸️ ${r.cool}`));
    d.title = t("users.conduct_hint");
    td.append(d);
    return td;
  },

  // a user's cloud tokens a day (every provider, the subscription too): the admin's choice, today's use beside it
  cloudCell(u, admin) {
    const td = el("td");
    const k = (n) => `${Math.round(n / 1000).toLocaleString()} k`;
    if (u.name === admin) { td.append(el("span", "muted", `${k(u.cloud_today || 0)} · ${t("users.cloud_none")}`)); return td; }
    const input = el("input");
    Object.assign(input, { type: "number", min: 0, step: 50, value: Math.round((u.cloud_cap || 0) / 1000), title: t("users.cloud_hint") });
    input.style.width = "6em";
    const used = el("span", u.cloud_cap && u.cloud_today >= u.cloud_cap ? "warn" : "muted",
      ` k · ${t("users.cloud_today", { n: k(u.cloud_today || 0) })}`);
    input.addEventListener("change", async () => {
      try { await call("/v1/aurora/users/cloud", { method: "PUT", body: JSON.stringify({ user: u.name, tokens: Math.max(0, Number(input.value) || 0) * 1000 }) }); input.classList.add("saved"); }
      catch (e) { alert(e.message); }
    });
    td.append(input, used);
    return td;
  },

  // what each user manages by themselves (sys_users_perm): the admin's choice, one switch per user and area
  async loadPerms() {
    const box = this.list.parentElement.querySelector(".perm");
    let d;
    try { d = await call("/v1/aurora/users/permissions"); } catch (e) { box.textContent = e.message; return; }
    const names = Object.keys(d.users);
    if (!names.length) { box.replaceChildren(el("p", "muted", t("perm.none"))); return; }
    const table = el("table", "table");
    const head = el("tr");
    head.append(el("th", "", t("users.name")), ...d.areas.map((a) => el("th", "", t(`perm.area.${a}`))));
    table.append(head);
    for (const u of names) {
      const tr = el("tr");
      tr.append(el("td", "", u));
      for (const a of d.areas) {
        const c = el("input");
        c.type = "checkbox";
        c.checked = !!d.users[u][a];
        c.addEventListener("change", async () => {
          try { await call("/v1/aurora/users/permissions", { method: "PUT", body: JSON.stringify({ user: u, area: a, allowed: c.checked }) }); }
          catch (e) { c.checked = !c.checked; alert(e.message); }
        });
        const td = el("td");
        td.append(c);
        tr.append(td);
      }
      table.append(tr);
    }
    box.replaceChildren(table, el("p", "muted", t("perm.admin_only", { list: d.admin_only.map((a) => t(`perm.fixed.${a}`)).join(", ") })),
      el("p", "muted", t("perm.always")));
  },
};

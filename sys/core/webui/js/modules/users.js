// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 👥 Users: my account (password, the Authenticator's QR) for everyone; the admin's users (create, reset, delete with
// the list of what goes). The mode single / multi is in Settings → Users, with its explanation.
import { call } from "../api.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { qrSvg } from "../qr.js";

export default {
  id: "users",
  icon: "👥",
  title: "nav.users",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="users.title"></h2><p class="muted" data-i18n="users.hint"></p>
      <h3 class="setting-cat" data-i18n="users.me"></h3><div class="me"></div>
      <div class="admin hidden"><h3 class="setting-cat" data-i18n="users.all"></h3><div class="list"></div>
        <form class="import add"><input name="person" data-i18n-placeholder="users.person">
          <input name="name" autocapitalize="none" data-i18n-placeholder="users.name" required>
          <input name="password" type="password" autocomplete="new-password" data-i18n-placeholder="users.password" required>
          <button type="submit" data-i18n="users.add"></button></form><p class="result add-out"></p></div>`;
    apply(root);
    this.meBox = root.querySelector(".me");
    this.adminBox = root.querySelector(".admin");
    this.list = root.querySelector(".list");
    const out = root.querySelector(".add-out");
    root.querySelector(".add").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = ev.target;
      try {
        await call("/v1/aurora/users", { method: "POST", body: JSON.stringify({ name: f.name.value.trim(), person: f.person.value.trim(), password: f.password.value }) });
        out.textContent = t("users.added", { name: f.name.value.trim() });
        out.className = "result add-out";
        f.reset();
        this.loadUsers();
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); out.className = "result add-out error"; }
    });
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
      } catch (e) { res.textContent = t("ev.error", { m: e.message }); res.className = "result error"; }
    });
    const totp = el("button", "", t(me.totp_on ? "users.totp_again" : "users.totp_link"));
    totp.type = "button";
    const enrol = el("div", "enrol");
    totp.addEventListener("click", async () => {
      const r = await call("/v1/aurora/me/totp", { method: "POST", body: "{}" });
      const code = el("input"); code.inputMode = "numeric"; code.maxLength = 6; code.placeholder = t("login.code");
      const ok = el("button", "", t("users.totp_confirm")); ok.type = "button";
      const msg = el("p", "result");
      ok.addEventListener("click", async () => {
        try {
          await call("/v1/aurora/me/totp", { method: "POST", body: JSON.stringify({ code: code.value.trim() }) });
          enrol.replaceChildren(el("p", "result", t("users.totp_ok")));
          this.renderMe(await call("/v1/aurora/me"));
        } catch (e) { msg.textContent = t("ev.error", { m: e.message }); msg.className = "result error"; }
      });
      enrol.replaceChildren(el("p", "", t("login.enroll")), qrSvg(r.uri),
        el("p", "muted", `${t("login.secret")} ${r.secret}`), code, ok, msg);
    });
    box.append(pw, res, totp, enrol, el("h4", "", `🔑 ${t("users.keys")}`), this.keysBox = el("div", "keys"));
    this.loadKeys();
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

  async loadUsers() {
    const { users, admin } = await call("/v1/aurora/users");
    const table = el("table", "table");
    const head = el("tr");
    for (const k of ["users.name", "users.role", "users.totp", "users.files", "users.devices", ""]) head.append(el("th", "", k && t(k)));
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
      }
      tr.append(el("td", "", u.name), el("td", "", t(`users.role.${u.role}`)), el("td", "", u.totp_on ? "✅" : "—"),
        el("td", "", String(u.files)), el("td", "", String(u.devices)), acts);
      table.append(tr);
    }
    this.list.replaceChildren(table);
  },
};

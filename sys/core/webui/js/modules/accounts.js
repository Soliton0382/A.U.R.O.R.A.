// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ☁️ Cloud accounts (ROADMAP 106; owner, 2026-10-15: «più facile la gestione degli account per user o per enviroment…
// da cli voglio che si acceda il minimo possibile»): every user sees what their calls use, adds their own account — a
// Claude subscription signed in from here (the link, then the code pasted back: no terminal) or a provider's key; the
// admin adds the shared ones and chooses the policy, in plain words.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderServices } from "./accounts_services.js";
import { settingsForm } from "./settings_form.js";

export default {
  id: "accounts",
  icon: "☁️",
  title: "nav.accounts",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="acc.title"></h2><p class="muted" data-i18n="acc.hint"></p>
      <div class="acc-policy"></div><div class="acc-list"></div><div class="acc-svc"></div><div class="acc-add"></div>
      <div class="acc-cloud-out"></div>`;
    apply(root);
    this.policyBox = root.querySelector(".acc-policy");
    this.list = root.querySelector(".acc-list");
    this.addBox = root.querySelector(".acc-add");
    this.svcBox = root.querySelector(".acc-svc");
    this.privacyBox = root.querySelector(".acc-cloud-out");
  },

  async enter() {
    try { this.d = await call("/v1/aurora/accounts"); }
    catch (e) { this.list.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
    LABELS = Object.fromEntries(this.d.providers.map((p) => [p.id, p.label]));
    this.drawPolicy();
    this.drawList();
    this.svcBox.replaceChildren(renderServices(this.d, () => this.enter()));
    this.drawAdd();
    // what leaves for the cloud, kept here since the «cloud» plugin went (owner, 2026-10-16: the page «è più completa»):
    // the words masked, the compression (SSCC, M41 and M223: no loss measured) and how much of each text it keeps
    if (this.d.admin) {
      this.privacyBox.replaceChildren(await settingsForm(["AURORA_CLOUD_MASK_WORDS", "AURORA_CLOUD_COMPRESSION", "AURORA_CLOUD_KEEP_PCT"],
        { title: `🔒 ${t("acc.cloud_out")}` }));
    }
  },

  drawPolicy() {
    const d = this.d;
    const box = el("section", "report acc-section");
    box.append(el("h3", "", t("acc.policy")));
    for (const p of d.policies) {
      const row = el("label", "acc-choice");
      const r = el("input");
      r.type = "radio";
      r.name = "acc-policy";
      r.checked = d.policy === p;
      r.disabled = !d.admin;
      r.addEventListener("change", async () => {
        try { await call("/v1/aurora/accounts/policy", { method: "PUT", body: JSON.stringify({ policy: p }) }); this.enter(); }
        catch (e) { alert(e.message); }
      });
      const txt = el("span");
      txt.append(el("strong", "", t(`acc.pol.${p}`)), el("small", "muted", t(`acc.pol.${p}.hint`)));
      row.append(r, txt);
      box.append(row);
    }
    if (!d.admin) box.append(el("p", "muted", t("acc.policy_admin")));
    this.policyBox.replaceChildren(box);
  },

  drawList() {
    const d = this.d;
    const rows = d.providers.map((p) => {
      const using = d.using[p.id];
      const acc = d.accounts.find((a) => a.id === using);
      if (using === "installation" && !p.ready) return el("li", "muted", `${name(p.id)}: ${t("acc.not_set")}`);
      const what = using === "installation" ? t(p.key ? "acc.installation_key" : "acc.installation_login") : acc
        ? `${acc.scope === "shared" ? t("acc.shared") : t("acc.own")}${acc.label ? ` · ${acc.label}` : ""}` : t("acc.none_local");
      return el("li", using ? "" : "muted", `${name(p.id)}: ${what}`);
    });
    const now = el("section", "report acc-section");
    const ul = el("ul");
    ul.append(...rows);
    now.append(el("h3", "", t("acc.using")), ul);
    const mine = el("section", "report acc-section");
    mine.append(el("h3", "", t("acc.accounts")));
    if (!d.accounts.length) mine.append(el("p", "muted", t("acc.empty")));
    for (const a of d.accounts) mine.append(this.row(a));
    this.list.replaceChildren(now, mine);
  },

  row(a) {
    const r = el("div", "acc-row");
    const head = el("span", "", `${name(a.provider)} · ${a.scope === "shared" ? t("acc.shared") : `${t("acc.own")}${a.user && a.user !== this.d.me ? ` (${a.user})` : ""}`}`
      + `${a.label ? ` · ${a.label}` : ""}${a.key ? ` · 🔑 ${a.key}` : ""} · ${clock(new Date(a.created * 1000).toISOString())}`);
    const st = el("span", "muted", "…");
    r.append(head, st);
    call(`/v1/aurora/accounts/${a.id}/status`).then((s) => {
      st.textContent = s.logged_in ? `✅ ${t("acc.ready")}${s.email ? ` · ${s.email}` : ""}${s.plan ? ` · ${s.plan}` : ""}`
        : `⚠️ ${t(a.provider === "claude_code" ? "acc.not_signed" : "acc.no_key")}`;
      st.className = s.logged_in ? "ok" : "error";
      if (!s.logged_in && a.provider === "claude_code") r.append(this.signIn(a));
    }).catch(() => { st.textContent = ""; });
    const del = el("button", "danger", `🗑️ ${t("acc.remove")}`);
    del.addEventListener("click", async () => {
      if (!confirm(t("acc.remove_q"))) return;
      await call(`/v1/aurora/accounts/${a.id}`, { method: "DELETE" });
      this.enter();
    });
    r.append(del);
    return r;
  },

  // the Claude sign-in, from the page: the link to open, then the code it shows pasted back
  signIn(a) {
    const box = el("div", "acc-signin");
    const go = el("button", "approve", `🔐 ${t("acc.sign_in")}`);
    go.addEventListener("click", async () => {
      go.disabled = true;
      go.textContent = t("acc.opening");
      let url;
      try { url = (await call(`/v1/aurora/accounts/${a.id}/login`, { method: "POST" })).url; }
      catch (e) { go.disabled = false; go.textContent = `🔐 ${t("acc.sign_in")}`; box.append(el("p", "error", e.message)); return; }
      const link = el("a", "", t("acc.open_link"));
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener";
      const code = el("input");
      code.placeholder = t("acc.code");
      code.autocomplete = "off";
      const send = el("button", "approve", t("acc.send_code"));
      const out = el("span", "muted");
      send.addEventListener("click", async () => {
        send.disabled = true;
        out.textContent = t("acc.checking");
        try {
          const s = await call(`/v1/aurora/accounts/${a.id}/code`, { method: "POST", body: JSON.stringify({ code: code.value }) });
          if (s.logged_in) { this.enter(); return; }
          out.textContent = t("acc.code_refused");
        } catch (e) { out.textContent = e.message; }
        send.disabled = false;
      });
      box.replaceChildren(el("p", "", t("acc.steps")), link, code, send, out);
    });
    box.append(go);
    return box;
  },

  drawAdd() {
    const d = this.d;
    const box = el("section", "report acc-section");
    box.append(el("h3", "", t("acc.add")));
    const prov = el("select");
    for (const p of d.providers) { const o = el("option", "", name(p.id)); o.value = p.id; prov.append(o); }
    const scope = el("select");
    for (const s of d.admin ? ["shared", "user"] : ["user"]) {
      const o = el("option", "", t(s === "shared" ? "acc.add_shared" : "acc.add_own"));
      o.value = s;
      scope.append(o);
    }
    const label = el("input");
    label.placeholder = t("acc.label");
    const key = el("input");
    key.type = "password";
    key.autocomplete = "off";
    key.placeholder = t("acc.key");
    const note = el("small", "muted");
    const sync = () => {
      const p = d.providers.find((x) => x.id === prov.value);
      key.hidden = !p.key;
      note.textContent = t(p.key ? "acc.key_note" : "acc.claude_note");
    };
    prov.addEventListener("change", sync);
    sync();
    const go = el("button", "approve", t("acc.add_go"));
    go.addEventListener("click", async () => {
      try {
        await call("/v1/aurora/accounts", { method: "POST", body: JSON.stringify({ provider: prov.value, scope: scope.value, label: label.value, key: key.value }) });
        this.enter();
      } catch (e) { note.textContent = e.message; note.className = "error"; }
    });
    const form = el("div", "acc-form");
    form.append(prov, scope, label, key, go);
    box.append(form, note, el("p", "muted", t("acc.privacy")));
    this.addBox.replaceChildren(box);
  },
};

const NAMES = { anthropic: "Anthropic API", openai: "OpenAI", google: "Google",
  xai: "xAI", mistral: "Mistral", openrouter: "OpenRouter", custom: "Custom" };
let LABELS = {};                                 // the services of one's own: their names, from the page's data
const name = (id) => (id === "claude_code" ? t("acc.claude_sub") : NAMES[id] || LABELS[id] || id);

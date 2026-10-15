// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔌 The house's firewalls (owner, 2026-10-16: «uno imposta lì i firewall, può scegliere tutti quelli che vuole…
// impostare quello che serve, le guide… e una volta confermato il collegamento la suite security comincia a
// funzionare»): one card each — kind, address, user and password (on OPNsense the API key and its secret), the
// blocking group, the official guides (filled in, a pasted link wins), whether it receives the blocks; «Collega» logs
// in, makes the group, indexes the guides, and only then the firewall counts. The admin's.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { pluginSlot } from "./plugin_slot.js";

const GUIDES = ["manual", "api", "syslog"];

function field(label, input, wide = false) {
  const row = el("label", `fwl-field${wide ? " wide" : ""}`);
  row.append(el("span", "", label), input);
  return row;
}

function check(label, input) {                         // a checkbox beside its words
  const row = el("label", "fwl-check");
  row.append(input, el("span", "", label));
  return row;
}

function input(value, type = "text") {
  const i = el("input");
  i.type = type;
  i.value = value ?? "";
  return i;
}

export default {
  id: "firewalls",
  icon: "🔌",
  title: "nav.sec.firewalls",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.sec.firewalls"></h2><p class="muted" data-i18n="fwl.hint"></p>
      <div class="fwl-list"></div><div class="appr-actions"><button class="fwl-add" data-i18n="fwl.add"></button></div>`;
    root.querySelector("h2")?.after(pluginSlot("firewalls"));   // its plugins, configured here
    apply(root);
    this.root = root;
    root.querySelector(".fwl-add").addEventListener("click", () => this.card({ id: "new", kind: "pfsense", name: "",
      url: "", user: "", verify_tls: true, block_group: "Aurora-Blocked", blocks: true, guides: {} }, true));
  },

  async enter() {
    let d;
    try { d = await call("/v1/aurora/security/firewalls"); } catch (e) { this.root.querySelector(".fwl-list").textContent = e.message; return; }
    this.kinds = d.kinds;
    const list = this.root.querySelector(".fwl-list");
    list.replaceChildren();
    if (!d.items.length) list.append(el("p", "muted", t("fwl.empty")));
    for (const it of d.items) this.card(it, false);
  },

  card(it, open) {
    const box = el("section", "report fwl-card");
    const state = it.confirmed ? `✅ ${t("fwl.connected")}` : it.error ? `❌ ${it.error}` : `⚪ ${t("fwl.not_connected")}`;
    const head = el("div", "fwl-head");
    head.append(el("strong", "", it.name || t("fwl.new")), el("span", "fwl-kind", it.kind),
      el("span", it.confirmed ? "ok" : it.error ? "bad" : "muted", state));
    box.append(head);
    if (it.id !== "new") {                              // what it is, in one line, before any form
      const facts = [it.url, `${t("fwl.group")}: ${it.block_group || "—"}`,
        it.blocks !== false ? `⛔ ${t("fwl.blocks")}` : `⏸️ ${t("fwl.no_blocks")}`];
      if (it.indexed && it.indexed.passages) facts.push(t("fwl.indexed", { n: it.indexed.passages }));
      box.append(el("p", "muted fwl-facts", facts.filter(Boolean).join(" · ")));
    }
    const form = el("div", "fwl-form");
    form.hidden = !open;
    const kind = el("select");
    for (const k of this.kinds || []) kind.append(new Option(k.kind, k.kind));
    kind.value = it.kind;
    const name = input(it.name), url = input(it.url), user = input(it.user), pass = input("", "password");
    url.placeholder = "https://192.0.2.1:443";
    pass.placeholder = it.has_password ? t("fwl.pass_kept") : "";
    const group = input(it.block_group), tls = input("", "checkbox"), blocks = input("", "checkbox");
    tls.checked = !!it.verify_tls;
    blocks.checked = it.blocks !== false;
    const guides = Object.fromEntries(GUIDES.map((g) => [g, input((it.guides || {})[g])]));
    const userLabel = () => {
      const k = (this.kinds || []).find((x) => x.kind === kind.value) || {};
      userRow.firstChild.textContent = t(k.user_is_key ? "fwl.key" : "fwl.user");
      passRow.firstChild.textContent = t(k.user_is_key ? "fwl.secret" : "fwl.password");
      note.textContent = t(`fwl.need.${kind.value}`);
      for (const g of GUIDES) if (!guides[g].value || it.id === "new") guides[g].value = (k.docs || {})[g] || guides[g].value;
    };
    const userRow = field("", user), passRow = field("", pass), note = el("p", "muted fwl-need");
    const grid = el("div", "fwl-grid");
    grid.append(field(t("fwl.name"), name), field(t("fwl.kind"), kind), field(t("fwl.url"), url, true), userRow, passRow,
      field(t("fwl.group"), group));
    const checks = el("div", "fwl-checks");
    checks.append(check(t("fwl.tls"), tls), check(t("fwl.blocks"), blocks));
    const docs = el("fieldset", "fwl-guides");
    docs.append(el("legend", "", t("fwl.guides")), el("p", "muted", t("fwl.guides_hint")),
      ...GUIDES.map((g) => field(t(`fwl.guide.${g}`), guides[g], true)));
    form.append(note, grid, checks, docs);
    kind.addEventListener("change", userLabel);
    userLabel();
    const out = el("span", "muted");
    const save = el("button", "approve", `💾 ${t("fwl.save")}`);
    const connect = el("button", "", `🔌 ${t("fwl.connect")}`);
    const edit = el("button", "", `✏️ ${t("fwl.edit")}`);
    edit.addEventListener("click", () => { form.hidden = !form.hidden; });
    const body = () => ({ name: name.value, kind: kind.value, url: url.value, user: user.value, block_group: group.value,
      verify_tls: tls.checked, blocks: blocks.checked, password: pass.value,
      ...Object.fromEntries(GUIDES.map((g) => [g, guides[g].value])) });
    save.addEventListener("click", async () => {
      out.textContent = "…";
      try {
        const r = await call(`/v1/aurora/security/firewalls/${it.id}`, { method: "PUT", body: JSON.stringify(body()) });
        out.textContent = r.restart ? t("fwl.saved_restart") : t("fwl.saved");
        it.id = r.id;
        this.enter();
      } catch (e) { out.textContent = e.message; }
    });
    connect.addEventListener("click", async () => {
      out.textContent = t("fwl.connecting");
      try {
        const r = await call(`/v1/aurora/security/firewalls/${it.id}/connect`, { method: "POST" });
        out.textContent = r.ok ? t("fwl.connected_ok") : `❌ ${r.error}`;
        bus.emit("plugins");                            // the security pages show once a firewall is connected
        this.enter();
      } catch (e) { out.textContent = e.message; }
    });
    edit.addEventListener("click", () => { edit.classList.toggle("on", !form.hidden); });
    const actions = el("div", "appr-actions fwl-actions");
    actions.append(...(it.id === "new" ? [] : [edit, connect]));
    if (it.id !== "main" && it.id !== "new") {
      const del = el("button", "danger", `🗑️ ${t("fwl.remove")}`);
      del.addEventListener("click", async () => {
        if (!confirm(t("fwl.remove_q", { name: it.name || it.kind }))) return;
        try { await call(`/v1/aurora/security/firewalls/${it.id}`, { method: "DELETE" }); this.enter(); } catch (e) { alert(e.message); }
      });
      actions.append(del);
    }
    const saveRow = el("div", "appr-actions");
    saveRow.append(save);
    form.append(saveRow);
    box.append(actions, form, out);
    this.root.querySelector(".fwl-list").append(box);
  },
};

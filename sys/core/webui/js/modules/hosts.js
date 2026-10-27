// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🖧 Server e computer in ⚙️ Sistema (owner, 2026-10-28: «aggiungere anche altri tipi di device, come computer o server
// in modalità ssh (con procedura guidata su come fare, come creare lo script di shutdown o restart sulla macchina
// target, la chiave… e dove)»): one card each — tried with Aurora's key, restarted or shut down on a click, and its own
// «shut down with the UPS» tick; 🧙 the guided steps for the target, the user filled in, each command to copy.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";

function input(value, type = "text", ph = "") {
  const i = el("input");
  i.type = type;
  i.value = value ?? "";
  i.placeholder = ph;
  return i;
}

function copyBlock(text) {                             // a command with its 📋
  const box = el("div", "hst-cmd");
  const pre = el("pre", "", text);
  const b = el("button", "", "📋");
  b.type = "button";
  b.title = t("hst.copy");
  b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); b.textContent = "✅"; } catch { b.textContent = "⚠️"; }
    setTimeout(() => { b.textContent = "📋"; }, 1500);
  });
  box.append(pre, b);
  return box;
}

export default {
  id: "hosts",
  icon: "🖧",
  title: "nav.hosts",
  adminOnly: true,

  mount(root, ctx) {
    this.root = root;
    this.ctx = ctx;
    root.classList.add("page");
    useCss("/static/css/hosts.css");
    root.innerHTML = `<h2 data-i18n="nav.hosts"></h2><p class="muted" data-i18n="hst.hint"></p>
      <div class="hst-list"></div><div class="appr-actions"><button class="hst-add" data-i18n="hst.add"></button></div>`;
    apply(root);
    root.querySelector(".hst-add").addEventListener("click", () =>
      this.card({ id: "new", name: "", host: "", user: "", port: "22", os: "linux", ups_off: false }, true));
  },

  async enter() {
    const list = this.root.querySelector(".hst-list");
    try { this.data = await call("/v1/aurora/power/hosts"); }
    catch (e) { list.replaceChildren(el("p", "error", e.message)); return; }
    list.replaceChildren();
    if (!this.data.items.length) list.append(el("p", "muted", t("hst.empty")));
    for (const it of this.data.items) this.card(it, false);
  },

  card(it, open) {
    const box = el("section", "report hst-card");
    const head = el("div", "hst-head");
    const state = it.tested ? `✅ ${t("hst.tested")}` : it.tested === false ? `❌ ${t("hst.failed")}` : `⚪ ${t("hst.untested")}`;
    head.append(el("strong", "", it.name || t("hst.new")), el("span", "muted", it.id === "new" ? "" : `${it.user}@${it.host}:${it.port} · ${it.os}`),
      el("span", it.tested ? "ok" : it.tested === false ? "bad" : "muted", state));
    if (it.ups_off) head.append(el("span", "muted", `🔋 ${t("fwl.ups_on")}`));
    box.append(head);
    const out = el("p", "muted hst-out");
    const form = el("div", "hst-form");
    form.hidden = !open;
    const name = input(it.name, "text", t("hst.name_ph")), host = input(it.host, "text", "192.168.1.50");
    const user = input(it.user, "text", t("hst.user_ph")), port = input(it.port, "text", "22");
    const os = el("select");
    for (const o of ["linux", "macos"]) os.append(new Option(t(`hst.os.${o}`), o));
    os.value = it.os || "linux";
    const ups = this.data?.ups || {}, upsOn = ups.mode && ups.mode !== "off" && ups.servers;
    const upsOff = input("", "checkbox");
    upsOff.checked = !!it.ups_off;
    upsOff.disabled = !upsOn;
    const limits = upsOn ? t("fwl.ups_limits", { charge: ups.charge_min, min: Math.round(ups.runtime_min / 60) }) : t("fwl.ups_none");
    const upsRow = el("label", "fwl-check");
    const toUps = el("button", "", `🔋 ${t("fwl.ups_settings")}`);
    toUps.type = "button";
    toUps.addEventListener("click", () => this.ctx?.show("ups"));
    upsRow.append(upsOff, el("span", "", `🔋 ${t("fwl.ups_off")} (${limits})`), toUps);
    const grid = el("div", "hst-grid");
    for (const [label, field] of [["hst.name", name], ["hst.host", host], ["hst.user", user], ["hst.port", port], ["hst.os", os]]) {
      const l = el("label", "fwl-field");
      l.append(el("span", "", t(label)), field);
      grid.append(l);
    }
    const save = el("button", "approve", `💾 ${t("fwl.save")}`);
    save.addEventListener("click", async () => {
      out.textContent = "…";
      try {
        const r = await call(`/v1/aurora/power/hosts/${it.id}`, { method: "PUT", body: JSON.stringify({
          name: name.value, host: host.value, user: user.value, port: port.value, os: os.value, ups_off: upsOff.checked }) });
        await this.enter();
        if (it.id === "new") this.guide(r);             // a new machine: straight to its guided steps
      } catch (e) { out.textContent = e.message; }
    });
    form.append(grid, upsRow, save);
    const actions = el("div", "appr-actions");
    if (it.id !== "new") {
      const act = (label, action, ask) => {
        const b = el("button", action === "shutdown" ? "danger" : "", label);
        b.addEventListener("click", async () => {
          if (ask && !confirm(t(ask, { name: it.name }))) return;
          out.textContent = "…";
          try {
            const r = await call(`/v1/aurora/power/hosts/${it.id}/${action}`, { method: "POST" });
            out.textContent = r.ok ? `✅ ${t(`hst.done.${action}`)}` : `❌ ${r.detail || ""}`;
            if (action === "test") this.enter();
          } catch (e) { out.textContent = e.message; }
        });
        return b;
      };
      const guide = el("button", "", `🧙 ${t("hst.guide")}`);
      guide.addEventListener("click", () => this.guide(it));
      const edit = el("button", "", `✏️ ${t("fwl.edit")}`);
      edit.addEventListener("click", () => { form.hidden = !form.hidden; });
      const del = el("button", "danger", `🗑️ ${t("fwl.remove")}`);
      del.addEventListener("click", async () => {
        if (!confirm(t("fwl.remove_q", { name: it.name }))) return;
        try { await call(`/v1/aurora/power/hosts/${it.id}`, { method: "DELETE" }); this.enter(); } catch (e) { out.textContent = e.message; }
      });
      actions.append(guide, act(`🔌 ${t("hst.test")}`, "test"), act(`↻ ${t("hst.restart")}`, "restart", "hst.ask.restart"),
        act(`⏻ ${t("hst.shutdown")}`, "shutdown", "hst.ask.shutdown"), edit, del);
    }
    box.append(actions, form, out);
    if (it.id === "new") this.root.querySelector(".hst-list").prepend(box);
    else this.root.querySelector(".hst-list").append(box);
  },

  async guide(it) {                                    // the steps for the target, in a dialog
    let s;
    try { s = await call(`/v1/aurora/power/hosts/${it.id}/setup`); } catch (e) { alert(e.message); return; }
    const dlg = el("dialog", "hst-guide");
    const close = el("button", "", "✕");
    close.addEventListener("click", () => dlg.close());
    dlg.append(close, el("h3", "", `🧙 ${t("hst.guide")} — ${it.name}`), el("p", "muted", t("hst.g.intro", { user: it.user, host: it.host })));
    const steps = [["hst.g.script", s.commands[0], s.commands[1]], ["hst.g.sudo", s.commands[2]], ["hst.g.key", s.commands[3]]];
    steps.forEach(([k, ...cmds], i) => {
      dlg.append(el("h4", "", `${i + 1}. ${t(`${k}.title`)}`), el("p", "", t(`${k}.text`, { path: s.path, user: it.user })),
        ...cmds.map(copyBlock));
    });
    dlg.append(el("h4", "", `4. ${t("hst.g.test.title")}`), el("p", "", t("hst.g.test.text")),
      el("details", "", ""));
    const more = dlg.lastChild;
    more.append(el("summary", "", t("hst.g.more")), el("p", "muted", t("hst.g.why")), copyBlock(s.script),
      copyBlock(s.sudoers), copyBlock(s.authorized_keys));
    const test = el("button", "approve", `🔌 ${t("hst.test")}`);
    const res = el("span", "muted");
    test.addEventListener("click", async () => {
      res.textContent = "…";
      try {
        const r = await call(`/v1/aurora/power/hosts/${it.id}/test`, { method: "POST" });
        res.textContent = r.ok ? `✅ ${t("hst.done.test")}` : `❌ ${r.detail || ""}`;
        this.enter();
      } catch (e) { res.textContent = e.message; }
    });
    const row = el("div", "appr-actions");
    row.append(test, res);
    dlg.append(row);
    document.body.append(dlg);
    dlg.addEventListener("close", () => dlg.remove());
    dlg.showModal();
  },
};

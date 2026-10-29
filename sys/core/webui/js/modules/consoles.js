// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🖥️ Pannelli dei dispositivi (owner, 2026-10-28: «una pagina dove posso aggiungere tutte le pagine di gestione web dei
// miei device… il firewall, il nas… cliccandoci su posso accedere alla pagina»): each user's own tiles, by group; a
// click opens the device's page in a new tab; ✏️ changes one, 🗑️ removes it; the form adds or saves.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { iconPicker } from "../icon_picker.js";

// the icon: a button that opens the icons' window (icon_picker.js; owner, 28 Oct)

export default {
  id: "consoles",
  icon: "🖥️",
  title: "nav.consoles",

  mount(root) {
    this.root = root;
    root.classList.add("page");
    useCss("/static/css/consoles.css");
    root.innerHTML = `<h2 data-i18n="nav.consoles"></h2><p class="muted" data-i18n="con.hint"></p>
      <div class="con-groups"></div>
      <h3 class="setting-cat con-form-title" data-i18n="con.add"></h3>
      <form class="con-form">
        <input name="icon" maxlength="8" data-i18n-placeholder="con.icon">
        <input name="name" maxlength="60" required data-i18n-placeholder="con.name">
        <input name="url" maxlength="500" required data-i18n-placeholder="con.url">
        <input name="group" maxlength="40" list="con-group-list" data-i18n-placeholder="con.group">
        <datalist id="con-group-list"></datalist>
        <input name="note" maxlength="200" data-i18n-placeholder="con.note">
        <div class="appr-actions"><button class="approve" type="submit" data-i18n="con.save"></button>
          <button type="button" class="con-cancel" hidden data-i18n="con.cancel"></button><span class="muted con-out"></span></div>
      </form>`;
    apply(root);
    this.form = root.querySelector(".con-form");
    this.picker = iconPicker(this.form.elements.icon);
    this.out = root.querySelector(".con-out");
    this.cancel = root.querySelector(".con-cancel");
    this.cancel.addEventListener("click", () => this.edit(null));
    this.form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const body = Object.fromEntries(new FormData(this.form));
      try {
        await call(this.editing ? `/v1/aurora/consoles/${this.editing}` : "/v1/aurora/consoles",
          { method: this.editing ? "PUT" : "POST", body: JSON.stringify(body) });
        this.edit(null);
        this.enter();
      } catch (e) { this.out.textContent = t("ev.error", { m: e.message }); }
    });
  },

  edit(item) {                                       // the form fills with a tile to change, or empties
    this.editing = item?.id || null;
    for (const f of ["icon", "name", "url", "group", "note"]) this.form.elements[f].value = item?.[f] || "";
    this.picker.set(item?.icon || "");
    this.root.querySelector(".con-form-title").textContent = t(item ? "con.edit" : "con.add");
    this.cancel.hidden = !item;
    this.out.textContent = "";
    if (item) this.form.scrollIntoView({ behavior: "smooth" });
  },

  async enter() {
    const box = this.root.querySelector(".con-groups");
    let items;
    try { items = await call("/v1/aurora/consoles"); }
    catch (e) { box.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
    const groups = new Map();
    for (const it of items) {
      const g = it.group || t("con.other");
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(it);
    }
    this.root.querySelector("#con-group-list").replaceChildren(
      ...[...groups.keys()].map((g) => Object.assign(el("option"), { value: g })));
    if (!items.length) { box.replaceChildren(el("p", "muted", t("con.empty"))); return; }
    box.replaceChildren(...[...groups].map(([name, list]) => {
      const sec = el("section", "con-group");
      if (groups.size > 1) sec.append(el("h3", "setting-cat", name));
      const grid = el("div", "con-grid");
      for (const it of list) {
        const tile = el("div", "con-tile");
        const a = Object.assign(el("a", "con-link"), { href: it.url, target: "_blank", rel: "noopener noreferrer" });
        a.append(el("span", "con-icon", it.icon || "🖥️"), el("span", "con-name", it.name),
          el("span", "con-url muted", it.url.replace(/^https?:\/\//, "")));
        if (it.note) a.append(el("span", "con-note muted", it.note));
        const tools = el("div", "con-tools");
        const ed = el("button", "", "✏️");
        ed.title = t("con.edit");
        ed.addEventListener("click", () => this.edit(it));
        const del = el("button", "", "🗑️");
        del.title = t("con.delete");
        del.addEventListener("click", async () => {
          if (!confirm(t("con.confirm", { name: it.name }))) return;
          try { await call(`/v1/aurora/consoles/${it.id}`, { method: "DELETE" }); this.enter(); }
          catch (e) { this.out.textContent = t("ev.error", { m: e.message }); }
        });
        tools.append(ed, del);
        tile.append(a, tools);
        grid.append(tile);
      }
      sec.append(grid);
      return sec;
    }));
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💶 Spese (owner, 2026-10-16: «expenses… tanto vale averlo assieme ai menù in vita»): the month by category with the
// budgets passed, and the latest spendings, from the expenses plugin's read-only tools; its settings at the top. A
// spending is recorded by telling Aurora («ho speso 45 € di benzina»), as before.
import { call } from "../api.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { pluginSlot } from "./plugin_slot.js";

async function read(tool, args = {}) {
  const r = await call(`/v1/aurora/plugins/expenses/try/${tool}`, { method: "POST", body: JSON.stringify(args) });
  return String(r.text || "");
}

export default {
  id: "expenses",
  icon: "💶",
  title: "nav.expenses",
  plugin: "expenses",                 // in the menu only when that plugin is on

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.expenses"></h2><p class="muted" data-i18n="exp.hint"></p>
      <h3 class="setting-cat" data-i18n="exp.month"></h3><div class="report exp-summary"></div>
      <h3 class="setting-cat" data-i18n="exp.latest"></h3><div class="report exp-list"></div>`;
    root.querySelector("h2")?.after(pluginSlot("expenses"));   // its plugin, configured here
    apply(root);
    this.root = root;
  },

  async enter() {
    for (const [box, tool, args] of [[".exp-summary", "expense_summary", {}], [".exp-list", "expense_list", { limit: 20 }]]) {
      const target = this.root.querySelector(box);
      try { target.replaceChildren(renderMarkdown(await read(tool, args))); }
      catch (e) { target.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
    }
  },
};

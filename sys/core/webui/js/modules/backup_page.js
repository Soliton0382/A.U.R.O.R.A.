// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💾 Backup and restore, a page of its own (owner, 27 Nov: «non trovo la scheda di backup e ripristino»; N165 F3): the
// last copy and the next, 💾 now and 🔌 the NAS (backup.js), then ♻️ restore — Aurora's copies by parts and users,
// Evidentia's apart (restore.js). The machine's: the admin's only (api/modules' adminOnly).
import { backupRow, restoreBox } from "../backup.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { pluginSlot } from "./plugin_slot.js";

export default {
  id: "backup",
  icon: "💾",
  title: "nav.backup",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="bkp.title"></h2><p class="muted" data-i18n="bkp.hint"></p><div class="bkp-row"></div><div class="bkp-restore"></div>`;
    apply(root);
    root.querySelector("h2").after(pluginSlot("backup"));   // its plugins (backup, its files, its check), configured here
    this.row = root.querySelector(".bkp-row");
    this.restore = root.querySelector(".bkp-restore");
  },

  async enter() {
    const row = await backupRow();
    this.row.replaceChildren(row || el("p", "muted", t("bkp.none")));
    const box = restoreBox();
    this.restore.replaceChildren(box);
    box.open = true;                                   // the page is for this: open, read at once
    box.dispatchEvent(new Event("toggle"));
  },
};

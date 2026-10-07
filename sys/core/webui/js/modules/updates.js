// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Updates from GitHub: how Aurora updates (notify / auto / off), what a new version changes (the commit
// messages, what it touches), and "update now" — fast-forward, tests, back to the previous version on failure.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { restartPrompt } from "../restart.js";
import { autonomySlot } from "./autonomy_box.js";

export default {
  id: "updates",
  icon: "⬆️",
  title: "nav.updates",

  mount(root, ctx) {
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="update.title"></h2>
      <p class="muted" data-i18n="update.hint"></p>
      <div class="upd-mode"></div>
      <div class="upd-state"></div>`;
    root.querySelector("h2").after(autonomySlot("updates"));   // how free Aurora is, here (owner, 2026-10-08)
    apply(root);
    this.ctx = ctx;
    this.modeBox = root.querySelector(".upd-mode");
    this.box = root.querySelector(".upd-state");
  },

  async enter() { await this.show(await call("/v1/aurora/update")); },

  async show(u) {
    const mb = this.modeBox;
    mb.replaceChildren();
    const sel = el("select");
    for (const m of ["notify", "auto", "off"]) {
      const o = el("option", "", t(`update.m.${m}`));
      o.value = m;
      sel.append(o);
    }
    sel.value = u.mode;
    sel.addEventListener("change", async () => {
      const r = await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify({ AURORA_UPDATE_MODE: sel.value }) });
      await restartPrompt(r.restart);
    });
    const row = el("label", "plug-field");
    row.append(el("strong", "", t("update.mode.label")), sel);
    mb.append(row);

    const box = this.box;
    box.replaceChildren();
    const line = u.error ? t("update.error", { m: u.error })
      : u.checked ? (u.behind ? t("update.behind", { n: u.behind, to: u.there })
        : t("update.current", { at: clock(new Date(u.checked * 1000).toISOString()) }))
      : t("update.never");
    box.append(el("div", "ev", line));
    if (u.commits?.length) {
      box.append(el("h3", "setting-cat", t("update.changes")));
      for (const c of u.commits) {
        const item = el("div", "ev");
        item.append(el("strong", "", `${c.date.slice(0, 10)} · ${c.subject}`));
        if (c.body) item.append(el("div", "muted", c.body));
        box.append(item);
      }
      const notes = [];
      if (u.requirements) notes.push(t("update.n.req"));
      if (u.schema) notes.push(t("update.n.schema"));
      if (notes.length) box.append(el("div", "ev", notes.join(" · ")));
      if (u.protected?.length) box.append(el("div", "ev error", t("update.protected", { f: u.protected.join(", ") })));
    }
    const actions = el("div", "settings-actions");
    const check = el("button", "", t("update.check"));
    check.addEventListener("click", async () => {
      check.disabled = true;
      try { await this.show({ ...(await call("/v1/aurora/update/check", { method: "POST", body: "{}" })), mode: u.mode }); }
      catch (e) { box.append(el("div", "ev error", e.message)); check.disabled = false; }
    });
    actions.append(check);
    if (u.behind && !u.protected?.length) {
      const go = el("button", "approve", t("update.now"));
      go.addEventListener("click", async () => {
        go.disabled = true;
        try {
          const { run_id: id } = await call("/v1/aurora/update/apply", { method: "POST", body: "{}" });
          box.append(el("div", "ev", t("update.started", { id })));
        } catch (e) { box.append(el("div", "ev error", e.message)); go.disabled = false; }
      });
      actions.append(go);
    }
    box.append(actions);
  },
};

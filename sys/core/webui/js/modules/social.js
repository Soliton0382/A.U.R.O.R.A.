// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Social pages: connected platforms, the daily report with ideas, and the composer.
// "Share" on any Aurora answer (bus event "share") opens this page with drafts for every platform;
// the owner edits and clicks "Publish": that click is the confirmation (recorded as an approval).
import { call } from "../api.js";
import { bus } from "../bus.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";

export default {
  id: "social",
  icon: "📣",
  title: "nav.social",

  mount(root, ctx) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="social.title"></h2><p class="muted" data-i18n="social.hint"></p>
      <div class="platforms"></div>
      <h3 class="setting-cat" data-i18n="social.compose"></h3>
      <form class="import compose"><textarea rows="4" data-i18n-placeholder="social.topic"></textarea>
        <button type="submit" data-i18n="social.draft"></button></form>
      <div class="drafts"></div>
      <h3 class="setting-cat" data-i18n="social.report"></h3><div class="report"></div>`;
    apply(root);
    this.platforms = root.querySelector(".platforms");
    this.drafts = root.querySelector(".drafts");
    this.report = root.querySelector(".report");
    const input = root.querySelector("textarea");
    const go = root.querySelector(".compose button");
    const make = async (text) => {
      go.disabled = true;
      this.drafts.replaceChildren(el("p", "muted", t("social.working")));
      try {
        const { drafts } = await call("/v1/aurora/social/draft", { method: "POST", body: JSON.stringify({ text }) });
        this.drafts.replaceChildren(...drafts.map((d) => this.card(d)));
      } catch (e) { this.drafts.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
      go.disabled = false;
    };
    root.querySelector(".compose").addEventListener("submit", (ev) => { ev.preventDefault(); if (input.value.trim()) make(input.value.trim()); });
    bus.on("share", async ({ text }) => { await ctx.show("social"); input.value = text; make(text); });
  },

  card(d) {
    const c = el("div", "appr-card external");
    const area = el("textarea");
    area.rows = 6;
    area.value = d.text;
    const count = el("span", "muted");
    const upd = () => { count.textContent = `${area.value.length}/${d.max_chars}`; count.className = area.value.length > d.max_chars ? "error" : "muted"; };
    area.addEventListener("input", upd);
    upd();
    const pub = el("button", "approve big", `✔ ${t("social.publish", { p: d.label })}`);
    const out = el("span", "muted");
    pub.addEventListener("click", async () => {
      pub.disabled = true;
      try {
        await call("/v1/aurora/social/publish", { method: "POST", body: JSON.stringify({ plugin: d.plugin, text: area.value }) });
        out.textContent = t("social.sent");
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); pub.disabled = false; }
    });
    const row = el("div", "appr-actions");
    row.append(pub, count, out);
    c.append(el("div", "appr-head", d.label), area, row);
    return c;
  },

  async enter() {
    const s = await call("/v1/aurora/social");
    this.platforms.replaceChildren(...(s.platforms.length ? s.platforms.map((p) => {
      const r = el("div", "ev");
      r.append(el("span", `pill ${p.available ? "ok" : "warn"}`, p.available ? t("social.connected") : t("social.off")),
        el("strong", "", p.label), el("span", "muted", p.available ? "" : t("plug.state.missing", { keys: p.missing.join(", ") })));
      return r;
    }) : [el("p", "muted", t("social.none"))]));
    this.report.replaceChildren(s.last_report
      ? Object.assign(el("div", "report-text", `${clock(s.last_report.created_at)}\n\n${s.last_report.text}`))
      : el("p", "muted", t("social.noreport")));
  },
};

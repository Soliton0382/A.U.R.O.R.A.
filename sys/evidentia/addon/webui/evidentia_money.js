// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💰 Follow the money (owner, 27 Nov: «una cosa automatica che caccia, trova e correla… seguire i soldi»): what
// Evidentia correlated on the archive's money pages — the banks, the companies, the accounts seen the most (by their
// last four digits), who ties the most accounts, which companies move money through the same accounts — each with
// pages to open. Run again by itself after every folder read in; «Rifai» for the admin.
import { call } from "/static/js/api.js";
import { el, useCss } from "/static/js/dom.js";
import { t } from "/static/js/i18n.js";
import { API, citeButton } from "./evidentia_view.js";

const n = (x) => Number(x || 0).toLocaleString();
const day = (s) => (s ? new Date(s * 1000).toLocaleString() : "—");

function table(title, rows, cells) {
  const card = el("div", "evd-card evd-money");
  card.append(el("h3", "", title));
  if (!rows?.length) { card.append(el("p", "muted", t("evd.money_none"))); return card; }
  const list = el("div", "evd-money-rows");
  for (const r of rows) {
    const row = el("div", "evd-money-row");
    row.append(...cells(r).map((c) => (typeof c === "string" ? el("span", "", c) : c)));
    const see = el("span", "evd-money-see");
    for (const [doc, page] of r.see || []) see.append(citeButton({ doc, page }));
    row.append(see);
    list.append(row);
  }
  card.append(list);
  return card;
}

export default {
  id: "evd_money",
  icon: "💰",
  title: "nav.evd_money",
  adminOnly: true,

  mount(root) {
    root.classList.add("page");
    useCss("/static/addons/evidentia/evidentia.css");
    this.body = el("div");
    root.append(el("h2", "", `💰 ${t("nav.evd_money")}`), el("p", "muted", t("evd.money_hint")), this.body);
  },

  async enter() {
    this.body.replaceChildren(el("p", "muted", "…"));
    let r;
    try { r = await call(`${API}/money`); } catch (e) { this.body.replaceChildren(el("p", "muted", t("evd.off", { m: e.message }))); return; }
    const head = el("div", "ev");
    head.append(el("span", "muted", r.pages ? t("evd.money_line", { p: n(r.pages), n: n(r.nodes), t: n(r.ties), d: day(r.at) })
      : t("evd.money_never")));
    const again = el("button", "", r.running ? `⏳ ${t("evd.money_running")}` : `🔄 ${t("evd.money_again")}`);
    again.disabled = !!r.running;
    again.addEventListener("click", async () => {
      again.disabled = true;
      try { await call(`${API}/money/run`, { method: "POST", quiet: true }); again.textContent = `⏳ ${t("evd.money_running")}`; }
      catch (e) { again.textContent = e.message; }
      setTimeout(() => this.enter(), 15000);
    });
    head.append(again);
    const grid = el("div", "evd-grid");
    grid.append(
      table(`🏦 ${t("evd.money_banks")}`, r.banks, (x) => [x.name, t("evd.money_pages", { n: n(x.pages) })]),
      table(`🏢 ${t("evd.money_orgs")}`, r.orgs, (x) => [x.name, t("evd.money_pages", { n: n(x.pages) })]),
      table(`🔗 ${t("evd.money_shared")}`, r.org_shared, (x) => [`${x.a} ⇄ ${x.b}`, t("evd.money_accounts", { n: n(x.accounts) })]),
      table(`🕸️ ${t("evd.money_hubs")}`, r.hubs, (x) => [x.name, t("evd.money_accounts", { n: n(x.accounts) })]),
      table(`💳 ${t("evd.money_top_accounts")}`, r.accounts, (x) => [`${x.kind} ${x.account}`, t("evd.money_pages", { n: n(x.pages) })]),
      table(`👤 ${t("evd.money_public")}`, r.people, (x) => [x.name, t("evd.money_pages", { n: n(x.pages) })]));
    this.body.replaceChildren(head, grid, el("p", "muted", t("evd.money_rules")));
  },
};

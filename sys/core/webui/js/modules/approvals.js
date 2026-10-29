// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Approvals: what waits for the owner (approve ✅ / reject ❌) and the decisions already taken. Social posts are in
// the Social page (to approve and their history), Aurora's self-reviews and repairs in Reports (owner, 2026-10-05).
// The page of every decision (owner, 2026-10-09: «la pagina approvazioni racchiude … statistica e log»): what waits
// elsewhere with its button, the numbers of each kind, the whole log with each request's icon. In tabs, as the Models
// page (owner, 2026-10-20: «nella pagina risulta incasinato… le pagine come quelle dei modelli mi piace»): what waits,
// the log, the numbers; each request a short card — what and why, ✔ / ✘ — its technical part folded.
import { call } from "../api.js";
import { clock, el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { autonomySlot } from "./autonomy_box.js";

function badge(n) {
  const b = document.querySelector('#nav button[data-view="approvals"] .label');
  if (!b) return;
  b.dataset.count = n || "";
  b.classList.toggle("has-badge", n > 0);
}

function preview(a) {
  const box = el("div", "preview");
  const p = a.preview || {};
  if (a.kind === "code_change") {
    box.append(el("div", "", `${t("appr.files")}: ${(p.files || []).join(", ")}`),
      el("div", "", `${t("appr.tests")}: ${p.tests || "—"}`),
      el("div", "", `${t("appr.restart")}: ${(p.services || []).join(", ") || "—"}`));
    const d = el("details");
    d.append(el("summary", "", t("appr.diff")), el("pre", "diff", p.diff || ""));
    box.append(d);
  } else if (a.kind === "plugin_install") {         // a plugin the forge built: what it may do, and its code
    const m = p.manifest || {};
    box.append(el("div", "", `${t("appr.plugin_effects")}: ${Object.entries(m.effects || {}).map(([k, v]) => `${k} → ${v}`).join(", ") || "—"}`),
      el("div", "", `${t("appr.plugin_env")}: ${(m.env || []).join(", ") || "—"}`));
    const d = el("details");
    d.append(el("summary", "", "server.py"), el("pre", "diff", p["server.py"] || ""));
    box.append(d);
  } else {
    box.append(el("div", "", `${p.plugin}.${p.tool}`), el("pre", "", JSON.stringify(p.arguments || {}, null, 1)));
  }
  const fold = el("details", "appr-more");                 // folded: what and why first, the rest on a tap
  fold.append(el("summary", "", t("appr.details")), box);
  return fold;
}

// the social plugins' names (their posts live in the Social page)
export async function socialPlugins() {
  try { return new Set((await call("/v1/aurora/plugins")).filter((p) => p.social).map((p) => p.name)); } catch { return new Set(); }
}
export const isPost = (a, social) => social.has((a.action || a.preview || {}).plugin);

// one decision card: approve or reject; refresh() redraws the page it is in. `small`: the chat's own (a bubble)
export function approvalCard(a, refresh, small = false) {
  const c = el("div", `appr-card ${a.effect}${small ? " appr-small" : ""}`);
  c.append(el("div", "appr-head", `${a.icon || (a.kind === "code_change" ? "🧬" : "📤")} ${a.title}`),
    el("div", "muted", `${clock(a.created)} · ${t(`appr.effect.${a.effect}`)}`), el("p", "appr-why", a.purpose || ""), preview(a));
  const row = el("div", "appr-actions");
  const yes = el("button", "approve big", `✔ ${t("appr.approve")}`), no = el("button", "reject big", `✘ ${t("appr.reject")}`);
  const out = el("span", "muted");
  const decide = async (d) => {
    yes.disabled = no.disabled = true;
    try { await call(`/v1/aurora/approvals/${a.id}/${d}`, { method: "POST" }); out.textContent = t(`appr.done.${d}`); }
    catch (e) { out.textContent = t("ev.error", { m: e.message }); yes.disabled = no.disabled = false; }
    setTimeout(refresh, 1500);
  };
  yes.addEventListener("click", () => decide("approve"));
  no.addEventListener("click", () => decide("reject"));
  row.append(yes, no, out);
  c.append(row);
  return c;
}

// each kind's requests, decisions and the time the owner took
function statsTable(numbers) {
  const kinds = Object.entries(numbers || {});
  if (!kinds.length) return el("p", "muted", t("appr.none"));
  const table = el("table", "appr-table");
  const head = el("tr");
  for (const h of ["appr.s.kind", "appr.s.requested", "appr.s.approved", "appr.s.rejected", "appr.s.pending", "appr.s.minutes"]) head.append(el("th", "", t(h)));
  table.append(head);
  for (const [kind, k] of kinds) {
    const tr = el("tr");
    const rate = k.approved + k.rejected ? ` (${Math.round((100 * k.approved) / (k.approved + k.rejected))}%)` : "";
    for (const v of [t(`appr.k.${kind}`), k.requested, `${k.approved}${rate}`, k.rejected, k.pending,
      k.median_minutes === null ? "—" : k.median_minutes]) tr.append(el("td", "", String(v)));
    table.append(tr);
  }
  const wrap = el("div", "appr-table-wrap");                      // a phone scrolls the table, not the page
  wrap.append(table);
  return wrap;
}

// the chat's own: what waits for a yes, over the box, short (owner, 2026-10-20: «un semplice blob in chat potrebbe
// aiutare per questo tipo di approvazioni»); only this page's kind (a post waits in Social), redrawn when one is decided
export async function chatApprovals(box) {
  let pending = [];
  try { pending = (await call("/v1/aurora/approvals?status=pending")).filter((a) => a.view === "approvals"); } catch { /* offline */ }
  box.replaceChildren(...pending.slice(0, 3).map((a) => approvalCard(a, () => chatApprovals(box), true)),
    ...(pending.length > 3 ? [el("p", "muted", t("appr.more_in_page", { n: pending.length - 3 }))] : []));
  box.hidden = !pending.length;
  return pending.length;
}

export default {
  id: "approvals",
  icon: "🛎️",
  title: "nav.approvals",

  mount(root, ctx) {
    useCss("/static/css/agents.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="appr.title"></h2><p class="muted" data-i18n="appr.hint"></p>
      <div class="appr-elsewhere"></div>
      <div class="prj-tabs appr-tabs">${["wait", "log", "stats"].map((x, i) => `<button type="button" class="cat-chip${i ? "" : " on"}" data-tab="${x}"></button>`).join("")}</div>
      <div class="appr-tab" data-tab="wait"><div class="pending"></div></div>
      <div class="appr-tab" data-tab="log" hidden><div class="history"></div></div>
      <div class="appr-tab" data-tab="stats" hidden><div class="appr-stats"></div></div>`;
    root.querySelector("h2").after(autonomySlot("repairs"));   // how free Aurora is, here (owner, 2026-10-08)
    apply(root);
    this.pending = root.querySelector(".pending");
    this.history = root.querySelector(".history");
    this.elsewhere = root.querySelector(".appr-elsewhere");
    this.stats = root.querySelector(".appr-stats");
    this.tabs = root.querySelectorAll(".appr-tabs button");
    this.tabs.forEach((b) => b.addEventListener("click", () => {
      this.tabs.forEach((x) => x.classList.toggle("on", x === b));
      root.querySelectorAll(".appr-tab").forEach((p) => { p.hidden = p.dataset.tab !== b.dataset.tab; });
    }));
    this.ctx = ctx;
    const poll = async () => { try { badge((await call("/v1/aurora/approvals?status=pending")).length); } catch { /* offline */ } };
    poll();
    setInterval(poll, 15000);
  },

  async enter() {
    const [everything, numbers] = await Promise.all([call("/v1/aurora/approvals"), call("/v1/aurora/approvals/stats")]);
    const here = everything.filter((a) => a.view === "approvals");
    // what waits in its own page (posts in Social, an update in Updates…): a button to go there
    const away = new Map();
    for (const a of everything.filter((x) => x.status === "pending" && x.view !== "approvals")) {
      const p = away.get(a.view) || { icon: a.icon, n: 0 };
      p.n += 1;
      away.set(a.view, p);
    }
    this.elsewhere.replaceChildren(...[...away].map(([view, p]) => {
      const b = el("button", "approve big", `${p.icon} ${t("appr.waiting_in", { n: p.n, page: t(`nav.${view}`) })}`);
      b.addEventListener("click", () => this.ctx?.show(view));
      return b;
    }));
    this.stats.replaceChildren(statsTable(numbers));
    const all = here;
    const pending = all.filter((a) => a.status === "pending");
    badge(everything.filter((a) => a.status === "pending").length);
    this.pending.replaceChildren(...(pending.length ? pending.map((a) => approvalCard(a, () => this.enter())) : [el("p", "muted", t("appr.none"))]));
    const done = everything.filter((a) => a.status !== "pending");
    const [w, l, s] = this.tabs;
    w.textContent = `⏳ ${t("appr.tab.wait")}${pending.length ? ` (${pending.length})` : ""}`;
    l.textContent = `📜 ${t("appr.tab.log")}`;
    s.textContent = `📊 ${t("appr.tab.stats")}`;
    if (!done.length) this.history.replaceChildren(el("p", "muted", t("appr.none")));
    else this.history.replaceChildren(...done.slice(0, 60).map((a) => {
      const row = el("div", `ev appr-${a.status}`);
      row.append(el("span", "ic", { executed: "✅", failed: "⛔", rejected: "✖️", approved: "⏳" }[a.status] || "•"),
        el("span", "", `${a.icon || ""} ${clock(a.created)} · ${a.title} · ${t(`appr.status.${a.status}`)}`));
      if (a.result) {
        const d = el("details");
        d.append(el("summary", "", t("appr.result")), el("pre", "", JSON.stringify(a.result, null, 1).slice(0, 4000)));
        row.lastChild.append(d);
      }
      return row;
    }));
  },
};

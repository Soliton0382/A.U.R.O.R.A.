// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Approvals: what waits for the owner (approve ✅ / reject ❌) and the decisions already taken. Social posts are in
// the Social page (to approve and their history), Aurora's self-reviews and repairs in Reports (owner, 2026-10-05).
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
    d.open = true;
    box.append(d);
  } else {
    box.append(el("div", "", `${p.plugin}.${p.tool}`), el("pre", "", JSON.stringify(p.arguments || {}, null, 1)));
  }
  return box;
}

// the social plugins' names (their posts live in the Social page)
export async function socialPlugins() {
  try { return new Set((await call("/v1/aurora/plugins")).filter((p) => p.social).map((p) => p.name)); } catch { return new Set(); }
}
export const isPost = (a, social) => social.has((a.action || a.preview || {}).plugin);

// one decision card: approve or reject; refresh() redraws the page it is in
export function approvalCard(a, refresh) {
  const c = el("div", `appr-card ${a.effect}`);
  c.append(el("div", "appr-head", `${a.kind === "code_change" ? "🧬" : "📤"} ${a.title}`),
    el("div", "muted", `${clock(a.created)} · ${t(`appr.effect.${a.effect}`)}`), el("p", "", a.purpose || ""), preview(a));
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

export default {
  id: "approvals",
  icon: "🛎️",
  title: "nav.approvals",

  mount(root) {
    useCss("/static/css/agents.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="appr.title"></h2><p class="muted" data-i18n="appr.hint"></p>
      <div class="pending"></div><p class="muted appr-posts"></p>
      <h3 class="setting-cat" data-i18n="appr.history"></h3><div class="history"></div>`;
    root.querySelector("h2").after(autonomySlot("repairs"));   // how free Aurora is, here (owner, 2026-10-08)
    apply(root);
    this.pending = root.querySelector(".pending");
    this.history = root.querySelector(".history");
    this.posts = root.querySelector(".appr-posts");
    const poll = async () => { try { badge((await call("/v1/aurora/approvals?status=pending")).length); } catch { /* offline */ } };
    poll();
    setInterval(poll, 15000);
  },

  async enter() {
    const [everything, social] = await Promise.all([call("/v1/aurora/approvals"), socialPlugins()]);
    const all = everything.filter((a) => !isPost(a, social));      // the posts: in the Social page
    const posts = everything.filter((a) => a.status === "pending" && isPost(a, social)).length;
    this.posts.textContent = posts ? t("appr.posts_in_social", { n: posts }) : "";
    const pending = all.filter((a) => a.status === "pending");
    badge(pending.length + posts);
    this.pending.replaceChildren(...(pending.length ? pending.map((a) => approvalCard(a, () => this.enter())) : [el("p", "muted", t("appr.none"))]));
    this.history.replaceChildren(...all.filter((a) => a.status !== "pending").slice(0, 30).map((a) => {
      const row = el("div", `ev appr-${a.status}`);
      row.append(el("span", "ic", { executed: "✅", failed: "⛔", rejected: "✖️", approved: "⏳" }[a.status] || "•"),
        el("span", "", `${clock(a.created)} · ${a.title} · ${t(`appr.status.${a.status}`)}`));
      if (a.result) {
        const d = el("details");
        d.append(el("summary", "", t("appr.result")), el("pre", "", JSON.stringify(a.result, null, 1).slice(0, 4000)));
        row.lastChild.append(d);
      }
      return row;
    }));
  },
};

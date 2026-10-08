// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Social pages: connected platforms, the daily report with ideas, and the composer.
// "Share" on any Aurora answer (bus event "share") opens this page with drafts for every platform;
// the owner edits and clicks "Publish": that click is the confirmation (recorded as an approval).
import { call } from "../api.js";
import { bus } from "../bus.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { approvalCard, isPost, socialPlugins } from "./approvals.js";
import { videoSection } from "./social_video.js";
import { autonomySlot } from "./autonomy_box.js";

// every "Publish" of this page (owner, 2026-10-08: his name went out unchecked): the server checks the text first —
// private data it is sure of, a repeat of the last 7 days — and the owner confirms what it found, or goes back to edit
export async function publishPost(body) {
  const r = await call("/v1/aurora/social/publish", { method: "POST", body: JSON.stringify(body) });
  if (!r.confirm) return r;
  const lines = [];
  for (const f of r.confirm.privacy || []) lines.push(`• ${f.value} → ${f.replacement || "?"}`);
  if (r.confirm.privacy?.length) lines.unshift(t("social.confirm_privacy"));
  if (r.confirm.repeat) lines.push(t("social.confirm_repeat", { what: r.confirm.repeat }));
  if (!confirm(`${lines.join("\n")}\n\n${t("social.confirm_q")}`)) return null;
  return call("/v1/aurora/social/publish", { method: "POST", body: JSON.stringify({ ...body, confirmed: true }) });
}

// what a post would give away (owner, 2026-10-05): the names of private people, places, contacts, ids — read by the
// local model; each finding with its replacement, the sure ones ticked; "apply" rewrites the text, then onApply
export function privacyBox(getText, setText, onApply) {
  const box = el("div", "privacy-box");
  const check = el("button", "", t("social.privacy"));
  const out = el("div", "privacy-out");
  check.type = "button";
  check.addEventListener("click", async () => {
    check.disabled = true;
    out.replaceChildren(el("p", "muted", t("social.privacy_working")));
    try {
      const r = await call("/v1/aurora/social/check", { method: "POST", body: JSON.stringify({ text: getText() }) });
      if (!r.findings.length) { out.replaceChildren(el("p", "ok", t("social.privacy_clean"))); return; }
      const ticks = r.findings.map((f) => {
        const row = el("label", "privacy-row");
        const box = el("input");
        box.type = "checkbox";
        box.checked = f.sure;
        row.append(box, el("strong", "", f.value), el("span", "muted", ` (${t(`social.kind.${f.kind}`) || f.kind}) → `),
          el("span", "", f.replacement));
        return [box, f, row];
      });
      const go = el("button", "approve", t("social.privacy_apply"));
      go.type = "button";
      go.addEventListener("click", () => {
        let text = getText();
        for (const f of ticks.filter(([b]) => b.checked).map(([, f]) => f).sort((a, b) => b.value.length - a.value.length)) {
          text = text.split(f.value).join(f.replacement);
        }
        setText(text);
        out.replaceChildren(el("p", "ok", t("social.privacy_done")));
        onApply?.(text);
      });
      out.replaceChildren(el("p", "warn", t("social.privacy_found", { n: r.findings.length })), ...ticks.map(([, , row]) => row), go);
    } catch (e) { out.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); } finally { check.disabled = false; }
  });
  box.append(check, out);
  return box;
}

export default {
  id: "social",
  icon: "📣",
  title: "nav.social",
  plugin: "social",                 // in the menu only when that plugin is on (social: any platform connected)

  mount(root, ctx) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="social.title"></h2><p class="muted" data-i18n="social.hint"></p>
      <div class="platforms"></div>
      <h3 class="setting-cat" data-i18n="social.to_approve"></h3><div class="soc-pending"></div>
      <h3 class="setting-cat" data-i18n="social.compose"></h3>
      <form class="import compose"><textarea rows="4" data-i18n-placeholder="social.topic"></textarea>
        <button type="submit" data-i18n="social.draft"></button></form>
      <div class="drafts"></div>
      <h3 class="setting-cat" data-i18n="social.video.title"></h3><div class="soc-video"></div>
      <h3 class="setting-cat" data-i18n="social.report"></h3><div class="report"></div>
      <h3 class="setting-cat" data-i18n="social.history"></h3><div class="soc-history"></div>`;
    root.querySelector("h2").after(autonomySlot("social"));   // how free Aurora is, here (owner, 2026-10-08)
    apply(root);
    this.platforms = root.querySelector(".platforms");
    this.drafts = root.querySelector(".drafts");
    this.report = root.querySelector(".report");
    this.socPending = root.querySelector(".soc-pending");
    this.socHistory = root.querySelector(".soc-history");
    this.videos = videoSection(root.querySelector(".soc-video"));
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
    // a dream or a picture of Aurora's travels with its file name: the post carries the picture
    bus.on("share", async ({ text, picture }) => { await ctx.show("social"); this.picture = picture || null; input.value = text; make(text); });
    root.querySelector(".compose").addEventListener("input", () => { if (!input.value.trim()) this.picture = null; });
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
    const picture = d.photo ? this.picture : null;
    const pub = el("button", "approve big", `✔ ${t("social.publish", { p: d.label })}`);
    const out = el("span", "muted");
    pub.addEventListener("click", async () => {
      pub.disabled = true;
      try {
        const r = await publishPost({ plugin: d.plugin, text: area.value, ...(picture ? { picture } : {}) });
        if (!r) { pub.disabled = false; return; }
        out.textContent = t("social.sent");
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); pub.disabled = false; }
    });
    const drop = el("button", "reject", `🗑️ ${t("social.discard")}`);     // changed my mind: the draft goes away
    drop.type = "button";
    drop.addEventListener("click", () => c.remove());
    const row = el("div", "appr-actions");
    row.append(pub, drop, count, out);
    c.append(el("div", "appr-head", d.label));
    if (picture) { const img = el("img", "share-pic"); img.src = `/v1/aurora/images/${picture}`; img.alt = picture; c.append(img); }
    c.append(area, privacyBox(() => area.value, (v) => { area.value = v; upd(); }), row);
    return c;
  },

  // a post waiting for the owner, with the privacy check: "fix and publish" publishes the corrected text (that click is
  // the confirmation, as for a draft) and turns the original down
  pendingCard(a) {
    const c = approvalCard(a, () => this.loadPosts());
    const act = a.action || a.preview || {};
    const args = act.arguments || {};
    const field = "message" in args ? "message" : "text";
    let fixed = null;
    const fix = el("button", "approve", `✔ ${t("social.fix_publish")}`);
    fix.type = "button";
    fix.hidden = true;
    fix.addEventListener("click", async () => {
      fix.disabled = true;
      try {
        const r = await publishPost({ plugin: act.plugin, text: fixed, ...(args.picture ? { picture: args.picture } : {}) });
        if (!r) { fix.disabled = false; return; }
        await call(`/v1/aurora/approvals/${a.id}/reject`, { method: "POST" });
        setTimeout(() => this.loadPosts(), 1000);
      } catch (e) { fix.disabled = false; fix.textContent = t("ev.error", { m: e.message }); }
    });
    const preview = el("p", "privacy-fixed");
    c.insertBefore(privacyBox(() => fixed ?? String(args[field] || ""), (v) => { fixed = v; preview.textContent = v; },
      () => { fix.hidden = false; }), c.querySelector(".appr-actions"));
    c.insertBefore(preview, c.querySelector(".appr-actions"));
    c.querySelector(".appr-actions").prepend(fix);
    return c;
  },

  // the posts: those waiting for the owner, and every one published (by her click or by Aurora by herself)
  async loadPosts() {
    const [all, social] = await Promise.all([call("/v1/aurora/approvals"), socialPlugins()]);
    const posts = all.filter((a) => isPost(a, social));
    const pending = posts.filter((a) => a.status === "pending");
    this.socPending.replaceChildren(...(pending.length ? pending.map((a) => this.pendingCard(a))
      : [el("p", "muted", t("social.none_to_approve"))]));
    const done = posts.filter((a) => a.status !== "pending").slice(0, 50);
    this.socHistory.replaceChildren(...(done.length ? done.map((a) => {
      const args = (a.action || a.preview || {}).arguments || {};
      const d = el("details", "report");
      const icon = { executed: "✅", auto: "🤖", failed: "⛔", rejected: "✖️", approved: "⏳" }[a.status] || "•";
      d.append(el("summary", "", `${icon} ${clock(a.created)} · ${a.title} · ${t(`social.st.${a.status}`)}`));
      if (args.picture) { const img = el("img", "share-pic"); img.src = `/v1/aurora/images/${args.picture}`; img.alt = args.picture; img.loading = "lazy"; d.append(img); }
      if (args.video) d.append(el("p", "muted", `🎬 ${args.video}`));
      d.append(el("p", "", args.message || args.text || args.caption || args.title || ""));
      const id = /post id (\S+)/.exec(typeof a.result === "string" ? a.result : a.result?.text || "")?.[1];
      if (id && (a.action || {}).plugin === "facebook") {
        const link = el("a", "", t("social.open_post"));
        link.href = `https://www.facebook.com/${id}`; link.target = "_blank"; link.rel = "noopener noreferrer";
        d.append(link);
      }
      return d;
    }) : [el("p", "muted", t("social.no_history"))]));
  },

  async enter() {
    this.loadPosts().catch(() => {});
    this.videos.load();
    const s = await call("/v1/aurora/social");
    const on = s.platforms.filter((p) => p.available);       // only the platforms switched on and connected
    this.platforms.replaceChildren(...(on.length ? on.map((p) => {
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

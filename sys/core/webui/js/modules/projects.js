// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Projects: the local ones (folder tree, files, README, history, sandboxed page preview), the owner's GitHub
// repositories (stars, forks, issues; clone to browse them), a new project, and "ask Aurora" about one.
// Reading only here; writing goes through Aurora's "projects" plugin and the owner's approvals.
import { policyFields } from "./project_policy.js";
import { call } from "../api.js";
import { bus } from "../bus.js";
import { clock, el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { openProject } from "./project_page.js";
import { pluginSlot } from "./plugin_slot.js";

export default {
  id: "projects",
  icon: "📁",
  title: "nav.projects",
  plugin: "projects",                 // in the menu only when that plugin is on (social: any platform connected)

  mount(root) {
    useCss("/static/css/projects.css");
    useCss("/static/css/models_mode.css");                        // its cards: the Models page's look
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="prj.title"></h2><p class="muted" data-i18n="prj.hint"></p>
      <div class="prj-list">
        <div class="prj-tabs"><button type="button" class="cat-chip on" data-tab="local" data-i18n="prj.local"></button>
          <button type="button" class="cat-chip" data-tab="new" data-i18n="prj.tab_new"></button>
          <button type="button" class="cat-chip" data-tab="brief" data-i18n="prj.tab_brief"></button>
          <button type="button" class="cat-chip" data-tab="github" data-i18n="prj.github"></button></div>
        <div class="prj-tab" data-tab="github" hidden><p class="muted" data-i18n="prj.github_hint"></p><div class="prj-github"></div></div>
        <div class="prj-tab" data-tab="local"><p class="muted" data-i18n="prj.local_hint"></p><div class="prj-local prj-grid"></div></div>
        <div class="prj-tab" data-tab="brief" hidden><div class="mch-panel prj-panel"><h4 data-i18n="prj.brief"></h4>
        <p class="muted" data-i18n="prj.brief_hint"></p>
        <form class="import prj-brief">
          <input name="name" required pattern="[a-z0-9][a-z0-9._-]{0,63}" data-i18n-placeholder="prj.name">
          <textarea name="goal" rows="2" required data-i18n-placeholder="prj.b_goal"></textarea>
          <textarea name="reqs" rows="4" data-i18n-placeholder="prj.b_reqs"></textarea>
          <textarea name="tests" rows="3" required data-i18n-placeholder="prj.b_tests"></textarea>
          <textarea name="limits" rows="2" data-i18n-placeholder="prj.b_limits"></textarea>
          <button type="submit" class="approve" data-i18n="prj.b_go"></button></form></div></div>
        <div class="prj-tab" data-tab="new" hidden><div class="mch-panel prj-panel"><h4 data-i18n="prj.new"></h4>
        <form class="prj-new"><label><span data-i18n="prj.f_name"></span><input name="name" required pattern="[a-z0-9][a-z0-9._-]{0,63}" data-i18n-placeholder="prj.name"></label>
          <label><span data-i18n="prj.f_what"></span><input name="description" required data-i18n-placeholder="prj.description"></label>
          <label><span data-i18n="prj.f_license"></span><select name="license"><option>MIT</option><option>Apache-2.0</option><option>GPL-3.0</option><option>BSD-3-Clause</option></select></label>
          <label><span data-i18n="prj.f_language"></span><input name="language" value="Python" data-i18n-placeholder="prj.language"></label>
          <label class="prj-policy-new"><span data-i18n="prj.f_policy"></span></label>
          <div class="appr-actions"><button type="submit" class="approve" data-i18n="prj.create"></button><span class="muted out"></span></div></form></div></div>
      </div>
      <div class="prj-detail hidden"></div>`;
    root.querySelector("h2")?.after(pluginSlot("projects"));   // its plugins, configured here
    apply(root);
    this.root = root;
    this.local = root.querySelector(".prj-local");
    this.github = root.querySelector(".prj-github");
    this.list = root.querySelector(".prj-list");
    this.detail = root.querySelector(".prj-detail");
    // two tabs (owner, 2026-10-04): the local projects, where Aurora writes, tests and tries again; GitHub's
    root.querySelectorAll(".prj-tabs button").forEach((b) => b.addEventListener("click", () => {
      root.querySelectorAll(".prj-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      root.querySelectorAll(".prj-tab").forEach((p) => { p.hidden = p.dataset.tab !== b.dataset.tab; });
    }));
    // a project given to Aurora as a brief (owner, 2026-10-05): goal, requirements, acceptance tests, limits, and how
    // to work — she creates it, writes, runs the tests in her cage, iterates, commits, reports (and notifies)
    root.querySelector(".prj-brief").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const b = ev.target;
      const block = (k, v) => (v.trim() ? `${t(k)}\n${v.trim()}\n\n` : "");
      bus.emit("ask", { text: `${t("prj.b_title", { name: b.name.value.trim() })}\n\n${block("prj.b_goal_h", b.goal.value)}`
        + `${block("prj.b_reqs_h", b.reqs.value)}${block("prj.b_tests_h", b.tests.value)}`
        + `${block("prj.b_limits_h", b.limits.value || t("prj.b_limits_default"))}${t("prj.b_how", { name: b.name.value.trim() })}` });
    });
    const form = root.querySelector(".prj-new");
    form.querySelector(".prj-policy-new").append(...policyFields());   // how Aurora handles it, chosen now
    root.querySelector(".prj-tab[data-tab=new] h4").after(el("p", "muted", t("prj.new_hint")));
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const out = form.querySelector(".out");
      out.textContent = t("prj.working");
      try {
        await call("/v1/aurora/projects", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) });
        out.textContent = t("prj.created");
        form.reset();
        await this.refresh();
        root.querySelector(".prj-tabs [data-tab=local]").click();          // back to the cards, the new one there
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
  },

  async enter() { this.back(false); await this.refresh(); },

  async refresh() {
    const { projects, base } = await call("/v1/aurora/projects");
    this.base = base;
    this.names = new Set(projects.map((p) => p.name));
    this.local.replaceChildren(...(projects.length ? projects.map((p) => this.localCard(p)) : [el("p", "muted", t("prj.none", { base }))]));
    this.github.replaceChildren(el("p", "muted", t("prj.loading")));
    try {
      const g = await call("/v1/aurora/projects/github");
      if (!g.connected) { this.github.replaceChildren(el("p", "muted", t("prj.gh_off"))); return; }
      const grid = el("div", "prj-grid");
      grid.append(...g.repos.map((r) => this.repoCard(r)));
      this.github.replaceChildren(el("p", "muted", t("prj.gh_user", { login: g.login, n: g.repos.length })), grid,
        ...(g.error ? [el("p", "error", g.error)] : []), el("p", "muted", t("prj.gh_private")));
    } catch (e) { this.github.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
  },

  // a project as a card, the Models page's way: what it is, whether all is saved, how Aurora handles it
  localCard(p) {
    const c = el("button", "mch-card prj-card");
    c.type = "button";
    const head = el("div", "mch-head");
    head.append(el("strong", "", `📁 ${p.name}`));
    const pol = p.policy || { models: "cloud", publish: true };
    if (pol.models === "local") head.append(el("span", "mch-tag", "🔒"));
    if (!pol.publish) head.append(el("span", "mch-tag prj-never", "🚫"));
    // 🖼️ its cover (prj_cover): the realistic view's picture, the project's own, or its main code; else the emoji
    const cover = el("img", "prj-cover");
    Object.assign(cover, { loading: "lazy", alt: "", src: `/v1/aurora/projects/${p.name}/cover?v=${encodeURIComponent(p.last_commit?.date || "")}` });
    cover.addEventListener("error", () => cover.remove());
    c.append(cover, head, el("div", "mch-line prj-what", p.description || t("prj.no_readme")));
    // git's words in plain ones (owner, 2026-10-21: «non capisco quelle scritte verdi e gialle (pulito, modifiche)»)
    const saved = el("div", p.changes ? "prj-state warn" : "prj-state ok", p.changes ? t("prj.changes", { n: p.changes }) : t("prj.clean"));
    saved.title = t(p.changes ? "prj.changes_hint" : "prj.clean_hint");
    c.append(saved);
    if (p.last_commit) c.append(el("div", "muted prj-when", t("prj.last_saved", { at: clock(p.last_commit.date), what: p.last_commit.subject })));
    c.append(el("div", "mch-price", `${t(`prj.card_${pol.models}`)} · ${t(pol.publish ? "prj.card_pub" : "prj.card_never")}`
      + (p.remote ? " · 🐙 GitHub" : "")));
    c.addEventListener("click", () => this.open(p));
    return c;
  },

  // a GitHub repository as a card, like the local ones (owner, 2026-10-21): with its local copy it opens it; without,
  // it only shows what GitHub says — and its last 14 days of visits and clones
  repoCard(r) {
    const local = r.name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "");
    const mine = this.names.has(local);
    const c = el(mine ? "button" : "div", `mch-card prj-card${mine ? "" : " prj-remote"}`);
    if (mine) { c.type = "button"; c.addEventListener("click", () => this.open({ name: local })); }
    const head = el("div", "mch-head");
    head.append(el("strong", "", `🐙 ${r.name}`));
    if (r.private) head.append(el("span", "mch-tag", "🔒"));
    if (r.archived) head.append(el("span", "mch-tag", "📦"));
    // 🖼️ the local copy's cover when there is one; else a band with the repository's language (nothing is loaded
    // from GitHub: the page's pictures come from Aurora only)
    const band = el("div", "prj-cover prj-cover-gh", `🐙 ${r.language || "GitHub"}`);
    if (mine) {
      const img = el("img", "prj-cover");
      Object.assign(img, { loading: "lazy", alt: "", src: `/v1/aurora/projects/${local}/cover` });
      img.addEventListener("error", () => img.replaceWith(band));
      c.append(img);
    } else c.append(band);
    c.append(head, el("div", "mch-line prj-what", r.description || t("prj.no_readme")));
    const stats = el("div", "mch-stats");
    const stat = (label, value, small) => {
      const s2 = el("div", "mch-stat");
      s2.append(el("small", "", label), el("strong", "", value), el("small", "", small || ""));
      return s2;
    };
    const views = stat(t("prj.gh_views"), "…", t("prj.gh_14d"));
    const clones = stat(t("prj.gh_clones"), "…", t("prj.gh_14d"));
    stats.append(views, clones);
    c.append(stats, el("div", "prj-gh-line", `⭐ ${r.stargazers_count} · 🍴 ${r.forks_count} · 🐞 ${r.open_issues_count}`
      + (r.language ? ` · ${r.language}` : "")));
    if (r.pushed_at) c.append(el("div", "muted prj-when", t("prj.pushed", { at: clock(r.pushed_at) })));
    const foot = el("div", "mch-price prj-gh-foot");
    const a = el("a", "", t("prj.gh_open"));
    a.href = r.html_url; a.target = "_blank"; a.rel = "noopener noreferrer";
    a.addEventListener("click", (ev) => ev.stopPropagation());
    foot.append(mine ? el("span", "prj-state ok", t("prj.gh_local")) : el("span", "muted", t("prj.gh_only")), a);
    if (r.has_pages || r.homepage) {
      const w = el("a", "", "🌐");
      w.href = r.homepage || `https://${r.full_name.split("/")[0].toLowerCase()}.github.io/${r.name}/`;
      w.target = "_blank"; w.rel = "noopener noreferrer"; w.title = t("prj.site");
      w.addEventListener("click", (ev) => ev.stopPropagation());
      foot.append(w);
    }
    if (!mine) {
      const b = el("button", "", t("prj.clone"));
      b.addEventListener("click", async () => {
        b.disabled = true; b.textContent = t("prj.cloning");
        try {
          const { name } = await call("/v1/aurora/projects/clone", { method: "POST", body: JSON.stringify({ full_name: r.full_name }) });
          await this.refresh();
          this.open({ name });
        } catch (e) { b.textContent = t("ev.error", { m: e.message }); }
      });
      foot.append(b);
    }
    c.append(foot);
    call(`/v1/aurora/projects/github/${r.full_name}/traffic`).then((tr) => {
      const put = (box, v) => {
        box.querySelector("strong").textContent = v ? String(v.count) : "—";
        box.querySelectorAll("small")[1].textContent = v ? t("prj.gh_uniques", { n: v.uniques }) : t("prj.gh_none");
      };
      put(views, tr.views);
      put(clones, tr.clones);
      if (tr.why === "permission") stats.title = t("prj.gh_perm");
      if (tr.why === "permission") views.querySelectorAll("small")[1].textContent = clones.querySelectorAll("small")[1].textContent = t("prj.gh_perm_short");
    }).catch(() => { views.querySelector("strong").textContent = "—"; clones.querySelector("strong").textContent = "—"; });
    return c;
  },

  back(reload = true) {
    this.detail.classList.add("hidden");
    this.list.classList.remove("hidden");
    this.root.classList.remove("prj-open");
    this.detail.replaceChildren();
    if (reload) this.refresh();          // what changed inside (a save, Aurora's work) shown on the cards at once
  },

  // one project's page, in sections the Models page's way (project_page.js)
  open(p) {
    this.list.classList.add("hidden");
    this.detail.classList.remove("hidden");
    this.root.classList.add("prj-open");                 // the list's title, plugins and words step aside
    openProject(this.detail, p, { base: this.base, back: () => this.back() });
  },
};

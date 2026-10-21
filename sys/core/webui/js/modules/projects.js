// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Projects: the local ones (folder tree, files, README, history, sandboxed page preview), the owner's GitHub
// repositories (stars, forks, issues; clone to browse them), a new project, and "ask Aurora" about one.
// Reading only here; writing goes through Aurora's "projects" plugin and the owner's approvals.
import { policyBox, policyFields } from "./project_policy.js";
import { call } from "../api.js";
import { bus } from "../bus.js";
import { clock, el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { docsView, pdfPages } from "./project_docs.js";
import { planView } from "./project_plan.js";
import { terminalView } from "./project_term.js";
import { pluginSlot } from "./plugin_slot.js";

const kb = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);

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
    c.append(head, el("div", "mch-line prj-what", p.description || t("prj.no_readme")));
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
    this.detail.replaceChildren();
    if (reload) this.refresh();          // what changed inside (a save, Aurora's work) shown on the cards at once
  },

  async open(p) {
    const name = p.name;
    this.list.classList.add("hidden");
    this.detail.classList.remove("hidden");
    const d = this.detail;
    d.innerHTML = `
      <div class="ev prj-bar"><button class="back"></button><h3></h3>
        <button class="preview"></button><button class="term"></button><button class="history"></button><button class="reports"></button><button class="plan"></button><button class="docs"></button></div>
      <form class="prj-ask"><input data-i18n-placeholder="prj.ask_ph"><button type="submit" data-i18n="prj.ask"></button></form>
      <div class="prj-body"><div class="prj-tree"></div><div class="prj-view"></div></div>`;
    apply(d);
    d.querySelector("h3").textContent = `📁 ${name}`;
    policyBox(name).then((b) => d.querySelector("h3").after(b));
    // 💾 what «saved» means: the project's history (git commits) — said here, and done with one click
    const saveBox = el("span", "prj-save");
    const drawSave = (changes) => {
      const st = el("span", changes ? "prj-state warn" : "prj-state ok", changes ? t("prj.changes", { n: changes }) : t("prj.clean"));
      st.title = t(changes ? "prj.changes_hint" : "prj.clean_hint");
      const b = el("button", changes ? "approve" : "", t("prj.save"));
      b.title = t("prj.save_hint");
      b.disabled = !changes;
      b.addEventListener("click", async () => {
        b.disabled = true;
        try {
          await call(`/v1/aurora/projects/${name}/save`, { method: "POST", body: JSON.stringify({ message: prompt(t("prj.save_q"), "") || "" }) });
          drawSave(0);
        } catch (e) { b.textContent = t("ev.error", { m: e.message }); }
      });
      saveBox.replaceChildren(st, b);
    };
    drawSave(p.changes || 0);
    d.querySelector(".prj-bar").after(saveBox);
    d.querySelector(".back").textContent = t("prj.back");
    d.querySelector(".back").addEventListener("click", () => this.back());
    const view = d.querySelector(".prj-view");
    const treeBox = d.querySelector(".prj-tree");
    const preview = d.querySelector(".preview");
    preview.textContent = t("prj.preview");
    preview.addEventListener("click", async () => {
      try {
        const { url } = await call(`/v1/aurora/projects/${name}/preview`, { method: "POST", body: "{}" });
        const f = el("iframe", "prj-frame");
        f.setAttribute("sandbox", "allow-scripts allow-forms allow-popups");   // opaque origin: no cookie, no API
        f.setAttribute("referrerpolicy", "no-referrer");
        f.src = url;
        view.replaceChildren(el("p", "muted", t("prj.preview_note")), f);
      } catch (e) { view.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
    });
    // 🖥️ the project run in its cage (roadmap 75): a terminal, no network, only this folder
    const term = d.querySelector(".term");
    term.textContent = t("prj.term");
    term.addEventListener("click", () => view.replaceChildren(terminalView(name)));
    // 🏗️ the project carried by Aurora herself, step by step (ROADMAP 97)
    const plan = d.querySelector(".plan");
    plan.textContent = t("plan.button");
    plan.addEventListener("click", () => view.replaceChildren(planView(name)));
    // 📑 the documentation it must be ready for: blueprints, patents (ROADMAP 100), with «Procedi»
    const docs = d.querySelector(".docs");
    docs.textContent = t("docs.button");
    docs.addEventListener("click", () => view.replaceChildren(docsView(name, (path) => show(path))));
    // Aurora's reports on this project (owner, 2026-10-05): her considerations, beside the alerts and the chat
    const reportsBtn = d.querySelector(".reports");
    reportsBtn.textContent = t("prj.reports");
    reportsBtn.addEventListener("click", async () => {
      let items = [];
      try { items = await call(`/v1/aurora/projects/${name}/reports`); } catch (e) { view.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
      view.replaceChildren(el("h4", "", t("prj.reports")), ...(items.length ? items.map((r, i) => {
        const box = el("details", "report");
        box.open = i === 0;
        box.append(el("summary", "", `${clock(r.at)} · ${t("prj.report_meta", { steps: r.steps ?? "?", min: Math.round((r.seconds || 0) / 60) })}`),
          renderMarkdown(r.summary || ""));
        return box;
      }) : [el("p", "muted", t("prj.no_reports"))]));
    });
    const hist = d.querySelector(".history");
    hist.textContent = t("prj.history");
    hist.addEventListener("click", async () => {
      const { commits } = await call(`/v1/aurora/projects/${name}/log`);
      view.replaceChildren(el("h4", "", t("prj.history")), ...(commits.length ? commits.map((c) => {
        const r = el("div", "ev");
        r.append(el("code", "", c.hash), el("span", "muted", clock(c.date)), el("span", "", c.subject), el("span", "muted", c.author));
        return r;
      }) : [el("p", "muted", t("prj.no_history"))]));
    });
    d.querySelector(".prj-ask").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const q = ev.target.querySelector("input").value.trim();
      if (q) bus.emit("ask", { text: t("prj.ask_text", { name, base: this.base, q }) });
    });
    const show = async (path) => {
      view.replaceChildren(el("p", "muted", t("prj.loading")));
      try {
        const f = await call(`/v1/aurora/projects/${name}/file?path=${encodeURIComponent(path)}`);
        const head = el("div", "muted", `${f.path} · ${kb(f.size)}${f.truncated ? ` · ${t("prj.truncated")}` : ""}`);
        if (f.image) {
          const img = el("img", "prj-img"); img.src = `data:${f.mime};base64,${f.image}`; img.alt = f.path;
          view.replaceChildren(head, img);
        } else if (f.pdf) {                         // its pages, as pictures: the drawings and the filings seen here
          const pages = el("div", "prj-pdf");
          view.replaceChildren(head, pages);
          await pdfPages(name, f.path, f.pages, pages);
        } else if (f.binary) view.replaceChildren(head, el("p", "muted", t("prj.binary")));
        else if (/\.(md|markdown)$/i.test(f.path)) view.replaceChildren(head, renderMarkdown(f.text));
        else view.replaceChildren(head, el("pre", "prj-code", f.text));
      } catch (e) { view.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
    };
    try {
      const { files } = await call(`/v1/aurora/projects/${name}/tree`);
      // folders open and close (owner, 2026-10-21: «l'alberatura… si possa collassare ed espandere»): closed at first,
      // the open ones remembered on this device for this project
      const key = `aurora.prj.open.${name}`;
      let open;
      try { open = new Set(JSON.parse(localStorage.getItem(key) || "[]")); } catch { open = new Set(); }
      const keep = () => { try { localStorage.setItem(key, JSON.stringify([...open])); } catch { /* not kept */ } };
      const nodes = files.map((f) => {
        const parts = f.path.split("/");
        const b = el("div", `prj-node${f.dir ? " dir" : ""}`);
        b.style.paddingLeft = `${(parts.length - 1) * 0.9}rem`;
        b.dataset.path = f.path;
        b.dataset.parents = JSON.stringify(parts.slice(0, -1).map((_, i) => parts.slice(0, i + 1).join("/")));
        if (f.dir) b.addEventListener("click", () => { open.has(f.path) ? open.delete(f.path) : open.add(f.path); keep(); draw(); });
        else { b.title = kb(f.size); b.addEventListener("click", () => show(f.path)); }
        return [b, f];
      });
      const draw = () => {
        for (const [b, f] of nodes) {
          b.hidden = JSON.parse(b.dataset.parents).some((p) => !open.has(p));
          b.textContent = `${f.dir ? (open.has(f.path) ? "▾ 📂" : "▸ 📁") : "📄"} ${f.path.split("/").pop()}`;
        }
      };
      const all = el("div", "prj-tree-tools");
      const openAll = el("button", "", t("prj.tree_open"));
      const closeAll = el("button", "", t("prj.tree_close"));
      openAll.addEventListener("click", () => { for (const [, f] of nodes) if (f.dir) open.add(f.path); keep(); draw(); });
      closeAll.addEventListener("click", () => { open.clear(); keep(); draw(); });
      all.append(openAll, closeAll);
      draw();
      treeBox.replaceChildren(all, ...nodes.map(([b]) => b));
      const readme = files.find((f) => /^readme(\.md)?$/i.test(f.path));
      if (readme) show(readme.path); else view.replaceChildren(el("p", "muted", t("prj.pick")));
    } catch (e) { treeBox.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
  },
};

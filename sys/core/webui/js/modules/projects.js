// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Projects: the local ones (folder tree, files, README, history, sandboxed page preview), the owner's GitHub
// repositories (stars, forks, issues; clone to browse them), a new project, and "ask Aurora" about one.
// Reading only here; writing goes through Aurora's "projects" plugin and the owner's approvals.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { clock, el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

const kb = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);

export default {
  id: "projects",
  icon: "📁",
  title: "nav.projects",

  mount(root) {
    useCss("/static/css/projects.css");
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="prj.title"></h2><p class="muted" data-i18n="prj.hint"></p>
      <div class="prj-list">
        <h3 class="setting-cat" data-i18n="prj.local"></h3><div class="prj-local"></div>
        <h3 class="setting-cat" data-i18n="prj.github"></h3><div class="prj-github"></div>
        <h3 class="setting-cat" data-i18n="prj.new"></h3>
        <form class="prj-new"><input name="name" required pattern="[a-z0-9][a-z0-9._-]{0,63}" data-i18n-placeholder="prj.name">
          <input name="description" required data-i18n-placeholder="prj.description">
          <select name="license"><option>MIT</option><option>Apache-2.0</option><option>GPL-3.0</option><option>BSD-3-Clause</option></select>
          <input name="language" value="Python" data-i18n-placeholder="prj.language">
          <button type="submit" data-i18n="prj.create"></button> <span class="muted out"></span></form>
      </div>
      <div class="prj-detail hidden"></div>`;
    apply(root);
    this.root = root;
    this.local = root.querySelector(".prj-local");
    this.github = root.querySelector(".prj-github");
    this.list = root.querySelector(".prj-list");
    this.detail = root.querySelector(".prj-detail");
    const form = root.querySelector(".prj-new");
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const out = form.querySelector(".out");
      out.textContent = t("prj.working");
      try {
        await call("/v1/aurora/projects", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) });
        out.textContent = t("prj.created");
        form.reset();
        this.refresh();
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
  },

  async enter() { this.back(); await this.refresh(); },

  async refresh() {
    const { projects, base } = await call("/v1/aurora/projects");
    this.base = base;
    this.names = new Set(projects.map((p) => p.name));
    this.local.replaceChildren(...(projects.length ? projects.map((p) => this.localCard(p)) : [el("p", "muted", t("prj.none", { base }))]));
    this.github.replaceChildren(el("p", "muted", t("prj.loading")));
    try {
      const g = await call("/v1/aurora/projects/github");
      if (!g.connected) { this.github.replaceChildren(el("p", "muted", t("prj.gh_off"))); return; }
      const rows = g.repos.map((r) => this.repoRow(r));
      this.github.replaceChildren(el("p", "muted", t("prj.gh_user", { login: g.login, n: g.repos.length })), ...rows,
        ...(g.error ? [el("p", "error", g.error)] : []), el("p", "muted", t("prj.gh_private")));
    } catch (e) { this.github.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
  },

  localCard(p) {
    const c = el("div", "appr-card prj-card");
    const head = el("div", "ev");
    head.append(el("strong", "", `📁 ${p.name}`), el("span", "muted", p.branch ? `⎇ ${p.branch}` : ""),
      p.changes ? el("span", "pill warn", t("prj.changes", { n: p.changes })) : el("span", "pill ok", t("prj.clean")));
    c.append(head, el("div", "", p.description || t("prj.no_readme")));
    if (p.last_commit) c.append(el("div", "muted", `${p.last_commit.hash} · ${clock(p.last_commit.date)} · ${p.last_commit.subject}`));
    if (p.remote) c.append(el("div", "muted", p.remote));
    c.addEventListener("click", () => this.open(p));
    return c;
  },

  repoRow(r) {
    const row = el("div", "ev prj-repo");
    const a = el("a", "", `${r.private ? "🔒 " : ""}${r.full_name}`);
    a.href = r.html_url; a.target = "_blank"; a.rel = "noopener noreferrer";
    row.append(a, el("span", "", `⭐ ${r.stargazers_count}`), el("span", "", `🍴 ${r.forks_count}`),
      el("span", "", `🐞 ${r.open_issues_count}`), el("span", "muted", r.language || ""),
      el("span", "muted", r.pushed_at ? t("prj.pushed", { at: clock(r.pushed_at) }) : ""));
    if (r.has_pages || r.homepage) {
      const w = el("a", "", "🌐");
      w.href = r.homepage || `https://${r.full_name.split("/")[0].toLowerCase()}.github.io/${r.name}/`;
      w.target = "_blank"; w.rel = "noopener noreferrer"; w.title = t("prj.site");
      row.append(w);
    }
    const local = r.name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "");
    if (this.names.has(local)) {
      const b = el("button", "", t("prj.open"));
      b.addEventListener("click", () => this.open({ name: local }));
      row.append(b);
    } else {
      const b = el("button", "", t("prj.clone"));
      b.addEventListener("click", async () => {
        b.disabled = true; b.textContent = t("prj.cloning");
        try {
          const { name } = await call("/v1/aurora/projects/clone", { method: "POST", body: JSON.stringify({ full_name: r.full_name }) });
          await this.refresh();
          this.open({ name });
        } catch (e) { b.textContent = t("ev.error", { m: e.message }); }
      });
      row.append(b);
    }
    if (r.description) row.append(el("div", "muted prj-desc", r.description));
    return row;
  },

  back() {
    this.detail.classList.add("hidden");
    this.list.classList.remove("hidden");
    this.detail.replaceChildren();
  },

  async open(p) {
    const name = p.name;
    this.list.classList.add("hidden");
    this.detail.classList.remove("hidden");
    const d = this.detail;
    d.innerHTML = `
      <div class="ev prj-bar"><button class="back"></button><h3></h3>
        <button class="preview"></button><button class="history"></button></div>
      <form class="prj-ask"><input data-i18n-placeholder="prj.ask_ph"><button type="submit" data-i18n="prj.ask"></button></form>
      <div class="prj-body"><div class="prj-tree"></div><div class="prj-view"></div></div>`;
    apply(d);
    d.querySelector("h3").textContent = `📁 ${name}`;
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
        } else if (f.binary) view.replaceChildren(head, el("p", "muted", t("prj.binary")));
        else if (/\.(md|markdown)$/i.test(f.path)) view.replaceChildren(head, renderMarkdown(f.text));
        else view.replaceChildren(head, el("pre", "prj-code", f.text));
      } catch (e) { view.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
    };
    try {
      const { files } = await call(`/v1/aurora/projects/${name}/tree`);
      treeBox.replaceChildren(...files.map((f) => {
        const depth = f.path.split("/").length - 1;
        const b = el("div", `prj-node${f.dir ? " dir" : ""}`, `${f.dir ? "📂" : "📄"} ${f.path.split("/").pop()}`);
        b.style.paddingLeft = `${depth * 0.9}rem`;
        if (!f.dir) { b.title = kb(f.size); b.addEventListener("click", () => show(f.path)); }
        return b;
      }));
      const readme = files.find((f) => /^readme(\.md)?$/i.test(f.path));
      if (readme) show(readme.path); else view.replaceChildren(el("p", "muted", t("prj.pick")));
    } catch (e) { treeBox.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📄 A project's files (the «File» section of its page): the folder tree that opens and closes, the file viewer
// (text, Markdown, pictures, PDF pages) and «ask Aurora» about the project.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { pdfPages } from "./project_docs.js";

const kb = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);

// returns the section and show(path): the documents' section opens a file through it
export function filesView(name, base) {
  const box = el("div", "prj-files");
  box.innerHTML = `
    <form class="prj-ask"><input data-i18n-placeholder="prj.ask_ph"><button type="submit" data-i18n="prj.ask"></button></form>
    <div class="prj-body"><div class="prj-tree"></div><div class="prj-view"></div></div>`;
  apply(box);
  const view = box.querySelector(".prj-view");
  const treeBox = box.querySelector(".prj-tree");
  box.querySelector(".prj-ask").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = ev.target.querySelector("input").value.trim();
    if (q) bus.emit("ask", { text: t("prj.ask_text", { name, base, q }) });
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
      if (matchMedia("(max-width: 760px)").matches) view.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { view.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
  };
  (async () => {
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
  })();
  return { box, show };
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The WebUI's Markdown renderer under node, with a minimal DOM: what each text becomes (test_webui_md.py).
class N {
  constructor(tag) { this.tag = tag; this.children = []; this.className = ""; this.dataset = {}; this._t = ""; }
  set textContent(t) { this._t = t; this.children = []; }
  append(...c) { this.children.push(...c); }
  querySelectorAll(sel) { const out = []; const walk = (n) => { if (n.className && n.className.split(" ").includes("math") && n.dataset.tex) out.push(n); (n.children || []).forEach(walk); }; walk(this); return out; }
  removeAttribute() {}
  get classList() { return { contains: (c) => this.className.split(" ").includes(c) }; }
}
globalThis.document = { createElement: (t) => new N(t), createTextNode: (t) => ({ text: t }), querySelector: () => null, head: { append: () => {} } };
const { renderMarkdown } = await import(process.argv[2]);
const show = (n) => n.text !== undefined ? n.text : n.tag + (n.className ? "." + n.className.replace(/ /g, ".") : "") + (n._t ? `[${n._t}]` : "") + (n.children.length ? "(" + n.children.map(show).join(" ") + ")" : "");
const cases = JSON.parse(process.argv[3]);
console.log(JSON.stringify(cases.map((t) => show(renderMarkdown(t)))));

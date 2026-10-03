// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// A small, safe Markdown renderer: builds DOM elements, never parses HTML (server text stays text).
// Headings, paragraphs, **bold**, *italic*, `code`, fenced code blocks, bullet and numbered lists, tables,
// formulas ($…$, $$…$$, \(…\), \[…\]) drawn by KaTeX (vendor/katex, loaded only when a formula is there).
// Wide blocks (code, tables, formulas) scroll inside themselves: the chat never gets wider than the screen.
import { el, useCss } from "./dom.js";

let katexReady = null;
function loadKatex() {
  katexReady ??= new Promise((ok, fail) => {
    useCss("/static/vendor/katex/katex.min.css");
    const s = document.createElement("script");
    s.src = "/static/vendor/katex/katex.min.js";
    s.onload = () => ok(window.katex);
    s.onerror = fail;
    document.head.append(s);
  });
  return katexReady;
}

// The formulas of a rendered block, drawn once KaTeX is there; until then (or if it fails) the TeX stays as text.
function typeset(root) {
  const nodes = root.querySelectorAll(".math[data-tex]");
  if (!nodes.length) return;
  loadKatex().then((katex) => {
    for (const n of nodes) {
      try {
        katex.render(n.dataset.tex, n, { displayMode: n.classList.contains("math-block"), throwOnError: false, trust: false });
        n.removeAttribute("data-tex");
      } catch { /* the TeX stays readable as text */ }
    }
  }).catch(() => {});
}

function math(tex, block) {
  const n = el(block ? "div" : "span", block ? "math math-block" : "math", tex);
  n.dataset.tex = tex;
  return n;
}

function inline(parent, text) {
  // a $ is a formula only when it does not touch a space inside and no digit follows the closing one ("$5 and $10")
  const rx = /(\$\$[^$]+?\$\$|\\\(.+?\\\)|\$[^$\s](?:[^$\n]*?[^$\s])?\$(?!\d)|\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0;
  for (const m of text.matchAll(rx)) {
    if (m.index > last) parent.append(document.createTextNode(text.slice(last, m.index)));
    const tok = m[0];
    if (tok.startsWith("$$")) parent.append(math(tok.slice(2, -2).trim(), false));
    else if (tok.startsWith("\\(")) parent.append(math(tok.slice(2, -2).trim(), false));
    else if (tok.startsWith("$")) parent.append(math(tok.slice(1, -1), false));
    else if (tok.startsWith("**")) parent.append(el("strong", "", tok.slice(2, -2)));
    else if (tok.startsWith("`")) parent.append(el("code", "", tok.slice(1, -1)));
    else parent.append(el("em", "", tok.slice(1, -1)));
    last = m.index + tok.length;
  }
  if (last < text.length) parent.append(document.createTextNode(text.slice(last)));
  return parent;
}

export function renderMarkdown(text) {
  const root = el("div", "md");
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  let i = 0, para = [], m;
  const flush = () => { if (para.length) { root.append(inline(el("p"), para.join(" "))); para = []; } };
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      flush();
      const code = [];
      for (i++; i < lines.length && !/^```/.test(lines[i]); i++) code.push(lines[i]);
      root.append(el("pre", "code", code.join("\n")));
      i++;
      continue;
    }
    const mb = line.trim().match(/^(\$\$|\\\[)(.*)$/);
    if (mb) {                                         // a display formula, on one line or many
      flush();
      const close = mb[1] === "$$" ? "$$" : "\\]";
      let body = mb[2], j = i;
      while (!body.trimEnd().endsWith(close) && j + 1 < lines.length) body += "\n" + lines[++j];
      if (body.trimEnd().endsWith(close)) {
        root.append(math(body.trimEnd().slice(0, -close.length).trim(), true));
        i = j + 1;
        continue;
      }
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush();                                        // a table: header, separator, rows
      const cells = (l) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      const table = el("table");
      const head = el("tr");
      for (const c of cells(line)) head.append(inline(el("th"), c));
      table.append(head);
      for (i += 2; i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i]); i++) {
        const tr = el("tr");
        for (const c of cells(lines[i])) tr.append(inline(el("td"), c));
        table.append(tr);
      }
      const wrap = el("div", "table-wrap");
      wrap.append(table);
      root.append(wrap);
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) { flush(); root.append(inline(el(`h${Math.min(6, h[1].length + 2)}`), h[2])); i++; continue; }
    const li = line.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)/);
    if (li) {
      flush();
      const list = el(li[1] ? "ol" : "ul");
      while (i < lines.length && (m = lines[i].match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)/))) {
        list.append(inline(el("li"), m[2]));
        i++;
      }
      root.append(list);
      continue;
    }
    if (!line.trim()) { flush(); i++; continue; }
    if (/^---+$/.test(line.trim())) { flush(); root.append(el("hr")); i++; continue; }
    para.push(line.trim());
    i++;
  }
  flush();
  typeset(root);
  return root;
}

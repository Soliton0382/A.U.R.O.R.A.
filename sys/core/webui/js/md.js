// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// A small, safe Markdown renderer: builds DOM elements, never parses HTML (server text stays text).
// Headings, paragraphs, **bold**, *italic*, `code`, fenced code blocks, bullet and numbered lists.
import { el } from "./dom.js";

function inline(parent, text) {
  const rx = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0;
  for (const m of text.matchAll(rx)) {
    if (m.index > last) parent.append(document.createTextNode(text.slice(last, m.index)));
    const tok = m[0];
    if (tok.startsWith("**")) parent.append(el("strong", "", tok.slice(2, -2)));
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
  return root;
}

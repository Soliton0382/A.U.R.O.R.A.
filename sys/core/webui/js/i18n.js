// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Interface language: it_IT / en_US. Code and comments stay in English.
const STORE = "aurora.lang";
let table = {};
const extra = {};                    // the strings of this installation's own pages (js/local), by language
export let lang = "it_IT";

export async function load(code) {
  lang = code;
  table = { ...(await (await fetch(`/static/i18n/${code}.json`)).json()), ...(extra[code] || {}) };
  learn();
  try { localStorage.setItem(STORE, code); } catch { /* ignore */ }
  document.documentElement.lang = code.slice(0, 2);
  apply(document);
}

// Static labels: data-i18n (text), data-i18n-placeholder, data-i18n-title.
export function apply(root) {
  root.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((e) => { e.placeholder = t(e.dataset.i18nPlaceholder); });
  root.querySelectorAll("[data-i18n-title]").forEach((e) => { e.title = t(e.dataset.i18nTitle); });
}

export function extend(strings) {
  for (const [code, s] of Object.entries(strings)) extra[code] = { ...(extra[code] || {}), ...s };
  Object.assign(table, extra[lang] || {});
}

// this browser's copy; never chosen here: the browser's own language (an English one gets English), else Italian —
// after the login the person's choice on the server wins (style.adopt)
export function saved() {
  const guess = /^en\b/i.test(navigator.language || "") ? "en_US" : "it_IT";
  try { return localStorage.getItem(STORE) || guess; } catch { return guess; }
}

// An error the server said in English (an HTTP error's detail: its sentence is its code, "err.<sentence>" here):
// in the reader's language when the table knows it, as it came otherwise (C526).
// A sentence built with values has its places named in the table ("err.{key}: one of {allowed}"): the values are read
// out of what the server said and put into the reader's sentence.
let shapes = [];
function learn() {
  shapes = Object.keys(table).filter((k) => k.startsWith("err.") && k.includes("{")).map((k) => {
    const names = [...k.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
    const rx = k.slice(4).replace(/[.*+?^$()|[\]\\]/g, "\\$&").replace(/\{\w+\}/g, "(.+?)");
    return { rx: new RegExp(`^${rx}$`, "s"), names, to: table[k] };
  });
}

export function said(detail) {
  if (typeof detail !== "string") return detail;
  if (table[`err.${detail}`] !== undefined) return table[`err.${detail}`];
  for (const s of shapes) {
    const m = s.rx.exec(detail);
    if (m) return s.names.reduce((out, n, i) => out.replaceAll(`{${n}}`, m[i + 1]), s.to);
  }
  return detail;
}

export function t(k, vars = {}) {
  let s = table[k] ?? k;
  for (const [name, value] of Object.entries(vars)) s = s.replaceAll(`{${name}}`, value);
  return s;
}

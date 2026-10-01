// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Interface language: it_IT / en_US. Code and comments stay in English.
const STORE = "aurora.lang";
let table = {};
export let lang = "it_IT";

export async function load(code) {
  lang = code;
  table = await (await fetch(`/static/i18n/${code}.json`)).json();
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

export function saved() {
  try { return localStorage.getItem(STORE) || "it_IT"; } catch { return "it_IT"; }
}

export function t(k, vars = {}) {
  let s = table[k] ?? k;
  for (const [name, value] of Object.entries(vars)) s = s.replaceAll(`{${name}}`, value);
  return s;
}

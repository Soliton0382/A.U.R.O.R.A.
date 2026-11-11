// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The WebUI's link helpers under node (test_c594_webui_app.py): which addresses become a link, and how.
globalThis.location = new URL("https://aurora.example/");
globalThis.document = {};
const { external, safeUrl } = await import(process.argv[2]);
const anchor = () => ({ attrs: {}, set href(v) { this.attrs.href = v; }, get href() { return this.attrs.href; },
  removeAttribute(n) { delete this.attrs[n]; } });
const cases = JSON.parse(process.argv[3]);
console.log(JSON.stringify(cases.map((u) => {
  const a = external(anchor(), u);
  return [Boolean(safeUrl(u)), a.attrs.href ?? null, a.target ?? null];
})));

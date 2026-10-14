// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📑 A project's documentation (ROADMAP 100, prj_docs): the owner ticks what the project must be ready for — dimensioned
// blueprints, a patent in Italy, Europe or the USA — and «Procedi» lets Aurora make it (the cad and patent plugins),
// before, during or after the work. The files it made are listed with their pages; nothing carries an AI notice.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { t } from "../i18n.js";

// the pages of a PDF of the project, as pictures (the page's own fetch: the session's cookie)
export async function pdfPages(name, path, pages, box) {
  for (let n = 1; n <= pages; n++) {
    const img = el("img", "prj-pdf-page");
    img.alt = `${path} · ${n}/${pages}`;
    box.append(img);
    try {
      const r = await fetch(`/v1/aurora/projects/${name}/pdf?path=${encodeURIComponent(path)}&page=${n}`, { credentials: "same-origin" });
      if (r.ok) img.src = URL.createObjectURL(await r.blob());
    } catch { /* a page that cannot be drawn stays empty */ }
  }
}

export function docsView(name, open) {
  const box = el("div", "prj-docs");
  box.append(el("h4", "", t("docs.title")), el("p", "muted", t("docs.hint")));
  const list = el("div", "prj-docs-ticks");
  const go = el("button", "approve", t("docs.go"));
  const out = el("p", "muted");
  const made = el("div", "prj-docs-made");
  box.append(list, go, out, made);
  let state = { targets: [], choices: {} };

  const ticked = () => [...list.querySelectorAll("input:checked")].map((i) => i.value);
  const save = () => call(`/v1/aurora/projects/${name}/docs`, { method: "POST", body: JSON.stringify({ targets: ticked() }) }).catch(() => {});

  call(`/v1/aurora/projects/${name}/docs`).then((d) => {
    state = d;
    list.replaceChildren(...Object.entries(d.choices).map(([k, label]) => {
      const row = el("label", "rt-opt");
      const c = el("input");
      c.type = "checkbox";
      c.value = k;
      c.checked = d.targets.includes(k);
      c.addEventListener("change", save);              // kept at once: the project agent keeps them in mind too
      row.append(c, el("span", "", label));
      return row;
    }));
    const last = (d.runs || []).slice(-1)[0];
    if (last) out.textContent = t("docs.last", { when: clock(last.at), what: last.targets.map((x) => d.choices[x] || x).join(", ") });
  }).catch((e) => { out.textContent = t("ev.error", { m: e.message }); });

  go.addEventListener("click", async () => {
    const targets = ticked();
    if (!targets.length) { out.textContent = t("docs.none"); return; }
    go.disabled = true;
    try {
      const r = await call(`/v1/aurora/projects/${name}/docs`, { method: "POST", body: JSON.stringify({ targets, go: true }) });
      out.textContent = t("docs.started", { id: r.run_id });
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    go.disabled = false;
  });

  // what is there already: cad/ and patent/ PDFs, each opened with its pages
  call(`/v1/aurora/projects/${name}/tree`).then(({ files }) => {
    const pdfs = files.filter((f) => !f.dir && /^(cad|patent)\/.+\.pdf$/i.test(f.path));
    if (!pdfs.length) return;
    made.append(el("h4", "", t("docs.made")));
    for (const f of pdfs) {
      const b = el("button", "prj-docs-file", `📄 ${f.path}`);
      b.addEventListener("click", () => open(f.path));
      made.append(b);
    }
  }).catch(() => {});
  return box;
}

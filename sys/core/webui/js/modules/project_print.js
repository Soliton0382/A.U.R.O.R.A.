// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🖨️ A project's models for a 3D printer (ROADMAP N41, prj_print): each model the cad plugin built, its parts with
// their sizes, and one zip to download — the parts' STL and a README (units, list, generic advice).
import { call } from "../api.js";
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";

export function printView(name) {
  const box = el("div", "prj-print");
  box.append(el("p", "muted", t("prj.print_hint")));
  const list = el("div", "prj-grid");
  box.append(list);
  call(`/v1/aurora/projects/${name}/cad`).then(({ models }) => {
    if (!models.length) { list.replaceWith(el("p", "muted", t("prj.print_none"))); return; }
    list.replaceChildren(...models.map((m) => {
      const c = el("div", "mch-card prj-print-card");
      const head = el("div", "mch-head");
      head.append(el("strong", "", `🧊 ${m.model}`), el("span", "mch-tag", t("prj.print_parts", { n: m.parts.length })));
      const parts = el("ul", "prj-print-parts");
      parts.append(...m.parts.map((p) => el("li", "", `${p.sign} · ${p.name || p.file}`
        + (Array.isArray(p.size_mm) ? ` — ${p.size_mm.join(" × ")} mm` : ""))));
      const a = el("a", "button approve", t("prj.print_zip"));
      a.href = `/v1/aurora/projects/${name}/cad/${m.model}/print.zip?lang=${lang.startsWith("it") ? "it" : "en"}`;
      a.download = `${name}-${m.model}-stampa3d.zip`;
      c.append(head, parts, a);
      return c;
    }));
  }).catch((e) => list.replaceWith(el("p", "error", t("ev.error", { m: e.message }))));
  return box;
}

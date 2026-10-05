// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Reports: what Aurora tells about herself — her daily self-review and her repairs — apart from the approvals,
// which wait for a decision (owner, 2026-10-05).
import { call } from "../api.js";
import { clock, el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

export default {
  id: "reports",
  icon: "🩺",
  title: "nav.reports",

  mount(root) {
    useCss("/static/css/agents.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="rep.title"></h2><p class="muted" data-i18n="rep.hint"></p><div class="reports"></div>`;
    apply(root);
    this.reports = root.querySelector(".reports");
  },

  async enter() {
    const refl = await call("/v1/aurora/reflections?n=100");
    const reports = refl.filter((r) => r.type === "self_review" || r.type === "repair").slice(0, 40);
    this.reports.replaceChildren(...(reports.length ? reports.map((r, i) => {
      const d = el("details", "report");
      d.open = i === 0;                                    // the newest open
      d.append(el("summary", "", `${r.type === "repair" ? "🛠️" : "🔍"} ${clock(r.created_at)} · ${t(`appr.kind.${r.type}`)}`),
        renderMarkdown(r.text));
      return d;
    }) : [el("p", "muted", t("appr.noreports"))]));
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Aurora's diary: memories of conversations, spontaneous thoughts, dreams. Her inner life, out of the chat.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

const ICON = { session_memory: "🗂️", thought: "💭", dream: "🌌" };

export default {
  id: "diary",
  icon: "📔",
  title: "nav.diary",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="diary.title"></h2><p class="muted" data-i18n="diary.hint"></p><div class="entries"></div>`;
    apply(root);
    this.box = root.querySelector(".entries");
  },

  async enter() {
    const items = (await call("/v1/aurora/reflections?n=100")).filter((r) => ICON[r.type]);
    this.box.replaceChildren(...(items.length ? items.map((r) => {
      const d = el("details", "report");
      d.open = r === items[0];
      const extra = r.type === "thought" && r.extra.fragment_title ? ` · «${r.extra.fragment_title}»` : "";
      d.append(el("summary", "", `${ICON[r.type]} ${clock(r.created_at)} · ${t(`diary.${r.type}`)}${extra}`),
        renderMarkdown(r.text));
      if (r.type === "dream" && r.extra.image_prompt) d.append(el("div", "muted", `🎨 ${r.extra.image_prompt}`));
      return d;
    }) : [el("p", "muted", t("diary.empty"))]));
  },
};

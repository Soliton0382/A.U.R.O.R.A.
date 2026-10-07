// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Aurora's diary: memories of conversations, spontaneous thoughts, dreams. Her inner life, out of the chat.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { shareButton } from "../share.js";
import { view } from "../viewer.js";
import { autonomySlot } from "./autonomy_box.js";

const ICON = { session_memory: "🗂️", thought: "💭", dream: "🌌" };

export default {
  id: "diary",
  icon: "📔",
  title: "nav.diary",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="diary.title"></h2><p class="muted" data-i18n="diary.hint"></p><div class="entries"></div>`;
    root.querySelector("h2").after(autonomySlot("inner", "morning"));   // how free Aurora is, here (owner, 2026-10-08)
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
      const image = r.extra.image ? `/v1/aurora/images/${r.extra.image}` : null;
      if (image) {                                    // the dream's painting, opened in the viewer
        const img = el("img", "dream-img");
        img.src = image;
        img.loading = "lazy";
        img.alt = r.extra.image;
        img.addEventListener("click", () => view(image, r.extra.image, "image/png"));
        d.append(img);
      }
      if (r.type === "dream" && r.extra.image_prompt) d.append(el("div", "muted", `🎨 ${r.extra.image_prompt}`));
      if (r.type === "dream" || r.type === "thought") d.append(shareButton(r.text, image));   // never a session memory
      return d;
    }) : [el("p", "muted", t("diary.empty"))]));
  },
};

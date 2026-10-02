// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Guide: the first steps, then every page of the menu (read from the menu itself, so a new page appears here
// on its own) with what it is for and a button that opens it, then how to do the common configurations.
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

const HOWTO = ["first", "cloud", "phone", "plugins", "safety"];

export default {
  id: "guide",
  icon: "📖",
  title: "nav.guide",

  mount(root, ctx) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="gd.title"></h2><p class="muted" data-i18n="gd.hint"></p>
      <div class="gd-howto"></div><h3 class="setting-cat" data-i18n="gd.pages"></h3><div class="gd-pages"></div>`;
    apply(root);
    this.ctx = ctx;
    this.howto = root.querySelector(".gd-howto");
    this.pages = root.querySelector(".gd-pages");
  },

  enter() {
    this.howto.replaceChildren(...HOWTO.map((k, i) => {
      const d = el("details", "gd-item");
      d.open = i === 0;
      d.append(el("summary", "", t(`gd.h.${k}`)), renderMarkdown(t(`gd.b.${k}`)));
      return d;
    }));
    const rows = [];
    for (const b of document.querySelectorAll("#nav button")) {
      const id = b.dataset.view;
      if (id === this.id) continue;
      const row = el("div", "ev gd-page");
      const open = el("button", "", t("gd.open"));
      open.addEventListener("click", () => this.ctx.show(id));
      const text = el("div", "gd-text");
      text.append(el("strong", "", `${b.querySelector(".ic").textContent} ${b.querySelector(".label").textContent}`),
        el("div", "muted", t(`gd.p.${id}`) === `gd.p.${id}` ? "" : t(`gd.p.${id}`)));
      row.append(text, open);
      rows.push(row);
    }
    this.pages.replaceChildren(...rows);
  },
};

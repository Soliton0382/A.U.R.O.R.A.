// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ⋯ Avanzate, the Essenziale style's way to every other page (ROADMAP 107): the areas of the full menu as cards, read
// from the full menu itself — the same pages, hidden the same way (a user's, a plugin's switched off); each page can
// be pinned to the short menu.
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { pins, togglePin } from "../style.js";

export default {
  id: "advanced",
  icon: "⋯",
  title: "nav.advanced",

  mount(root, ctx) {
    this.ctx = ctx;
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="adv.title"></h2><p class="muted" data-i18n="adv.hint"></p><div class="adv-grid"></div>`;
    apply(root);
    this.grid = root.querySelector(".adv-grid");
  },

  enter() {
    const full = document.querySelector("#nav .nav-full");
    if (!full) return;
    const pinned = new Set(pins());
    const cards = [];
    const card = (title, buttons) => {
      const shown = buttons.filter((b) => !b.classList.contains("hidden") && b.dataset.view !== "advanced");
      if (!shown.length) return;
      const c = el("section", "adv-card");
      c.append(el("h3", "", title));
      for (const b of shown) {
        const id = b.dataset.view;
        const row = el("div", "adv-row");
        const go = el("button", "adv-go", `${b.querySelector(".ic")?.textContent || ""} ${b.querySelector(".label")?.textContent || id}`);
        go.type = "button";
        go.addEventListener("click", () => this.ctx.show(id));
        const pin = el("button", `adv-pin${pinned.has(id) ? " on" : ""}`, "📌");
        pin.type = "button";
        pin.title = t(pinned.has(id) ? "adv.unpin" : "adv.pin");
        pin.setAttribute("aria-label", `${pin.title}: ${go.textContent.trim()}`);
        pin.setAttribute("aria-pressed", String(pinned.has(id)));
        pin.addEventListener("click", () => { togglePin(id); bus.emit("pins"); this.enter(); });
        row.append(go, pin);
        c.append(row);
      }
      cards.push(c);
    };
    const loose = [];
    for (const node of full.children) {
      if (node.classList.contains("nav-group")) {
        if (!node.classList.contains("hidden")) card(node.querySelector(".nav-head .label")?.textContent || "", [...node.querySelectorAll(".nav-sub button[data-view]")]);
      } else if (node.dataset.view) loose.push(node);
    }
    card(t("adv.other"), loose);
    this.grid.replaceChildren(...cards);
  },
};

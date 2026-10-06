// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💡 Suggest an idea: a page of its own, apart from the bug report (owner, 2026-10-06). The form is ideas.js.
import { apply } from "../i18n.js";
import { renderIdeas } from "./ideas.js";

export default {
  id: "ideas",
  icon: "💡",
  title: "nav.ideas",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="idea.title"></h2><p class="muted" data-i18n="idea.hint"></p><div class="ideas"></div>`;
    apply(root);
    this.box = root.querySelector(".ideas");
  },

  enter() { return renderIdeas(this.box); },
};

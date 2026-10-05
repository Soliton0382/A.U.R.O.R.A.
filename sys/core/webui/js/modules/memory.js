// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧠 What Aurora remembers of you (owner, 2026-10-05, from what people ask of an AI: a memory they control): her
// long-term memories of your conversations, newest first, each with "forget" — gone for good, memory and index.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

export default {
  id: "memory",
  icon: "🧠",
  title: "nav.memory",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="mem.title"></h2><p class="muted" data-i18n="mem.hint"></p><div class="mem-list"></div>`;
    apply(root);
    this.list = root.querySelector(".mem-list");
  },

  async enter() {
    let items = [];
    try { items = await call("/v1/aurora/memory/about-me"); } catch (e) { this.list.textContent = t("ev.error", { m: e.message }); return; }
    if (!items.length) { this.list.replaceChildren(el("p", "muted", t("mem.none"))); return; }
    this.list.replaceChildren(el("p", "muted", t("mem.count", { n: items.length })), ...items.map((m) => {
      const d = el("details", "report");
      d.append(el("summary", "", `${clock(m.created_at)} · ${m.text.split("\n")[0].slice(0, 110)}`), renderMarkdown(m.text));
      const forget = el("button", "danger", `🗑️ ${t("mem.forget")}`);
      forget.addEventListener("click", async () => {
        if (!confirm(t("mem.forget_q"))) return;
        try { await call(`/v1/aurora/memory/about-me?source_id=${encodeURIComponent(m.source_id)}`, { method: "DELETE" }); d.remove(); }
        catch (e) { alert(e.message); }
      });
      d.append(el("div", "appr-actions"), forget);
      return d;
    }));
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Import documents into a domain of the vault.
import { call } from "../api.js";
import { el, toBase64 } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { autonomySlot } from "./autonomy_box.js";

export default {
  id: "import",
  icon: "📥",
  title: "nav.import",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="import.title"></h2>
      <p class="muted" data-i18n="import.hint"></p>
      <form class="import">
        <label><span data-i18n="import.domain"></span> <select required></select></label>
        <input type="file" multiple accept=".txt,.md,.markdown,.html,.htm,.pdf" required>
        <button type="submit" data-i18n="import.send"></button>
      </form>
      <div class="log"></div>`;
    root.querySelector("h2").after(autonomySlot("knowledge"));   // how free Aurora is, here (owner, 2026-10-08)
    apply(root);
    this.select = root.querySelector("select");
    const files = root.querySelector("input[type=file]");
    const button = root.querySelector("button");
    const log = root.querySelector(".log");
    root.querySelector("form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      button.disabled = true;
      for (const file of files.files) {
        const row = el("div", "ev");
        row.append(el("span", "ic", "⏳"), el("span", "", file.name));
        log.prepend(row);
        try {
          const r = await call("/v1/aurora/import", { method: "POST",
            body: JSON.stringify({ name: file.name, domain: this.select.value, data: await toBase64(file) }) });
          row.firstChild.textContent = "✅";
          row.lastChild.textContent = t("import.done", { name: file.name, chunks: r.chunks, written: r.written,
            dup: r.duplicates, rej: Object.keys(r.rejected).length, domain: r.domain });
        } catch (e) {
          row.className = "ev err";
          row.firstChild.textContent = "⛔";
          row.lastChild.textContent = `${file.name}: ${e.message}`;
        }
      }
      button.disabled = false;
      files.value = "";
    });
  },

  async enter() {
    const keep = this.select.value;
    const code = lang.slice(0, 2);
    const domains = await call("/v1/aurora/domains");
    this.select.replaceChildren(...domains.map((d) => { const o = el("option", "", `${d[code] || d.en} (${d.id})`); o.value = d.id; return o; }));
    if (keep) this.select.value = keep;
  },
};

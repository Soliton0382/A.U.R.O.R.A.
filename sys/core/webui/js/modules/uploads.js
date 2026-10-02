// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Files attached in the chat: what Aurora keeps so that conversations show them again; open or delete each one.
// They live as long as their conversation turn (or AURORA_UPLOADS_KEEP_DAYS); a memory reset removes them all.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { viewLink } from "../viewer.js";

const size = (n) => (n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`);

export default {
  id: "uploads",
  icon: "📎",
  title: "nav.uploads",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="up.title"></h2><p class="muted up-hint"></p><div class="up-grid"></div>
      <h3 class="setting-cat" data-i18n="up.docs"></h3><div class="up-docs"></div>`;
    apply(root);
    this.hint = root.querySelector(".up-hint");
    this.grid = root.querySelector(".up-grid");
    this.docs = root.querySelector(".up-docs");
  },

  async enter() {
    const { files, total_bytes: total, keep_days: days } = await call("/v1/aurora/uploads");
    this.hint.textContent = t("up.hint", { n: files.length, size: size(total) }) + " "
      + (days ? t("up.keep_days", { d: days }) : t("up.keep_turn"));
    this.grid.replaceChildren(...(files.filter((f) => f.size).length
      ? files.filter((f) => f.size).map((f) => this.card(f)) : [el("p", "muted", t("up.none"))]));
    const docs = await call("/v1/aurora/documents");          // the PDFs Aurora wrote: download them
    this.docs.replaceChildren(...(docs.length ? docs.map((d) => {
      const a = viewLink(el("a", "ev"), d.url, d.name, "application/pdf");
      a.append(el("span", "", "📄"), el("span", "", d.name), el("span", "muted", size(d.bytes)));
      return a;
    }) : [el("p", "muted", t("up.no_docs"))]));
  },

  card(f) {
    const c = el("div", "appr-card up-card");
    const open = el("a", "up-open");
    viewLink(open, f.url, f.name, f.mime);
    if (f.inline && f.mime.startsWith("image/")) { const img = el("img"); img.src = f.url; img.loading = "lazy"; img.alt = f.name; open.append(img); }
    else if (f.inline && f.mime.startsWith("video/")) { const v = el("video"); v.src = f.url; v.preload = "metadata"; v.muted = true; open.append(v); }
    else open.append(el("div", "up-icon", f.mime.startsWith("audio/") ? "🎧" : "📄"));
    const del = el("button", "", "🗑️");
    del.title = t("up.delete");
    del.addEventListener("click", async () => {
      if (!confirm(t("up.confirm", { name: f.name }))) return;
      await call(`/v1/aurora/uploads/${f.id}`, { method: "DELETE" });
      this.enter();
    });
    const row = el("div", "ev");
    row.append(el("span", "up-name", f.name), del);
    c.append(open, row, el("div", "muted", `${size(f.size)} · ${clock(f.created)}`));
    return c;
  },
};

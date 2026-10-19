// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Files attached in the chat: what Aurora keeps so that conversations show them again; open or delete each one.
// They live as long as their conversation turn (or AURORA_UPLOADS_KEEP_DAYS); a memory reset removes them all.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { viewLink } from "../viewer.js";

const size = (n) => (n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`);

// a file's small picture: the image itself, a PDF's first page (I5), else an icon
function thumbOf(f) {
  const pdf = f.mime === "application/pdf" || /\.pdf$/i.test(f.name);
  if (!(f.inline && /^(image|video)\//.test(f.mime)) && !pdf) return el("span", "up-icon", f.mime?.startsWith("audio/") ? "🎧" : f.mime?.startsWith("video/") ? "🎬" : "📄");
  const img = el(f.mime?.startsWith("video/") ? "video" : "img", "up-thumb");
  if (img.tagName === "VIDEO") { img.preload = "metadata"; img.muted = true; }
  else { img.loading = "lazy"; img.alt = ""; }
  img.src = pdf ? `/v1/aurora/preview/page?url=${encodeURIComponent(f.url)}&n=1` : f.url;
  img.addEventListener("error", () => img.replaceWith(el("span", "up-icon", "📄")), { once: true });
  return img;
}

// a compact list with a tick on each row (owner, 2026-10-20: «un'impaginazione più compatta e con la possibilità di
// selezionare più file alla volta prima di premere elimina — tutti, nessuno e selezione individuale»): the bar
// above ticks all or none and deletes the ticked ones with one question; a row's name opens the file
function picker(items, done) {
  const ticks = [];
  const bar = el("div", "up-bar");
  const all = el("button", "", `☑️ ${t("up.all")}`), none = el("button", "", `⬜ ${t("up.none_sel")}`);
  const del = el("button", "danger", "");
  const count = () => {
    const n = ticks.filter((x) => x.checked).length;
    del.textContent = `🗑️ ${t("up.delete_sel", { n })}`;
    del.disabled = !n;
  };
  all.addEventListener("click", () => { ticks.forEach((x) => (x.checked = true)); count(); });
  none.addEventListener("click", () => { ticks.forEach((x) => (x.checked = false)); count(); });
  del.addEventListener("click", async () => {
    const chosen = items.filter((_, i) => ticks[i].checked);
    if (!chosen.length || !confirm(t("up.confirm_n", { n: chosen.length }))) return;
    del.disabled = true;
    const failed = [];
    for (const it of chosen) { try { await it.drop(); } catch (e) { failed.push(`${it.name}: ${e.message}`); } }
    if (failed.length) alert(failed.join("\n"));
    done();
  });
  bar.append(all, none, del);
  const list = el("div", "up-list");
  for (const it of items) {
    const row = el("label", "up-row");
    const tick = el("input");
    tick.type = "checkbox";
    tick.addEventListener("change", count);
    ticks.push(tick);
    const open = viewLink(el("a", "up-name"), it.url, it.name, it.mime);
    open.textContent = it.name;
    const text = el("div", "up-text");
    text.append(open, el("span", "muted", it.meta));
    row.append(tick, it.thumb, text);
    list.append(row);
  }
  count();
  return [bar, list];
}

export default {
  id: "uploads",
  icon: "📎",
  title: "nav.uploads",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="up.title"></h2><p class="muted up-hint"></p><div class="up-grid"></div>
      <h3 class="setting-cat" data-i18n="up.docs"></h3><div class="up-docs"></div>
      <h3 class="setting-cat" data-i18n="up.trash"></h3><p class="muted up-trash-hint"></p><div class="up-trash"></div>`;
    apply(root);
    this.trash = root.querySelector(".up-trash");
    this.trashHint = root.querySelector(".up-trash-hint");
    this.hint = root.querySelector(".up-hint");
    this.grid = root.querySelector(".up-grid");
    this.docs = root.querySelector(".up-docs");
  },

  async enter() {
    const { files, total_bytes: total, keep_days: days } = await call("/v1/aurora/uploads");
    this.hint.textContent = t("up.hint", { n: files.length, size: size(total) }) + " "
      + (days ? t("up.keep_days", { d: days }) : t("up.keep_turn"));
    const kept = files.filter((f) => f.size);
    this.grid.replaceChildren(...(kept.length ? picker(kept.map((f) => ({
      name: f.name, url: f.url, mime: f.mime, meta: `${size(f.size)} · ${clock(f.created)}`, thumb: thumbOf(f),
      drop: () => call(`/v1/aurora/uploads/${f.id}`, { method: "DELETE" }) })), () => this.enter())
      : [el("p", "muted", t("up.none"))]));
    const docs = await call("/v1/aurora/documents");          // the PDFs Aurora wrote
    this.docs.replaceChildren(...(docs.length ? picker(docs.map((d) => ({
      name: d.name, url: d.url, mime: "application/pdf", meta: size(d.bytes), thumb: thumbOf({ ...d, mime: "application/pdf" }),
      drop: () => call(d.url, { method: "DELETE" }) })), () => this.enter())
      : [el("p", "muted", t("up.no_docs"))]));
    await this.loadTrash();
  },

  // the trash: what was deleted here, restorable until it expires (AURORA_TRASH_DAYS)
  async loadTrash() {
    const { items, enabled, days } = await call("/v1/aurora/trash");
    this.trashHint.textContent = enabled ? t("up.trash_hint", { d: days }) : t("up.trash_off");
    const rows = items.map((i) => {
      const row = el("div", "ev");
      const back = el("button", "", "♻️");
      back.title = t("up.restore");
      back.addEventListener("click", async () => {
        try { await call(`/v1/aurora/trash/${i.id}/restore`, { method: "POST" }); } catch (e) { alert(e.message); }
        this.enter();
      });
      const del = el("button", "danger", "✖");
      del.title = t("up.remove");
      del.addEventListener("click", async () => {
        if (!confirm(t("up.remove_q", { name: i.name }))) return;
        await call(`/v1/aurora/trash/${i.id}`, { method: "DELETE" });
        this.loadTrash();
      });
      row.append(el("span", "", i.kind === "document" ? "📄" : "📎"), el("span", "up-name", i.name),
        el("span", "muted", `${size(i.bytes)} · ${t("up.expires", { at: clock(i.expires) })}`), back, del);
      return row;
    });
    if (items.length) {
      const empty = el("button", "danger", t("up.empty"));
      empty.addEventListener("click", async () => {
        if (!confirm(t("up.empty_q", { n: items.length }))) return;
        await call("/v1/aurora/trash/all", { method: "DELETE" });
        this.loadTrash();
      });
      rows.push(empty);
    }
    this.trash.replaceChildren(...(rows.length ? rows : [el("p", "muted", t("up.trash_none"))]));
  },

};

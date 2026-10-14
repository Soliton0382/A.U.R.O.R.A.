// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🌙 Her dreams, all of them (owner, 2026-10-15: «manca una bella voce nel menù relativi ai sogni con le immagini e le
// descrizioni… dopo un po' si perdono nelle chat»): a gallery of paintings, newest first; a card opens the dream whole,
// a click on the painting opens it in the viewer; words to find one; the older ones a page at a time.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { shareButton } from "../share.js";
import { view } from "../viewer.js";

const PAGE = 24;

export default {
  id: "dreams",
  icon: "🌙",
  title: "nav.dreams",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="dreams.title"></h2><p class="muted" data-i18n="dreams.hint"></p>
      <div class="dr-bar"><input type="search" class="dr-q"><span class="muted dr-count"></span></div>
      <div class="dr-grid"></div><div class="dr-open"></div><button class="dr-more" hidden data-i18n="dreams.more"></button>`;
    apply(root);
    this.grid = root.querySelector(".dr-grid");
    this.open = root.querySelector(".dr-open");
    this.more = root.querySelector(".dr-more");
    this.count = root.querySelector(".dr-count");
    const q = root.querySelector(".dr-q");
    q.placeholder = t("dreams.search");
    let wait;
    q.addEventListener("input", () => { clearTimeout(wait); wait = setTimeout(() => { this.q = q.value; this.load(true); }, 350); });
    this.more.addEventListener("click", () => this.load(false));
    // the dream opens above the gallery: ✕, Esc or a click outside closes it, the gallery where it was
    this.open.addEventListener("click", (e) => { if (e.target === this.open) this.close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && this.open.firstChild) this.close(); });
    this.q = "";
  },

  enter() { return this.load(true); },

  async load(fresh) {
    if (fresh) { this.items = []; this.grid.replaceChildren(); this.open.replaceChildren(); }
    const before = !fresh && this.items.length ? `&before=${encodeURIComponent(this.items.at(-1).created_at)}` : "";
    let r;
    try { r = await call(`/v1/aurora/dreams?n=${PAGE}${before}&q=${encodeURIComponent(this.q || "")}`); }
    catch (e) { this.grid.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
    this.items.push(...r.dreams);
    this.grid.append(...r.dreams.map((d) => this.card(d)));
    if (!this.items.length) this.grid.replaceChildren(el("p", "muted", t(this.q ? "dreams.none_found" : "dreams.empty")));
    this.count.textContent = this.items.length ? t("dreams.count", { n: this.items.length }) + (r.more ? "+" : "") : "";
    this.more.hidden = !r.more;
  },

  card(d) {
    const b = el("button", "dr-card");
    b.type = "button";
    if (d.image) {
      const img = el("img");
      img.src = d.image;
      img.loading = "lazy";
      img.alt = d.image_prompt || t("dreams.painting");
      b.append(img);
    } else b.append(el("span", "dr-noimg", "🌙"));
    b.append(el("small", "muted", clock(d.created_at)), el("span", "dr-first", first(d.text)));
    b.addEventListener("click", () => this.show(d, b));
    return b;
  },

  show(d, card) {
    for (const c of this.grid.querySelectorAll(".dr-card.on")) c.classList.remove("on");
    card.classList.add("on");
    const box = el("article", "report dr-full");
    const close = el("button", "dr-close", "✕");
    close.title = t("dreams.close");
    close.addEventListener("click", () => this.close());
    box.append(close, el("h3", "", `🌙 ${clock(d.created_at)}`));
    if (d.image) {
      const img = el("img", "dream-img");
      img.src = d.image;
      img.alt = d.image_prompt || t("dreams.painting");
      img.addEventListener("click", () => view(d.image, d.image.split("/").pop(), "image/png"));
      box.append(img);
    }
    box.append(renderMarkdown(d.text));
    if (d.image_prompt) box.append(el("div", "muted", `🎨 ${d.image_prompt}`));
    else if (d.painting_problem) box.append(el("div", "muted", `🎨 ${t("dreams.no_painting")}: ${d.painting_problem}`));
    box.append(shareButton(d.text, d.image));
    this.open.replaceChildren(box);
    close.focus();
  },

  close() {
    this.open.replaceChildren();
    for (const c of this.grid.querySelectorAll(".dr-card.on")) { c.classList.remove("on"); c.focus(); }
  },
};

// the dream's first sentence, the card's title
function first(text) {
  const s = (text || "").replace(/\s+/g, " ").trim();
  const m = s.match(/^.{20,140}?[.!?…](\s|$)/);
  return m ? m[0].trim() : s.slice(0, 120) + (s.length > 120 ? "…" : "");
}

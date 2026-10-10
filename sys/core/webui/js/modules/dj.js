// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎧 DJ: your tracks (uploaded here, kept in your music folder), a style, "Create": one track becomes a remix, several
// become a mix at one tempo. Made in the background; a notification when ready; the mixes play here (owner, 2026-10-05).
import { call } from "../api.js";
import { clock, el, toBase64, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { deckPanel } from "./dj_deck.js";

const size = (n) => (n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`);

export default {
  id: "dj",
  icon: "🎧",
  title: "nav.dj",
  plugin: "dj",                       // in the menu only when that plugin is on

  mount(root) {
    root.classList.add("page");
    useCss("/static/css/dj_deck.css");
    root.innerHTML = `<h2 data-i18n="dj.title"></h2><p class="muted" data-i18n="dj.hint"></p>
      <h3 class="setting-cat" data-i18n="dj.tracks"></h3>
      <label class="dj-upload"><span data-i18n="dj.upload"></span><input type="file" accept="audio/*" multiple hidden></label>
      <span class="muted dj-up-out"></span><div class="dj-tracks"></div>
      <h3 class="setting-cat" data-i18n="dj.make"></h3>
      <div class="dj-deck-slot"></div>
      <div class="appr-actions"><select class="dj-style"></select><button class="approve dj-go" data-i18n="dj.go"></button>
        <span class="muted dj-out"></span></div>
      <h3 class="setting-cat" data-i18n="dj.mixes"></h3><div class="dj-mixes"></div>`;
    apply(root);
    this.tracks = root.querySelector(".dj-tracks");
    this.mixes = root.querySelector(".dj-mixes");
    this.style = root.querySelector(".dj-style");
    this.order = [];                                  // the tracks in the order they were ticked: A, then B
    this.deck = deckPanel(() => { this.order.reverse(); this.deck.show(...this.order); });
    root.querySelector(".dj-deck-slot").append(this.deck);
    this.out = root.querySelector(".dj-out");
    const upOut = root.querySelector(".dj-up-out");
    root.querySelector(".dj-upload input").addEventListener("change", async (ev) => {
      for (const f of ev.target.files) {
        upOut.textContent = t("dj.uploading", { name: f.name });
        try { await call("/v1/aurora/dj/tracks", { method: "POST", body: JSON.stringify({ name: f.name, data: await toBase64(f) }) }); }
        catch (e) { upOut.textContent = t("ev.error", { m: e.message }); return; }
      }
      upOut.textContent = "";
      ev.target.value = "";
      this.enter();
    });
    root.querySelector(".dj-go").addEventListener("click", async () => {
      const ticked = [...this.tracks.querySelectorAll("input:checked")].map((b) => b.value);
      const chosen = ticked.length === 2 ? this.order : ticked;
      if (!chosen.length) { this.out.textContent = t("dj.pick"); return; }
      const body = { tracks: chosen, style: this.style.value, ...(chosen.length === 2 ? { deck: this.deck.options() } : {}) };
      try {
        const r = await call("/v1/aurora/dj/make", { method: "POST", body: JSON.stringify(body) });
        this.out.textContent = t("dj.started", { title: r.title });
      } catch (e) { this.out.textContent = t("ev.error", { m: e.message }); }
      this.enter();
    });
  },

  player(kind, f) {
    const row = el("div", "ev dj-row");
    const audio = el("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = `/v1/aurora/dj/${kind}/${encodeURIComponent(f.name)}`;
    const del = el("button", "", "🗑️");
    del.title = t("up.delete");
    del.addEventListener("click", async (ev) => {
      ev.preventDefault();
      if (!confirm(t("up.confirm", { name: f.name }))) return;
      await call(`/v1/aurora/dj/${kind}/${encodeURIComponent(f.name)}`, { method: "DELETE" });
      this.enter();
    });
    row.append(el("span", "up-name", f.name), el("span", "muted", `${size(f.bytes)} · ${clock(f.at)}`), audio, del);
    return row;
  },

  async enter() {
    const s = await call("/v1/aurora/dj");
    if (!this.style.options.length) {
      for (const st of s.styles) { const o = el("option", "", st.label + (st.bpm ? ` · ${st.bpm} BPM` : "")); o.value = st.id; this.style.append(o); }
      this.style.value = "techno_trance";
    }
    this.tracks.replaceChildren(...(s.tracks.length ? s.tracks.map((f) => {
      const row = this.player("tracks", f);
      const box = el("input");
      box.type = "checkbox";
      box.value = f.name;
      box.checked = this.order.includes(f.name);
      box.addEventListener("change", () => {           // A and B: the order of the ticks
        this.order = this.order.filter((n) => n !== f.name);
        if (box.checked) this.order.push(f.name);
        this.deck.show(...(this.order.length === 2 ? this.order : []));
      });
      row.prepend(box);
      return row;
    }) : [el("p", "muted", t("dj.no_tracks"))]));
    this.mixes.replaceChildren(...(s.mixes.length ? s.mixes.map((f) => this.player("mixes", f)) : [el("p", "muted", t("dj.no_mixes"))]));
    clearTimeout(this.timer);
    if (s.busy) {                                    // working: the state again in a few seconds
      this.out.textContent = t("dj.busy", { title: s.busy });
      this.timer = setTimeout(() => this.enter(), 5000);
    }
  },
};

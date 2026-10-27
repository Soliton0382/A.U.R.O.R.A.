// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎧 Musica e DJ (owner, 2026-10-05; 27 Oct: «toglierei la parte sotto di elenco file che non serve più… importare musica
// propria nel player così puliamo la pagina e la rendiamo più accattivante… la chiamerei Musica e DJ»): the player is the
// page's centre — your music imported there (⏏), every track, mix, set and song in its playlist, each ticked to be
// mixed — then «Crea»: one ticked → a remix in a style, two → the two decks, more → a mix or Aurora's set; and a song
// from an idea. Made in the background; a notification when ready.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { bus } from "../bus.js";
import { deckPanel } from "./dj_deck.js";
import { djPlayer } from "./dj_player.js";
import { setConsole, setPanel, songPanel } from "./dj_set.js";
import { pluginSlot } from "./plugin_slot.js";

export default {
  id: "dj",
  icon: "🎧",
  title: "nav.dj",
  plugin: "dj",                       // in the menu only when that plugin is on

  mount(root) {
    this.root = root;
    root.classList.add("page");
    useCss("/static/css/dj_deck.css");
    useCss("/static/css/dj_set.css");
    useCss("/static/css/dj_player.css");
    root.innerHTML = `<h2 data-i18n="dj.title"></h2><p class="muted" data-i18n="dj.hint"></p><div class="dj-player-slot"></div>
      <div class="dj-console-slot"></div>
      <h3 class="setting-cat" data-i18n="dj.make"></h3><p class="muted dj-chosen"></p>
      <div class="dj-deck-slot"></div>
      <div class="appr-actions"><select class="dj-style"></select><button class="approve dj-go" data-i18n="dj.go"></button>
        <span class="muted dj-out"></span></div>
      <div class="dj-set-slot"></div><div class="dj-song-slot"></div>`;
    root.querySelector("h2")?.after(pluginSlot("dj"));   // its plugins, configured here
    apply(root);
    this.style = root.querySelector(".dj-style");
    this.order = [];                                  // what is ticked in the player, in the order of the ticks: A, then B
    this.deck = deckPanel(() => { this.order.reverse(); this.deck.show(...this.order); });
    root.querySelector(".dj-deck-slot").append(this.deck);
    root.querySelector(".dj-set-slot").append(setPanel(() => this.order, () => this.enter()));
    this.consoleSlot = root.querySelector(".dj-console-slot");
    const chosenNote = root.querySelector(".dj-chosen");
    this.playerView = djPlayer({                       // 📻 the Winamp-like player over every track, mix and song
      reload: () => this.enter(),
      onSelect: (refs) => {
        this.order = refs;
        this.deck.show(...(refs.length === 2 ? refs : []));
        chosenNote.textContent = refs.length ? t("dj.chosen", { n: refs.length }) : t("dj.pick");
      },
      onConsole: async (name) => {
        try { this.consoleSlot.replaceChildren(await setConsole(name)); this.consoleSlot.scrollIntoView({ behavior: "smooth" }); }
        catch (e) { this.consoleSlot.replaceChildren(el("p", "warn", e.message)); }
      },
    });
    root.querySelector(".dj-player-slot").append(this.playerView.box);
    // a song sung, a mix made, a failure: the playlist at once, not at the next look (owner, 27 Oct: «non c'è un
    // refresh in tempo reale dell'elenco»); the activity is each user's own (note() per user)
    bus.on("activity", (a) => { if (String(a?.event || "").startsWith("dj.") && this.root?.isConnected) this.enter(); });
    this.out = root.querySelector(".dj-out");
    root.querySelector(".dj-go").addEventListener("click", async () => {
      const chosen = this.order;
      if (!chosen.length) { this.out.textContent = t("dj.pick"); return; }
      const body = { tracks: chosen, style: this.style.value, ...(chosen.length === 2 ? { deck: this.deck.options() } : {}) };
      try {
        const r = await call("/v1/aurora/dj/make", { method: "POST", body: JSON.stringify(body) });
        this.out.textContent = t("dj.started", { title: r.title });
        this.out.dataset.working = "1";
      } catch (e) { this.out.textContent = t("ev.error", { m: e.message }); }
      this.enter();
    });
  },

  async enter() {
    const s = await call("/v1/aurora/dj");
    const songSlot = this.root.querySelector(".dj-song-slot");
    if (!songSlot.firstChild || songSlot.dataset.ready !== String(s.song.code && s.song.weights)) {
      songSlot.replaceChildren(songPanel(s.song, () => this.enter()));   // drawn again only when installed or not changes
      songSlot.dataset.ready = String(s.song.code && s.song.weights);
    }
    if (!this.style.options.length) {
      for (const st of s.styles) { const o = el("option", "", st.label + (st.bpm ? ` · ${st.bpm} BPM` : "")); o.value = st.id; this.style.append(o); }
      this.style.value = "techno_trance";
    }
    this.playerView.refresh(s);                      // the playlist follows the files
    clearTimeout(this.timer);
    if (s.busy) {                                    // working: the state again in a few seconds
      this.out.textContent = t("dj.busy", { title: s.busy });
      this.out.dataset.working = "1";
      this.timer = setTimeout(() => this.enter(), 5000);
    } else {                                         // over: no note says «working» any more (owner, 27 Oct)
      for (const n of this.root.querySelectorAll("[data-working='1']")) {
        n.textContent = t("dj.ready");
        delete n.dataset.working;
        setTimeout(() => { if (!n.dataset.working) n.textContent = ""; }, 8000);
      }
    }
  },
};

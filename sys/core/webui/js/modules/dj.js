// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎧 Musica e DJ (owner, 2026-10-05; 27 Oct: «toglierei la parte sotto di elenco file che non serve più… importare musica
// propria nel player così puliamo la pagina e la rendiamo più accattivante… la chiamerei Musica e DJ»): the player is the
// page's centre — your music imported there (⏏), every track, mix, set and song in its playlist, each ticked to be
// mixed — then «Crea»: one ticked → a remix in a style, two → the two decks, more → a mix or Aurora's set; and a song
// from an idea. Made in the background; a notification when ready. Under the player, tabs (owner, 29 Oct: «ora mi sembra
// incasinata»): 🎛️ Mixa, 📻 Radio (and 🎓 learn), 🎤 Canzone, 🎓 Stili — the one last open comes back.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { bus } from "../bus.js";
import { deckPanel } from "./dj_deck.js";
import { djPlayer } from "./dj_player.js";
import { radioPanel } from "./dj_radio.js";
import { spotifyPanel } from "./dj_spotify.js";
import { stylesPanel } from "./dj_styles.js";
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
    const tabs = [["mix", "🎛️"], ["radio", "📻"], ["song", "🎤"], ["styles", "🎓"]];
    root.innerHTML = `<h2 data-i18n="dj.title"></h2><p class="muted" data-i18n="dj.hint"></p><div class="dj-player-slot"></div>
      <div class="dj-console-slot"></div>
      <div class="prj-tabs dj-tabs">${tabs.map(([id, icon]) => `<button type="button" class="cat-chip" data-tab="${id}">${icon} <span data-i18n="dj.tab.${id}"></span></button>`).join("")}</div>
      <div class="dj-tab" data-tab="mix">
        <p class="muted dj-chosen"></p>
        <div class="dj-deck-slot"></div>
        <div class="appr-actions"><select class="dj-style"></select><button class="approve dj-go" data-i18n="dj.go"></button>
          <span class="muted dj-out"></span></div>
        <div class="dj-set-slot"></div></div>
      <div class="dj-tab dj-tab-open" data-tab="radio" hidden><div class="dj-radio-slot"></div></div>
      <div class="dj-tab dj-tab-open" data-tab="song" hidden><div class="dj-song-slot"></div></div>
      <div class="dj-tab" data-tab="styles" hidden><div class="dj-styles-slot"></div></div>`;
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
    const play = (url, title, onAir) => this.playerView.playStream(url, title, onAir);
    root.querySelector(".dj-player-slot").append(this.playerView.box);
    root.querySelector(".dj-radio-slot").append(radioPanel(play));
    root.querySelector(".dj-styles-slot").append(stylesPanel(play));
    root.querySelectorAll(".dj-tabs button").forEach((b) => b.addEventListener("click", () => this.tab(b.dataset.tab)));
    let last = "mix";
    try { last = localStorage.getItem("dj.tab") || "mix"; } catch { /* a private window: the first tab */ }
    this.tab(tabs.some(([id]) => id === last) ? last : "mix");
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

  tab(id) {                                          // one tab shown; a <details> inside it opened, its title hidden
    this.root.querySelectorAll(".dj-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
    this.root.querySelectorAll(".dj-tab").forEach((d) => {
      d.hidden = d.dataset.tab !== id;
      if (!d.hidden) d.querySelectorAll(":scope details").forEach((x) => { if (d.classList.contains("dj-tab-open")) x.open = true; });
    });
    try { localStorage.setItem("dj.tab", id); } catch { /* the choice is only a convenience */ }
  },

  fillStyles(styles) {                               // the style list, the choice kept when it is still there
    const was = this.style.value;
    this.style.replaceChildren(...styles.map((st) => {
      const o = el("option", "", st.label + (st.bpm ? ` · ${st.bpm} BPM` : ""));
      o.value = st.id;
      return o;
    }));
    this.style.value = styles.some((st) => st.id === was) ? was : "techno_trance";
  },

  async enter() {
    const s = await call("/v1/aurora/dj");
    const songSlot = this.root.querySelector(".dj-song-slot");
    if (!songSlot.firstChild || songSlot.dataset.ready !== String(s.song.code && s.song.weights)) {
      songSlot.replaceChildren(songPanel(s.song, () => this.enter(), s.song_style));   // again only when installed or not changes
      songSlot.dataset.ready = String(s.song.code && s.song.weights);
    }
    this.fillStyles(s.styles);
    if (!this.stylesHeard) {                         // a style learnt or forgotten (dj_radio.js): the list follows
      this.stylesHeard = true;
      window.addEventListener("dj-styles", async () => {
        try { this.fillStyles((await call("/v1/aurora/dj")).styles); } catch { /* the next visit fills it */ }
      });
    }
    this.playerView.refresh(s);                      // the playlist follows the files
    if (!this.spotify && s.spotify?.client_id) {      // 🟢 Spotify only where it is set up (a Premium account's)
      this.spotify = spotifyPanel(s);
      if (this.spotify) this.playerView.box.after(this.spotify);
    }
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

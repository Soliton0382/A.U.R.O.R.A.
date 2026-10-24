// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🌍 The interpreter (ROADMAP N44, owner 24 Oct: «mentre parlo le introduce simultaneamente quello che dico in una lingua
// che voglio e viceversa… una Tab apposita»): two halves, one a person, each with its language and its 🎙️. A sentence
// ends at the pause (vad.js), goes to /v1/aurora/interpret (heard in its language, translated into the other's),
// and is written on both halves and said aloud in the other language. Continuous: the next sentence is recorded
// while the last one is translated; with earphones also while it is spoken. Nothing is kept on Aurora's side.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el, toBase64, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { watch } from "../vad.js";
import * as voice from "../voice.js";

const LANGS = ["it", "en", "fr", "de", "es", "pt", "nl", "ro", "pl", "ru", "uk", "ar", "zh", "ja", "ko", "tr", "el", "sv"];
const KEY = "aurora.interpret";
const recType = () => ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac"].find((m) => MediaRecorder.isTypeSupported?.(m));

function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; } }
function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* storage unavailable */ } }

function langName(code) {
  try { return new Intl.DisplayNames([navigator.language || "it"], { type: "language" }).of(code) || code; } catch { return code; }
}

export default {
  id: "interpret",
  icon: "🌍",
  title: "nav.interpret",

  mount(root) {
    root.classList.add("page");
    useCss("/static/css/interpret.css");
    const kept = load();
    root.innerHTML = `<h2 data-i18n="interpret.title"></h2><p class="muted" data-i18n="interpret.hint"></p>
      <div class="itp-opts">
        <label><input type="checkbox" class="itp-aloud"> <span data-i18n="interpret.aloud"></span></label>
        <label><input type="checkbox" class="itp-loop"> <span data-i18n="interpret.loop"></span></label>
        <label><input type="checkbox" class="itp-ears"> <span data-i18n="interpret.ears"></span></label>
        <label><input type="checkbox" class="itp-table"> <span data-i18n="interpret.table"></span></label>
        <button class="itp-clear" data-i18n="interpret.clear"></button>
      </div>
      <div class="itp-halves"></div><p class="muted itp-out"></p>`;
    apply(root);
    this.root = root;
    this.out = root.querySelector(".itp-out");
    this.lines = [];                                  // the conversation so far, in the speakers' own words
    this.queue = Promise.resolve();                   // results shown and said in the order they were spoken
    const opt = (cls, key, dflt) => {
      const box = root.querySelector(cls);
      box.checked = kept[key] ?? dflt;
      box.addEventListener("change", () => { save({ ...load(), [key]: box.checked }); this.layout(); });
      return box;
    };
    this.aloud = opt(".itp-aloud", "aloud", true);
    this.loop = opt(".itp-loop", "loop", true);
    this.ears = opt(".itp-ears", "ears", false);
    this.table = opt(".itp-table", "table", false);
    this.halves = [this.half("b", kept.b || "en"), this.half("a", kept.a || "it")];   // the other person on top
    root.querySelector(".itp-halves").append(...this.halves.map((h) => h.box));
    root.querySelector(".itp-clear").addEventListener("click", () => {
      this.lines = [];
      this.halves.forEach((h) => { h.log.textContent = ""; });
    });
    bus.on("view", ({ id }) => { if (id !== "interpret") this.stop(); });
    this.layout();
  },

  half(side, lang) {
    const box = el("div", `itp-half itp-${side}`);
    const sel = el("select", "itp-lang");
    for (const c of LANGS) sel.append(new Option(langName(c), c, false, c === lang));
    sel.addEventListener("change", () => save({ ...load(), [side]: sel.value }));
    const mic = el("button", "approve itp-mic", "🎙️");
    mic.title = t("interpret.speak");
    const log = el("div", "itp-log");
    box.append(el("div", "itp-head", ""), log);
    box.firstChild.append(sel, mic);
    const h = { side, box, sel, mic, log, lang: () => sel.value };
    mic.addEventListener("click", () => this.toggle(h));
    return h;
  },

  layout() { this.halves?.[0].box.classList.toggle("itp-flip", this.table.checked); },

  other(h) { return this.halves.find((x) => x !== h); },

  async toggle(h) {
    if (this.active === h) { this.stop(); return; }
    this.stop();
    if (!(window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder)) {
      this.out.textContent = t("chat.src.unsupported");
      return;
    }
    if (h.lang() === this.other(h).lang()) { this.out.textContent = t("interpret.same"); return; }
    voice.unlock();                                   // during the tap: some phones speak only after one
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      this.out.textContent = t(e.name === "NotAllowedError" ? "chat.src.denied" : "ev.error", { m: e.message });
      return;
    }
    this.active = h;
    h.mic.classList.add("recording");
    h.mic.textContent = "⏹️";
    this.sentence(h);
  },

  stop() {
    this.active?.mic.classList.remove("recording");
    if (this.active) this.active.mic.textContent = "🎙️";
    this.active = null;
    this.unwatch?.();
    try { this.rec?.stop(); } catch { /* stopped already */ }
    this.stream?.getTracks().forEach((tr) => tr.stop());
    this.stream = null;
    this.floor = 0;
    this.out.textContent = "";
  },

  // one sentence: recorded until the pause, then sent; the next one starts at once (continuous) or after the voice
  async sentence(h) {
    if (this.active !== h || !this.stream) return;
    while (this.aloud.checked && !this.ears.checked && voice.speaking()) {     // a loudspeaker: not over her voice
      await new Promise((ok) => setTimeout(ok, 150));
      if (this.active !== h) return;
    }
    const type = recType();
    const chunks = [];
    const rec = new MediaRecorder(this.stream, type ? { mimeType: type } : {});
    this.rec = rec;
    rec.ondataavailable = (ev) => { if (ev.data.size) chunks.push(ev.data); };
    const t0 = performance.now();
    let nothing = false;
    this.out.textContent = t("interpret.listening", { lang: langName(h.lang()) });
    // the floor learnt by the first sentence: the next one may start while the person still speaks (C349)
    this.unwatch = watch(this.stream, (state, floor) => {
      nothing = state === "nothing";
      if (floor) this.floor = floor;
      try { rec.stop(); } catch { /* stopped already */ }
    }, 100, this.floor ? { floor: this.floor } : null);
    rec.onstop = () => {
      if (this.active !== h) return;                  // stopped by a tap: nothing sent
      if (!nothing && (performance.now() - t0) / 1000 >= 0.8 && chunks.length) {
        this.send(h, new Blob(chunks, { type: rec.mimeType || type || "audio/webm" }));
      }
      if (!this.loop.checked) { this.stop(); return; }
      // on a loudspeaker the next sentence waits for the translations to be said, not to record her voice
      if (this.aloud.checked && !this.ears.checked) this.queue.then(() => this.sentence(h));
      else this.sentence(h);
    };
    rec.start(250);
  },

  send(h, blob) {
    const src = h.lang(), dst = this.other(h).lang(), before = this.lines.slice(-4);
    const pending = el("div", "itp-line mine pending", "…");
    h.log.append(pending);
    h.log.scrollTop = h.log.scrollHeight;
    const asked = (async () => call("/v1/aurora/interpret", {
      method: "POST", body: JSON.stringify({ data: await toBase64(blob), mime: blob.type, from: src, to: dst, before }),
    }))();
    this.queue = this.queue.then(async () => {
      let r;
      try { r = await asked; } catch (e) { pending.textContent = t("ev.error", { m: e.message }); return; }
      if (!r.heard) { pending.remove(); return; }
      pending.classList.remove("pending");
      pending.textContent = r.heard;
      this.lines.push(r.heard);
      const there = this.other(h);
      const line = el("div", "itp-line theirs", r.text);
      line.title = `${r.seconds?.hear ?? "–"} s + ${r.seconds?.translate ?? "–"} s`;
      there.log.append(line);
      there.log.scrollTop = there.log.scrollHeight;
      if (this.aloud.checked) {
        try { await voice.speak(r.text, dst); } catch { this.out.textContent = t("interpret.novoice", { lang: langName(dst) }); }
      }
    });
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// webui/js/voice.js's SentenceFeed and streamSpeak under node (test_voice_pieces.py): an answer arriving in tokens is
// spoken while it is written — a fake server voice (each clip made in 20 ms) and a fake player (each clip heard in 60 ms).
globalThis.window = {}; globalThis.localStorage = { getItem: () => null, setItem: () => {} };
const t0 = Date.now(), made = [], heard = [];
globalThis.URL.createObjectURL = (b) => b.text;
globalThis.fetch = async (url, opt) => {
  const { text } = JSON.parse(opt.body);
  made.push([text, Date.now() - t0]);
  await new Promise((r) => setTimeout(r, 20));
  return { ok: true, blob: async () => ({ text }) };
};
// mode "pause": the phone pauses the second clip 20 ms in (a microphone opened: C349), as a page never would
const ended = [];
let clipNo = 0;
globalThis.Audio = class {
  constructor() { this.paused = true; this.ended = false; }
  set src(v) { this._src = v; this.left = 60; this.ended = false; this.no = ++clipNo; }
  get src() { return this._src; }
  play() {
    if (this.src.startsWith("data:")) return Promise.resolve();
    heard.push([this.src, Date.now() - t0]);
    this.paused = false;
    const from = Date.now();
    this.timer = setTimeout(() => { this.paused = true; this.ended = true; ended.push(this.src); this.onended?.(); }, this.left);
    if (process.argv[3] === "pause" && this.no === 3 && this.left === 60) {     // clip 1 is the unlock's silence
      setTimeout(() => { clearTimeout(this.timer); this.left -= Date.now() - from; this.paused = true; this.onpause?.(); }, 20);
    }
    return Promise.resolve();
  }
  pause() { clearTimeout(this.timer); this.paused = true; this.onpause?.(); }
};
const { SentenceFeed, streamSpeak } = await import(process.argv[2]);
const [mode, tokens] = [process.argv[3], JSON.parse(process.argv[4])];
if (mode === "feed") {
  const f = new SentenceFeed();
  const out = tokens.flatMap((x) => f.push(x));
  console.log(JSON.stringify([...out, ...f.end()]));
} else {
  const s = streamSpeak("it-IT");
  let at = 0;
  for (const x of tokens) { s.push(x); await new Promise((r) => setTimeout(r, 15)); }
  s.end(); at = Date.now() - t0;
  const r = await s.done;
  console.log(JSON.stringify({ r, made, heard, ended: at, whole: ended }));
}

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
globalThis.Audio = class {
  constructor() { this.paused = true; }
  play() {
    if (this.src.startsWith("data:")) return Promise.resolve();
    heard.push([this.src, Date.now() - t0]);
    this.paused = false;
    setTimeout(() => { this.paused = true; this.onended?.(); }, 60);
    return Promise.resolve();
  }
  pause() { this.paused = true; this.onpause?.(); }
};
const { SentenceFeed, streamSpeak } = await import(process.argv[2]);
const [mode, tokens] = [process.argv[3], JSON.parse(process.argv[4])];
if (mode === "feed") {
  const f = new SentenceFeed();
  const out = tokens.flatMap((x) => f.push(x));
  console.log(JSON.stringify([...out, ...f.end()]));
} else {
  const s = streamSpeak("it-IT");
  let ended = 0;
  for (const x of tokens) { s.push(x); await new Promise((r) => setTimeout(r, 15)); }
  s.end(); ended = Date.now() - t0;
  const r = await s.done;
  console.log(JSON.stringify({ r, made, heard, ended }));
}

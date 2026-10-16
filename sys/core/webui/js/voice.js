// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Aurora's answers read aloud by the device the owner is using (the PC's speakers, the phone's), with the
// browser's speech synthesis. Only the device's own voices (localService): an online voice would send the answer's
// text to the browser's maker. Modes, per device: "voice" (answer aloud when the owner spoke), "always", "off".
const KEY = "aurora.voice.reply";
const MODES = ["voice", "always", "off"];

export function mode() {
  try { const m = localStorage.getItem(KEY); if (MODES.includes(m)) return m; } catch { /* storage unavailable */ }
  return "voice";
}

export function setMode(m) {
  try { localStorage.setItem(KEY, MODES.includes(m) ? m : "voice"); } catch { /* storage unavailable */ }
}

export function nextMode() {
  const m = MODES[(MODES.indexOf(mode()) + 1) % MODES.length];
  try { localStorage.setItem(KEY, m); } catch { /* storage unavailable */ }
  return m;
}

export const supported = () => "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

// The voices load late in some browsers: wait for them; an empty list is never kept (it was, until a reload:
// a first tap before the voices arrived said "no voice" for the whole session).
let voicesReady = null;
function voices() {
  voicesReady ??= new Promise((ok) => {
    const now = speechSynthesis.getVoices();
    if (now.length) { ok(now); return; }
    const done = () => ok(speechSynthesis.getVoices());
    speechSynthesis.addEventListener("voiceschanged", done, { once: true });
    setTimeout(done, 3000);
  }).then((list) => { if (!list.length) voicesReady = null; return list; });
  return voicesReady;
}

// Why there is no voice here: none at all, or only online ones (the browser maker's: never used, they would get the text).
export async function why(lang) {
  const base = lang.slice(0, 2).toLowerCase();
  const all = (await voices()).filter((v) => v.lang.toLowerCase().startsWith(base));
  return all.length ? "online" : "none";
}

const NAME = "aurora.voice.name";
// Better first: the voices engines call natural or neural, then those of the user's chosen gender
// (AURORA_ASSISTANT_GENDER, female by default), then the rest. Engines give no gender: their names tell it.
const FEMALE = /(elsa|alice|federica|paola|isabella|bianca|lucia|carla|emma|giulia|sara|silvia|chiara|female|donna|woman)/i;
const MALE = /(luca|cosimo|diego|giorgio|roberto|marco|paolo|giuseppe|andrea|matteo|riccardo|male\b|uomo|\bman\b)/i;
let gender = "female";
export function setGender(g) { gender = g === "male" ? "male" : "female"; }
const rank = (v) => (/(natural|neural|enhanced|premium|wavenet|high)/i.test(v.name) ? 0 : 2)
  + ((gender === "male" ? MALE.test(v.name) && !/female/i.test(v.name) : FEMALE.test(v.name)) ? 0 : 1);

export async function localVoices(lang) {
  const base = lang.slice(0, 2).toLowerCase();
  return (await voices()).filter((v) => v.localService && v.lang.toLowerCase().startsWith(base))
    .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}

export function chosen() { try { return localStorage.getItem(NAME) || ""; } catch { return ""; } }
export function choose(name) { try { localStorage.setItem(NAME, name); } catch { /* storage unavailable */ } }

export const SERVER = "__aurora__";                  // the name kept when this device chose Aurora's own voice

export async function localVoice(lang) {
  if (chosen() === SERVER) return null;               // chosen on purpose: Aurora's voice from her machine
  // nothing chosen on this device: Aurora's own voice first, when her machine has it (owner, 2026-10-06)
  if (!chosen() && await serverAvailable(lang)) return null;
  const all = await localVoices(lang);
  return all.find((v) => v.name === chosen()) || all[0] || null;
}

// Aurora's voice made on her machine (mdl_tts): offered in the list of voices even when the device has none
let serverLangs = null;                              // asked once per page: the machine's voices do not change
export async function serverAvailable(lang) {
  try {
    if (!serverLangs) {
      const s = await (await fetch("/v1/aurora/tts", { credentials: "same-origin" })).json();
      serverLangs = s.enabled ? s.languages || [] : [];
    }
    return serverLangs.includes(lang.slice(0, 2).toLowerCase());
  } catch { return false; }
}

export const speakServer = (text, lang) => serverSpeak(text, lang);

// What is said: the answer without Markdown, citations, code, formulas and links.
export function speakable(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\(.+?\\\)|\$[^$\n]+\$/g, " ")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{FE0F}\u{200D}\u{20E3}]/gu, " ")   // emoji are not read aloud («stelline»)
    .replace(/\[\d+(?:\s*[,–-]\s*\d+)*\]/g, "")
    .replace(/^\s*\|.*\|\s*$/gm, " ")
    .replace(/[#*_`>|]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

// iOS and some browsers speak only after a touch: an empty utterance during the owner's tap unlocks it.
export function unlock() {
  if (supported() && !speechSynthesis.speaking) speechSynthesis.speak(new SpeechSynthesisUtterance(""));
}

// Aurora's own voice, made on her machine (mdl_tts, Piper): for a device with no local voice. The text goes only to
// Aurora's server — never to a browser maker's online voice.
// One player for the page, unlocked during the owner's tap (prime): browsers let a tap start sound only for a few
// seconds, and the voice may come later than that on a phone (C177: «solo voci online» said for a refused play).
const SILENCE = "data:audio/wav;base64,UklGRrQBAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YZABAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA";
let audio = null, player = null;
// Clips made by Aurora's machine, by text (C200): a tap plays one at once, with no wait before play() — the strictest
// browsers (Safari on the iPhone) allow sound only from inside the tap itself, and «tap again» used to make the clip
// again, wait for it, and be refused again, for ever. A message that is likely to be heard (the good morning) is
// prepared before the tap.
const clips = new Map();                             // speakable text -> object URL
const KEEP_CLIPS = 4;
export function prime() {
  if (!player) player = new Audio();
  if (player.src && !player.paused) return;
  player.src = SILENCE;
  player.play().catch(() => { /* not a tap: nothing unlocked, the real play says so */ });
}

async function fetchClip(say, lang) {
  if (clips.has(say)) return { url: clips.get(say) };
  let res;
  try {
    res = await fetch("/v1/aurora/tts", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: say, lang, format: "mp3" }) });
  } catch { return { err: "offline" }; }
  if (!res.ok) return { err: res.status === 503 ? "novoice" : "server" };
  const url = URL.createObjectURL(await res.blob());
  clips.set(say, url);
  while (clips.size > KEEP_CLIPS) {
    const [old, u] = clips.entries().next().value;
    clips.delete(old);
    URL.revokeObjectURL(u);
  }
  return { url };
}

// The clip heard to its end. A pause the page did not ask for (stop() or a new answer change `turn`) is the phone's:
// opening a microphone moves Android's sound to a call's route and pauses what plays (C349, owner 17 Oct: «quello che
// dice in quel secondo e mezzo di silenzio non si sente») — played again from where it was, not taken for the end.
export const RESUME_TRIES = 3, RESUME_MS = 400;
function untilHeard(a, mine) {
  return new Promise((ok) => {
    let tries = 0;
    a.onended = () => ok();
    a.onpause = () => {
      if (mine !== turn || a !== audio || a.ended || ++tries > RESUME_TRIES) { ok(); return; }
      setTimeout(() => {
        if (mine !== turn || a !== audio || a.ended) { ok(); return; }
        a.play().catch(() => ok());
      }, RESUME_MS);
    };
  });
}

// play() called at once, so a tap's permission is still there; the browser's refusal said by its name
function playClip(url, keep = false) {
  if (!keep) stop();
  if (!player) player = new Audio();
  audio = player;
  audio.src = url;
  return audio.play().then(() => "ok", (e) => {
    if (e?.name === "NotAllowedError") return "blocked";      // the clip stays: the next tap plays it inside the tap
    console.warn("voice: the browser could not play the clip", e);
    unplayable = e?.name || "error";
    return "unplayable";
  });
}
export let unplayable = "";                          // the name of the last refusal that was not about permission

// The answer in pieces of whole sentences (ROADMAP 99 step 3): the first one, a sentence alone, is made and heard at
// once while the next is made — a long answer's MP3 whole took 11.3 s before the first sound, its first sentence 0.8 s
// (M211). A made clip of the whole text (the good morning, prepared before the tap) is played as it is.
export function pieces(say, rest = 400) {
  const out = [];
  for (const s of say.match(/[^.!?;:]+[.!?;:]*\s*/g) || [say]) {
    const last = out.length - 1;                    // the first piece stays one sentence: heard at once
    if (last >= 1 && out[last].length + s.length <= rest) out[last] += s;
    else out.push(s);
  }
  return out.map((x) => x.trim()).filter(Boolean);
}

let queued = 0;                                       // pieces still to be heard: «speaking» until the last one
let turn = 0;                                         // a new answer or ⏹️ ends the queue of the one before
async function serverSpeak(text, lang) {
  const say = speakable(text);
  if (!say) return "ok";
  if (clips.has(say)) return playClip(clips.get(say));
  const parts = pieces(say);
  const mine = ++turn;
  queued = parts.length;
  let next = fetchClip(parts[0], lang);
  for (let i = 0; i < parts.length; i++) {
    const c = await next;
    if (mine !== turn) return "ok";                  // stopped, or another answer began
    if (c.err) { queued = 0; return c.err; }
    next = i + 1 < parts.length ? fetchClip(parts[i + 1], lang) : null;     // made while this one is heard
    const r = await playClip(c.url, true);
    if (r !== "ok") { queued = 0; return r; }
    await untilHeard(audio, mine);
    queued -= 1;
  }
  return "ok";
}

// Aurora's voice for this text made before the owner taps (only when her voice is the one this device uses)
export async function prepare(text, lang) {
  const say = speakable(text);
  if (!say || clips.has(say) || (supported() && await localVoice(lang))) return;
  await fetchClip(say, lang);
}

export function stop() {
  if (supported()) speechSynthesis.cancel();
  turn += 1;
  queued = 0;
  if (audio) { audio.pause(); audio = null; }
}

export const speaking = () => queued > 0 || Boolean(audio && !audio.paused) || (supported() && (speechSynthesis.speaking || speechSynthesis.pending));

// Long texts in sentences: some engines stop a single long utterance after ~15 s.
export async function speak(text, lang, only = null) {
  // made already: played inside the tap, nothing before it — unless this device chose one of its own voices since
  const ready = !only && (!chosen() || chosen() === SERVER) && clips.get(speakable(text));
  if (ready) return playClip(ready);
  prime();
  const voice = only || (supported() ? await localVoice(lang) : null);
  if (!voice) return serverSpeak(text, lang);              // none here: Aurora's own voice from her machine
  stop();
  const parts = speakable(text).match(/[^.!?;:]+[.!?;:]*\s*/g) || [];
  for (const p of parts) {
    const u = new SpeechSynthesisUtterance(p.trim());
    u.voice = voice;
    u.lang = voice.lang;
    speechSynthesis.speak(u);
  }
  return "ok";
}

// ROADMAP 99: the answer spoken while it is written (the self route, whose final text is the stream itself: nothing is
// taken out afterwards). The text comes in tokens; a piece goes out when it ends a sentence and says something (≥ MIN_SAY
// characters spoken: «1.» of a list waits for its item), never inside a code block still open.
const MIN_SAY = 12;
export class SentenceFeed {
  constructor() { this.buf = ""; }
  push(text) { this.buf += text; return this.take(false); }
  end() { return this.take(true); }
  take(all) {
    let cut = all ? this.buf.length : -1;
    if (!all) {
      const re = /[.!?;:](?=\s)|\n\s*\n/g;
      for (let m; (m = re.exec(this.buf));) {
        const end = m.index + m[0].length, head = this.buf.slice(0, end);
        if ((head.match(/```/g) || []).length % 2 === 0 && speakable(head).length >= MIN_SAY) cut = end;   // outside code
      }
    }
    if (cut <= 0) return [];
    const out = this.buf.slice(0, cut);
    this.buf = this.buf.slice(cut);
    return speakable(out) ? [out] : [];
  }
}

// {push(text), end()} and `done`, the outcome as speak() says it. The first piece one sentence, heard at once; then
// what has come meanwhile, up to 400 characters, made while the piece before is heard (M211's queue, fed as it grows)
export function streamSpeak(lang) {
  stop();
  const mine = turn;
  prime();
  const feed = new SentenceFeed(), queue = [];
  let ended = false, wake = null, first = true;
  queued = 1;                                         // «speaking» from the first token to the last piece heard
  const put = (chunks) => { for (const c of chunks) { const s = speakable(c); if (s) queue.push(s); } wake?.(); };
  const more = () => new Promise((ok) => {           // until a piece or the end comes; only its own waker cleared
    if (queue.length || ended) { ok(); return; }
    const mineWake = () => { if (wake === mineWake) wake = null; ok(); };
    wake = mineWake;
  });
  const take = () => {
    let say = queue.shift();
    while (!first && queue.length && say.length + 1 + queue[0].length <= 400) say += ` ${queue.shift()}`;
    first = false;
    return say;
  };
  const done = (async () => {
    const own = supported() && (!chosen() || chosen() !== SERVER) ? await localVoice(lang) : null;
    let ahead = null;                                 // the next clip, made while this one is heard
    while (mine === turn) {
      if (!ahead && !queue.length) { if (ended) return "ok"; await more(); continue; }
      if (own) {                                      // the device's voice queues the sentences itself
        const u = new SpeechSynthesisUtterance(take());
        u.voice = own;
        u.lang = own.lang;
        speechSynthesis.speak(u);
        continue;
      }
      const c = await (ahead || fetchClip(take(), lang));
      ahead = null;
      if (mine !== turn) return "ok";
      if (c.err) return c.err;
      const r = await playClip(c.url, true);
      if (r !== "ok") return r;
      const heard = untilHeard(audio, mine);
      while (!queue.length && !ended && audio && !audio.paused) await Promise.race([heard, more()]);
      if (queue.length) ahead = fetchClip(take(), lang);
      await heard;
    }
    return "ok";
  })().finally(() => { if (mine === turn) queued = 0; });
  return {
    push: (text) => { if (mine === turn) put(feed.push(text)); },
    end: () => { if (mine === turn) { put(feed.end()); ended = true; wake?.(); } },
    done,
  };
}

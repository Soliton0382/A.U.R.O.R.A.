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
let audio = null, player = null, ready = null;
export function prime() {
  if (!player) player = new Audio();
  if (player.src && !player.paused) return;
  player.src = SILENCE;
  player.play().catch(() => { /* not a tap: nothing unlocked, the real play says so */ });
}
async function serverSpeak(text, lang) {
  const say = speakable(text);
  if (!say) return "ok";
  let res;
  try {
    res = await fetch("/v1/aurora/tts", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: say, lang, format: "mp3" }) });
  } catch { return "offline"; }
  if (!res.ok) return res.status === 503 ? "novoice" : "server";
  stop();
  if (ready) URL.revokeObjectURL(ready);
  ready = URL.createObjectURL(await res.blob());
  audio = player || new Audio();
  audio.src = ready;
  try {
    await audio.play();
    return "ok";
  } catch { return "blocked"; }                  // the browser refused: a second tap plays it at once (it is here)
}

export function stop() {
  if (supported()) speechSynthesis.cancel();
  if (audio) { audio.pause(); audio = null; }
}

export const speaking = () => Boolean(audio && !audio.paused) || (supported() && (speechSynthesis.speaking || speechSynthesis.pending));

// Long texts in sentences: some engines stop a single long utterance after ~15 s.
export async function speak(text, lang, only = null) {
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

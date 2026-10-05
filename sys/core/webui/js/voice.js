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

// The voices load late in some browsers: wait for them once.
let voicesReady = null;
function voices() {
  voicesReady ??= new Promise((ok) => {
    const now = speechSynthesis.getVoices();
    if (now.length) { ok(now); return; }
    const done = () => ok(speechSynthesis.getVoices());
    speechSynthesis.addEventListener("voiceschanged", done, { once: true });
    setTimeout(done, 1500);
  });
  return voicesReady;
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

export async function localVoice(lang) {
  const all = await localVoices(lang);
  return all.find((v) => v.name === chosen()) || all[0] || null;
}

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

export function stop() { if (supported()) speechSynthesis.cancel(); }

export const speaking = () => supported() && (speechSynthesis.speaking || speechSynthesis.pending);

// Long texts in sentences: some engines stop a single long utterance after ~15 s.
export async function speak(text, lang, only = null) {
  if (!supported()) return "unsupported";
  const voice = only || await localVoice(lang);
  if (!voice) return "novoice";
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

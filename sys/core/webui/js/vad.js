// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// When the owner starts and stops speaking, from the microphone's level (ROADMAP 99, owner 2026-10-13: «non è proprio
// real time»): no tap to stop a dictation; in a conversation the silence closes the turn. Local only: the level is
// read in the browser, nothing leaves until the turn is recorded.

// The decision, apart from the microphone (tested under node): the noise floor is learnt in the first CALIB ms; a
// level above max(floor × RATIO, MIN) is speech; after speech, SILENCE ms quiet end the turn; no speech in WAIT ms:
// nothing was said.
export const CALIB = 300, RATIO = 3, MIN = 0.012, SILENCE = 1200, WAIT = 8000;

export class SilenceGate {
  constructor() { this.t = 0; this.floor = 0; this.n = 0; this.heard = false; this.quiet = 0; }
  // rms: the level of the last `ms` of sound → "calibrating" | "waiting" | "speaking" | "end" | "nothing"
  step(rms, ms) {
    this.t += ms;
    if (this.t <= CALIB) { this.floor = (this.floor * this.n + rms) / ++this.n; return "calibrating"; }
    const loud = rms > Math.max(this.floor * RATIO, MIN);
    if (loud) { this.heard = true; this.quiet = 0; return "speaking"; }
    if (!this.heard) return this.t >= WAIT ? "nothing" : "waiting";
    this.quiet += ms;
    return this.quiet >= SILENCE ? "end" : "speaking";
  }
}

// Watch a microphone stream; onEnd("end" | "nothing") once. Returns stop(). No Web Audio here: the gate never ends.
export function watch(stream, onEnd, every = 100) {
  const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!AC) return () => {};
  const ctx = new AC();
  ctx.resume?.().catch(() => {});                   // reopened without a tap (a conversation): started anyway
  const an = ctx.createAnalyser();
  an.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(an);
  const buf = new Float32Array(an.fftSize);
  const gate = new SilenceGate();
  let done = false;
  const timer = setInterval(() => {
    an.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    const state = gate.step(Math.sqrt(sum / buf.length), every);
    if (state === "end" || state === "nothing") { stop(); onEnd(state); }
  }, every);
  function stop() {
    if (done) return;
    done = true;
    clearInterval(timer);
    ctx.close().catch(() => {});
  }
  return stop;
}

// Barge-in (owner, 2026-10-14: «se parli con una persona, spesso la conversazione non è un ricevo tutto e poi ti
// rispondo»): while Aurora speaks in a conversation, the owner's voice over hers stops her and opens the microphone.
// Stricter than the end of a turn: her own voice leaking from the speakers (echo cancellation takes most of it) is the
// floor learnt here, so only a voice OVER × that floor, for HOLD ms in a row, counts — a cough is not a turn.
export const OVER = 5, HOLD = 400;

export class BargeGate {
  constructor() { this.t = 0; this.floor = 0; this.n = 0; this.run = 0; }
  step(rms, ms) {                                    // → true when the owner is speaking over her
    this.t += ms;
    if (this.t <= CALIB) { this.floor = (this.floor * this.n + rms) / ++this.n; return false; }
    this.run = rms > Math.max(this.floor * OVER, MIN * 2) ? this.run + ms : 0;
    return this.run >= HOLD;
  }
}

// Listen for the owner over Aurora's voice; onSpeech() once. Returns stop(). Nothing is recorded or sent here.
export function bargeIn(stream, onSpeech, every = 100) {
  const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!AC) return () => {};
  const ctx = new AC();
  ctx.resume?.().catch(() => {});
  const an = ctx.createAnalyser();
  an.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(an);
  const buf = new Float32Array(an.fftSize);
  const gate = new BargeGate();
  let done = false;
  const timer = setInterval(() => {
    an.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    if (gate.step(Math.sqrt(sum / buf.length), every)) { stop(); onSpeech(); }
  }, every);
  function stop() {
    if (done) return;
    done = true;
    clearInterval(timer);
    ctx.close().catch(() => {});
  }
  return stop;
}

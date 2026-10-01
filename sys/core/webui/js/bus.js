// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The only channel between modules: named events with a payload.
//   thinking  {active: boolean}   a run started / all runs ended (the sky listens)
//   view      {id}                the shell changed view
//   lang      {code}              the interface language changed
const target = new EventTarget();

export const bus = {
  on(name, fn) {
    const h = (ev) => fn(ev.detail);
    target.addEventListener(name, h);
    return () => target.removeEventListener(name, h);
  },
  emit(name, detail = {}) { target.dispatchEvent(new CustomEvent(name, { detail })); },
};

// Runs in progress, counted, so that overlapping runs keep "thinking" on until the last ends.
let running = 0;
export function runStarted() { if (running++ === 0) bus.emit("thinking", { active: true }); }
export function runEnded() { running = Math.max(0, running - 1); if (running === 0) bus.emit("thinking", { active: false }); }

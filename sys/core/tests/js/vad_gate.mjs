// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The silence gate of webui/js/vad.js under node: a sequence of levels (one every 100 ms) → the states (test_vad.py).
const { SilenceGate } = await import(process.argv[2]);
const out = {};
for (const [name, given] of Object.entries(JSON.parse(process.argv[3]))) {
  const [levels, from] = Array.isArray(given) ? [given, null] : [given.levels, given.from];   // from: a barge-in's hand-over
  const g = new SilenceGate(from);
  let last = "";
  for (const v of levels) { last = g.step(v, 100); if (last === "end" || last === "nothing") break; }
  out[name] = [last, g.t];
}
console.log(JSON.stringify(out));

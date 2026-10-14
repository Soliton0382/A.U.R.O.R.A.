// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The barge-in gate of webui/js/vad.js under node: levels (one every 100 ms) → the ms at which it fired, or -1.
const { BargeGate } = await import(process.argv[2]);
const out = {};
for (const [name, levels] of Object.entries(JSON.parse(process.argv[3]))) {
  const g = new BargeGate();
  out[name] = -1;
  for (const v of levels) if (g.step(v, 100)) { out[name] = g.t; break; }
}
console.log(JSON.stringify(out));

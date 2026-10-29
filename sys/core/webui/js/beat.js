// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🥁 A beat from the bass (the player's spectrum, every frame): the bass rising by RISE over its lowest of the last WIN
// frames, at most one beat every MIN_GAP_MS → bus "beat" {n}. The top bar's face dances on it (owner, 30 Oct: «far
// alternare anche le emoji facendole ballare sul loro posto, tipo a ritmo della musica»). A rise, not a peak: the
// analyser smooths, a mix's bass stays at 0.57–0.93 and climbs over ~10 frames on a kick — measured on a trance mix,
// 25 s: «30 % over the average» found 7 beats, this 45 (median 433 ms apart, 138 BPM).
import { bus } from "./bus.js";

const RISE = 0.06;
const WIN = 10;                            // frames, about 170 ms at 60 fps
const FLOOR = 0.25;                        // a quiet bass is never a beat
const MIN_GAP_MS = 280;                    // 214 BPM at most
let ring = [], last = 0, n = 0;

export function beat(bass, now, live) {
  if (!live) { ring = []; return false; }
  const low = ring.length ? Math.min(...ring) : bass;
  const hit = bass - low >= RISE && bass > FLOOR && now - last > MIN_GAP_MS;
  ring.push(bass);
  if (ring.length > WIN) ring.shift();
  if (!hit) return false;
  last = now;
  ring = [bass];                           // the next beat rises from here
  bus.emit("beat", { n: ++n });
  return true;
}

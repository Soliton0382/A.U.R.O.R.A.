// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧠 How much Aurora thinks for the next messages (kno_think; owner, 2026-10-07: «leggera, media, profonda e auto»):
// chosen in the composer's ⚙️ menu (chat_menu.js), remembered by this device; "" leaves it to AURORA_ANSWER_MODE.
export const THINK = ["", "auto", "light", "medium", "deep"];
export const THINK_ICON = { "": "🧠", auto: "🤖", light: "⚡", medium: "⚖️", deep: "🔬" };
const KEY = "aurora.think";
let kept = null;                      // the page's own copy: a private window keeps the choice until it closes

export function thinkMode() {
  if (kept !== null) return kept;
  try { const v = localStorage.getItem(KEY) || ""; kept = THINK.includes(v) ? v : ""; } catch { kept = ""; }
  return kept;
}

export function setThink(mode) {
  kept = THINK.includes(mode) ? mode : "";
  try { localStorage.setItem(KEY, kept); } catch { /* storage unavailable: this visit only */ }
}

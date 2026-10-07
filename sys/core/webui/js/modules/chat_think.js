// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧠 How much Aurora thinks for the next messages (kno_think; owner, 2026-10-07: «leggera, media, profonda e auto»): a
// tap changes it, this device remembers it; «⚙️» leaves it to the setting AURORA_ANSWER_MODE.
import { t } from "../i18n.js";

const MODES = ["", "auto", "light", "medium", "deep"];
const ICON = { "": "⚙️", auto: "🤖", light: "⚡", medium: "⚖️", deep: "🔬" };
const KEY = "aurora.think";

function load() {
  try { const v = localStorage.getItem(KEY) || ""; return MODES.includes(v) ? v : ""; } catch { return ""; }
}

// the button shows the mode and cycles through them; returns a function that gives the mode to send ("" = the setting)
export function thinkButton(btn) {
  let mode = load();
  const show = () => {
    btn.textContent = ICON[mode];
    btn.title = t(`chat.think.${mode || "setting"}`);
    btn.setAttribute("aria-label", btn.title);
  };
  btn.addEventListener("click", () => {
    mode = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    try { localStorage.setItem(KEY, mode); } catch { /* this device only: kept for the page */ }
    show();
  });
  show();
  return () => mode;
}

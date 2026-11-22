// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📚 Where Aurora searches her vault for the next messages (kno_scope; owner, 2026-11-20: «bottoni come quella sulla
// profondità di ragionamento... retrieval nel vault verso domini specifici o in modalità automatica»): chosen in the
// composer's ⚙️ menu (chat_menu.js), several together, remembered by this device; none chosen is 🤖 auto (as before).
// The groups are kno_scope.GROUPS (the same ids, tests/test_scope.py): their domains are decided by the server.
export const SOURCES = ["legal", "medicine", "science", "technology", "humanities", "economics", "general"];
export const SOURCE_ICON = { auto: "🤖", legal: "⚖️", medicine: "🩺", science: "🔬", technology: "💻", humanities: "📜",
  economics: "💰", general: "📖" };
const KEY = "aurora.sources";
let kept = null;                      // the page's own copy: a private window keeps the choice until it closes

const clean = (list) => SOURCES.filter((s) => Array.isArray(list) && list.includes(s));

export function sourcesChoice() {
  if (kept !== null) return kept;
  try { kept = clean(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch { kept = []; }
  return kept;
}

// "auto" empties the choice; a group is added or taken away
export function toggleSource(s) {
  const now = sourcesChoice();
  kept = s === "auto" ? [] : clean(now.includes(s) ? now.filter((x) => x !== s) : [...now, s]);
  try { localStorage.setItem(KEY, JSON.stringify(kept)); } catch { /* storage unavailable: this visit only */ }
  return kept;
}

// what the gear shows: the chosen icons, at most two and «+n»; nothing for auto
export function sourcesBadge(list = sourcesChoice()) {
  if (!list.length) return "";
  const icons = list.map((s) => SOURCE_ICON[s]);
  return icons.length > 2 ? `${icons.slice(0, 2).join("")}+${icons.length - 2}` : icons.join("");
}

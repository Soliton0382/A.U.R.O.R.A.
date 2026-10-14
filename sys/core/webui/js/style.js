// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The menu's style, each person's choice (ROADMAP 107; owner, 2026-10-15: «c'è chi preferisce menù completi come gli
// admin e chi preferisce menù minimalisti… è giusto che ognuno scelga il suo stile… un terzo che unisce admin e
// minimal»): Completo (every area, the chat first), Essenziale (six pages, the pinned ones, Avanzate one click away;
// Oggi first), Misto (every area, Oggi first). Until one is chosen: Completo for the admin, Essenziale for a user. The
// colours are the theme's (theme.js): a style changes what the menu holds, never the colours. The style and the pins
// are each person's on the server (/v1/aurora/me/prefs: the same on every device); this browser keeps a copy, so the
// page opens in its style before the server answers.
import { call } from "./api.js";
import { THEMES, applyTheme, current as currentTheme } from "./theme.js";

export const STYLES = ["completo", "essenziale", "misto"];
export const SHORT = ["today", "chat", "home", "calendar", "dreams", "memory"];
const KEY = "aurora.style";
const PINS = "aurora.pins";
const OWNER = "aurora.prefs.who";
const THEME = "aurora.theme";                           // theme.js's own copy

export function chosen() {
  try { return STYLES.includes(localStorage.getItem(KEY)) ? localStorage.getItem(KEY) : null; } catch { return null; }
}

export function current(isAdmin) {
  return chosen() || (isAdmin ? "completo" : "essenziale");
}

export function applyStyle(id) {
  document.body.dataset.style = STYLES.includes(id) ? id : "completo";
}

export function setStyle(id) {
  try { localStorage.setItem(KEY, id); } catch { /* private window: this visit only */ }
  applyStyle(id);
  save({ style: id });
}

// what the server holds for this person, taken as this browser's copy (at login, on every device)
// whose copy it is: two people on one browser never get each other's; a choice made here before the server kept
// them (one person's) goes up once
export function adopt(prefs, who) {
  try {
    const owner = localStorage.getItem(OWNER);
    if (owner !== null && owner !== String(who)) { localStorage.removeItem(KEY); localStorage.removeItem(PINS); localStorage.removeItem(THEME); }
    localStorage.setItem(OWNER, String(who));
    const up = {};
    if (STYLES.includes(prefs?.style)) localStorage.setItem(KEY, prefs.style);
    else if (chosen()) up.style = chosen();
    if (Array.isArray(prefs?.pins)) localStorage.setItem(PINS, JSON.stringify(prefs.pins));
    else if (pins().length) up.pins = pins();
    if (THEMES.some((x) => x.id === prefs?.theme)) applyTheme(prefs.theme);          // the colours too, on any device
    else if (localStorage.getItem(THEME)) up.theme = currentTheme();
    else applyTheme("aurora");                           // another person's colours never stay
    if (Object.keys(up).length) save(up);
  } catch { /* this visit only */ }
}

function save(change) {
  call("/v1/aurora/me/prefs", { method: "PUT", body: JSON.stringify(change) }).catch(() => { /* kept here, said nowhere */ });
}

// the first page: Oggi for the two styles that have it, the chat for Completo (as before)
export function home(isAdmin) {
  return current(isAdmin) === "completo" ? "chat" : "today";
}

export function pins() {
  try { return JSON.parse(localStorage.getItem(PINS) || "[]").filter((x) => typeof x === "string"); } catch { return []; }
}

export function togglePin(id) {
  const now = pins();
  const next = now.includes(id) ? now.filter((x) => x !== id) : [...now, id].slice(-8);
  try { localStorage.setItem(PINS, JSON.stringify(next)); } catch { /* this visit only */ }
  save({ pins: next });
  return next;
}

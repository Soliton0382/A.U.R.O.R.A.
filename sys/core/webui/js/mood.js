// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💗 Aurora's emotions (kno_mood, roadmap 52): the face that prevails, and the rows with their measured causes —
// shared by the top bar's mood button (alerts.js) and the Health page (status.js).
import { el } from "./dom.js";
import { t } from "./i18n.js";

// one face per emotion that can prevail; the rows use the same faces
export const MOOD_ICON = { serenity: "😌", stress: "😣", satisfaction: "😊", curiosity: "🧐", tiredness: "😴",
  longing: "🥺", melancholy: "😔", worry: "😟", anger: "😠", joy: "😄" };

// the music player playing: she listens with you (owner, 27 Oct: «una bella emoji con le cuffie»), unless anger or
// worry prevail — those are never hidden
export const listening = (m) => Boolean(m?.listening) && !["anger", "worry"].includes(m?.dominant);
export const moodFace = (m) => (listening(m) ? "🎧" : MOOD_ICON[m?.dominant] || "😌");
export const moodKey = (m) => (listening(m) ? "listening" : m?.dominant || "serenity");

export function moodTitle(m) {
  return t("mood.title", { d: `${moodFace(m)} ${t(`mood.${m.dominant || "serenity"}`)}` });
}

// the dominant emotion's first cause, in one line (the top bar's tooltip and aria-label)
export function moodLine(m) {
  if (listening(m)) return t("mood.listening", { title: m.listening.title || "…" });
  const top = m.emotions?.[m.dominant];
  return top ? `${moodTitle(m)} — ${top.causes[0]}` : `${moodTitle(m)} — ${t("mood.calm")}`;
}

export function moodRows(m) {
  const rows = [];
  for (const [k, v] of Object.entries(m.emotions || {})) {
    const row = el("div", `ev mood-row${k === m.dominant ? " top" : ""}`);
    const bar = el("span", "mood-bar");
    const fill = el("span", "");
    fill.style.width = `${Math.round(100 * (v.value || 0))}%`;
    bar.append(fill);
    row.append(el("span", "", MOOD_ICON[k] || "•"), el("strong", "", t(`mood.${k}`)), bar,
      el("span", "", v.value === null ? "—" : v.value.toFixed(2)), el("span", "muted", v.causes.join(" · ")));
    rows.push(row);
  }
  return rows;
}

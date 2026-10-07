// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🍽️ A meal of the diet plan (hlt_diet, roadmap 55): the dish proposed with its reasons, the alternatives, "I'll have
// this", a free meal, something else in words — shared by Health → Diet (care_diet.js) and the chat's reminder.
import { call } from "./api.js";
import { el, useCss } from "./dom.js";
import { t } from "./i18n.js";

useCss("/static/css/diet.css");

const MEAL_ICON = { colazione: "☕", spuntino: "🍎", pranzo: "🍝", merenda: "🥛", cena: "🍽️" };

export const mealTitle = (meal) => `${MEAL_ICON[meal] || "🍽️"} ${t(`diet.meal.${meal}`)}`;

async function choose(s, body) {
  return call("/v1/aurora/diet/choice", { method: "POST", body: JSON.stringify({ day: s.day, meal: s.meal, ...body }) });
}

function option(s, o, top, done) {
  const box = el("div", `diet-opt${top ? " top" : ""}`);
  const list = el("ul", "diet-items");
  for (const it of o.items) list.append(el("li", "", it));
  box.append(list);
  if (o.note) box.append(el("div", "muted", o.note));
  if (o.why.length) box.append(el("div", "diet-why muted", o.why.join(" · ")));
  const pick = el("button", top ? "primary" : "", `✓ ${t("diet.pick")}`);
  pick.type = "button";
  pick.addEventListener("click", async () => {
    pick.disabled = true;
    try { await choose(s, { option: o.id }); done(); } catch (e) { pick.disabled = false; box.append(el("div", "warn", e.message)); }
  });
  box.append(pick);
  return box;
}

// one meal: chosen already (with "undo"), or the proposal, the alternatives and the other ways to answer
export function mealCard(s, done, { compact = false } = {}) {
  const card = el("div", "diet-meal");
  card.dataset.meal = s.meal;
  card.append(el("h4", "", mealTitle(s.meal)));
  if (s.chosen) {
    const c = s.chosen;
    const what = c.free ? t("diet.free") : c.option ? [s.suggested, ...s.alternatives].find((o) => o?.id === c.option)?.label
      || c.option : c.text;
    const row = el("div", "diet-chosen", `✅ ${what}`);
    const undo = el("button", "link", t("diet.undo"));
    undo.type = "button";
    undo.addEventListener("click", async () => { await call(`/v1/aurora/diet/choice/${c.id}`, { method: "DELETE" }); done(); });
    row.append(" ", undo);
    card.append(row);
    return card;
  }
  if (!s.suggested) { card.append(el("p", "muted", t("diet.no_option"))); return card; }
  card.append(el("div", "diet-label", t("diet.proposed")), option(s, s.suggested, true, done));
  for (const h of s.hints || []) card.append(el("div", "diet-hint", `💡 ${h}`));
  if (s.alternatives.length) {
    const more = el("details", "diet-more");
    more.append(el("summary", "", t("diet.alternatives", { n: s.alternatives.length })));
    for (const o of s.alternatives) more.append(option(s, o, false, done));
    if (!compact) more.open = false;
    card.append(more);
  }
  const other = el("form", "diet-other");
  const words = el("input");
  words.placeholder = t("diet.other_ph");
  const ok = el("button", "", t("diet.other"));
  other.append(words, ok);
  other.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!words.value.trim()) return;
    try { await choose(s, { text: words.value }); done(); } catch (e) { other.append(el("div", "warn", e.message)); }
  });
  if (s.free_left) {
    const free = el("button", "", `🍕 ${t("diet.free_left", { n: s.free_left })}`);
    free.type = "button";
    free.addEventListener("click", async () => { await choose(s, { free: true }); done(); });
    card.append(free);
  }
  card.append(other);
  return card;
}

// the chat: the meals reminded and not answered yet, one bubble each (owner, 2026-10-07: «messaggi automatici in chat»)
export async function dietBubbles(messages) {
  let pend;
  try { pend = await call("/v1/aurora/diet/pending"); } catch { return; }
  for (const s of pend.meals || []) {
    const key = `${s.day}-${s.meal}`;
    if (messages.querySelector(`[data-diet="${key}"]`)) continue;
    const m = el("div", "msg aurora diet-bubble");
    m.dataset.diet = key;
    const done = () => { m.replaceChildren(el("div", "dream-title", mealTitle(s.meal)), el("p", "", `✅ ${t("diet.noted")}`)); };
    m.append(el("div", "dream-title", t("diet.time_for", { meal: t(`diet.meal.${s.meal}`) })), mealCard(s, done, { compact: true }));
    messages.append(m);
  }
}

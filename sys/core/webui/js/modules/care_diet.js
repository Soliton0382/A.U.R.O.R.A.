// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🍽️ Health → Diet: the dietitian's plan followed day by day (roadmap 55, owner 2026-10-07). «Elabora documenti» reads
// the plan from the documents; then each meal of the day with its proposal and alternatives, the week's groups
// against the frequencies, the plan's rules, and the reminders at meal times (on/off, the times).
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { mealCard, mealTitle } from "../diet.js";

const GROUP = { pesce: "🐟", carne_bianca: "🍗", carne_rossa: "🥩", uova: "🥚", formaggi: "🧀", affettati: "🥓", legumi: "🫘" };
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export async function renderDiet(box) {
  let day = box.dataset.day || iso(new Date());
  let v;
  try { v = await call(`/v1/aurora/diet?day=${day}`); } catch (e) { box.replaceChildren(el("p", "warn", e.message)); return; }
  const again = () => renderDiet(box);
  const out = el("span", "muted");
  const go = el("button", "primary", `🧠 ${t(v.plan ? "diet.process_again" : "diet.process")}`);
  go.type = "button";
  go.disabled = !v.documents;
  go.addEventListener("click", async () => {
    go.disabled = true;
    out.textContent = t("diet.processing");
    try {
      const r = await call("/v1/aurora/diet/process", { method: "POST" });
      out.textContent = t("diet.processed", { n: r.plan.options.length, f: Object.keys(r.plan.frequencies).length, s: r.seconds });
      setTimeout(again, 1500);
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); go.disabled = false; }
  });
  const head = el("div", "diet-head");
  head.append(go, out);
  const parts = [head];
  if (!v.plan) {
    parts.push(el("p", "muted", t(v.documents ? "diet.none_yet" : "diet.no_docs")));
    box.replaceChildren(...parts);
    return;
  }
  const p = v.plan;
  const when = new Date(p.processed_at * 1000).toLocaleDateString();
  parts.push(el("p", "muted", t("diet.from", { src: p.source, when, n: p.options.length })));
  if (v.stale) parts.push(el("p", "warn", `⚠️ ${t("diet.stale")}`));

  // the day: ‹ date ›, each meal
  const nav = el("div", "diet-nav");
  const shift = (n) => { const d = new Date(`${day}T12:00`); d.setDate(d.getDate() + n); box.dataset.day = iso(d); again(); };
  const prev = el("button", "", "‹"), next = el("button", "", "›"), today = el("button", "link", t("diet.today"));
  [prev, next, today].forEach((b) => { b.type = "button"; });
  prev.addEventListener("click", () => shift(-1));
  next.addEventListener("click", () => shift(1));
  today.addEventListener("click", () => { delete box.dataset.day; again(); });
  const label = new Date(`${day}T12:00`).toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
  nav.append(prev, el("strong", "", label), next, today);
  parts.push(nav);
  const meals = el("div", "diet-meals");
  for (const s of v.meals) meals.append(mealCard(s, again));
  parts.push(meals);

  // the week against the frequencies: a chip per group, its state said in words and icon, not by colour alone
  const freq = p.frequencies || {};
  if (Object.keys(freq).length) {
    const week = el("div", "diet-week");
    week.append(el("h4", "", t("diet.week")));
    for (const [g, f] of Object.entries(freq)) {
      const n = v.week[g] || 0;
      const state = n > f.max ? "over" : n >= f.min ? "ok" : "under";
      const chip = el("span", `diet-chip ${state}`, `${GROUP[g] || "•"} ${t(`diet.group.${g}`)} ${n}/${f.min === f.max ? f.min : `${f.min}–${f.max}`} ${state === "ok" ? "✓" : state === "over" ? "⚠️" : ""}`);
      chip.title = t(`diet.state.${state}`);
      week.append(chip);
    }
    if (p.free_meals_per_week) week.append(el("span", "diet-chip", `🍕 ${t("diet.free")} ${v.week.libero || 0}/${p.free_meals_per_week}`));
    parts.push(week);
  }
  if (p.rules?.length || p.limits?.length) {
    const r = el("details", "report");
    r.append(el("summary", "", `📋 ${t("diet.rules")}`));
    const ul = el("ul");
    for (const l of p.limits || []) ul.append(el("li", "", t("diet.limit", { what: l.what, n: l.max, per: t(`diet.per.${l.per}`) })));
    for (const x of p.rules || []) ul.append(el("li", "", x));
    r.append(ul, el("div", "muted", t("diet.rules_hint")));
    parts.push(r);
  }

  // the reminders: on/off and the time of each meal the plan has
  const rem = el("details", "report diet-rem");
  rem.append(el("summary", "", `🔔 ${t("diet.reminders")}: ${t(v.reminders ? "diet.on" : "diet.off")}`));
  const on = el("input");
  on.type = "checkbox";
  on.checked = v.reminders;
  const lab = el("label", "");
  lab.append(on, ` ${t("diet.reminders_on")}`);
  rem.append(lab);
  const times = {};
  for (const s of v.meals) {
    const i = el("input");
    i.type = "time";
    i.value = v.times[s.meal] || "";
    times[s.meal] = i;
    const row = el("label", "diet-time");
    row.append(el("span", "", mealTitle(s.meal)), i);
    rem.append(row);
  }
  const save = el("button", "", t("diet.save"));
  save.type = "button";
  const said = el("span", "muted");
  save.addEventListener("click", async () => {
    const spec = Object.entries(times).filter(([, i]) => i.value).map(([m, i]) => `${m}=${i.value}`).join(",");
    try {
      await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify({ AURORA_DIET_REMINDERS: on.checked ? "true" : "false", AURORA_DIET_TIMES: spec }) });
      said.textContent = t("diet.saved");
    } catch (e) { said.textContent = t("ev.error", { m: e.message }); }
  });
  rem.append(el("p", "muted", t("diet.reminders_hint")), save, said);
  parts.push(rem);
  box.replaceChildren(...parts);
}

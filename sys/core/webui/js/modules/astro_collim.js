// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → ⭕ Collimation (owner, 2026-10-19: «una tab specifica nella sezione astro dedicata alla collimazione così
// almeno ho una parte dedicata e aurora la può sfruttare durante le sessioni»): 1. the collimator's picture read by the
// server (ast_ocal), drawn back with what was found; 2. the defocused star taken by N.I.N.A., the screws learned and
// which to turn (ast_donut); 3. a night's stars across the field (ast_stars). The last of each is what the chat reads.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { datePicker } from "../dates.js";
import { liveCard } from "./astro_collim_live.js";

const MARK = { true: "✅", false: "⚠️", null: "ℹ️" };
const TURNS = ["1/16", "1/8", "1/4", "3/8", "1/2", "1"];

function verdicts(list) {
  const ul = el("ul", "an-findings");
  for (const v of list || []) ul.append(el("li", "", `${MARK[v.ok] ?? "•"} ${v.text}`));
  return ul;
}

function photoCard(state) {
  const c = el("section", "astro-card wide");
  c.append(el("h4", "", `📷 ${t("col.photo")}`), el("p", "muted", t("col.photo_hint")));
  const out = el("div");
  const pick = el("input");
  pick.type = "file";
  pick.accept = "image/*";
  pick.hidden = true;
  const btn = el("button", "approve", `📎 ${t("col.photo_pick")}`);
  btn.addEventListener("click", () => pick.click());
  pick.addEventListener("change", async () => {
    const f = pick.files[0];
    if (!f) return;
    out.replaceChildren(el("p", "muted", t("col.reading")));
    try {
      const r = await call("/v1/aurora/astro/collimation/photo", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: f });
      if (r.error) { out.replaceChildren(el("p", "warn", r.error)); return; }
      const img = el("img", "col-pic");
      img.src = r.image;
      img.alt = t("col.photo");
      out.replaceChildren(verdicts(r.verdict), img, el("p", "muted", t("col.legend")));
    } catch (e) { out.replaceChildren(el("p", "warn", e.message)); }
    pick.value = "";
  });
  c.append(btn, pick, out);
  if (state.photo) out.append(el("p", "muted", t("col.last", { d: new Date(state.photo.at * 1000).toLocaleString() })), verdicts(state.photo.verdict));
  return c;
}

function starCard(state) {
  const c = el("section", "astro-card wide");
  c.append(el("h4", "", `⭐ ${t("col.star")}`), el("p", "muted", t("col.star_hint")));
  const exp = el("input");
  exp.type = "number";
  exp.min = "0.1";
  exp.step = "0.5";
  exp.value = "3";
  exp.className = "col-num";
  const out = el("p", "col-say");
  const go = el("button", "primary", `📸 ${t("col.measure")}`);
  const run = async (extra) => {
    out.textContent = t("col.shooting");
    try {
      const r = await call("/v1/aurora/astro/collimation/star", { method: "POST", body: JSON.stringify({ exposure_s: Number(exp.value) || 3, ...extra }) });
      out.textContent = [r.learned ? `🧠 ${r.learned}` : "", r.say].filter(Boolean).join("\n");
      if (r.learned) learned.replaceChildren(...screwList({ ...state.screws, [extra.learned_screw]: [0, 0] }));
    } catch (e) { out.textContent = e.message; }
  };
  go.addEventListener("click", () => run({}));
  const row = el("div", "col-row");
  row.append(el("label", "", t("col.exposure")), exp, go);
  // learning a screw: its name as the person calls it, how much it was turned and which way
  const name = el("input");
  name.placeholder = t("col.screw_name");
  const amount = el("select");
  for (const a of TURNS) amount.append(new Option(a, a));
  amount.value = "1/8";
  const way = el("select");
  way.append(new Option(t("col.cw"), "orario"), new Option(t("col.ccw"), "antiorario"));
  const learn = el("button", "approve", `🧠 ${t("col.learn")}`);
  learn.addEventListener("click", () => {
    if (!name.value.trim()) { name.focus(); return; }
    run({ learned_screw: name.value.trim(), turned: `${amount.value} ${way.value}` });
  });
  const lrow = el("div", "col-row");
  lrow.append(el("label", "", t("col.turned")), name, amount, way, learn);
  const learned = el("ul", "an-findings");
  learned.append(...screwList(state.screws));
  c.append(row, out, el("h5", "", t("col.screws")), el("p", "muted", t("col.learn_hint")), lrow, learned);
  if (state.star) out.textContent = state.star.say;
  return c;
}

function screwList(screws) {
  const names = Object.keys(screws || {});
  return names.length ? names.map((n) => el("li", "", `🔩 ${n}`)) : [el("li", "muted", t("col.no_screws"))];
}

function starsCard(state) {
  const c = el("section", "astro-card wide");
  c.append(el("h4", "", `🌌 ${t("col.field")}`), el("p", "muted", t("col.field_hint")));
  const date = datePicker();
  const go = el("button", "primary", `🔎 ${t("col.field_go")}`);
  const out = el("pre", "col-text");
  go.addEventListener("click", async () => {
    out.textContent = t("col.reading");
    try {
      const r = await call(`/v1/aurora/astro/collimation/stars?date=${encodeURIComponent(date.value || "")}`);
      out.textContent = r.error || r.text;
    } catch (e) { out.textContent = e.message; }
  });
  const row = el("div", "col-row");
  row.append(el("label", "", t("col.night")), date.el, go);
  c.append(row, out);
  if (state.stars) out.textContent = state.stars.text;
  return c;
}

export async function collimTab(box) {
  box.replaceChildren(el("p", "muted", t("col.hint")));
  let state = {};
  try { state = await call("/v1/aurora/astro/collimation"); } catch (e) { box.append(el("p", "warn", e.message)); }
  const cards = el("div", "astro-cards");
  cards.append(liveCard(state.scope), photoCard(state), starCard(state), starsCard(state));
  box.append(cards);
}

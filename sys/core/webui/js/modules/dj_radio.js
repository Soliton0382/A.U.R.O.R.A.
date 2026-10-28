// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📻 Internet radio (aud_radio; owner, 28 Oct: «io però non ho premium… qualche radio internet che possiamo
// sfruttare?»): the genres as buttons, a search by name, the stations found with ▶ (played in the player, through
// Aurora, with its visualiser) and ☆ to keep one; the stations kept first.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

export function radioPanel(play) {
  const box = el("details", "report dj-radio");
  box.append(el("summary", "", `📻 ${t("dj.radio.title")}`), el("p", "muted", t("dj.radio.hint")));
  const presets = el("div", "dj-radio-presets");
  const form = el("form", "dj-radio-search");
  const q = el("input");
  q.placeholder = t("dj.radio.ph");
  const go = el("button", "", "🔎");
  go.type = "submit";
  form.append(q, go);
  const kept = el("div", "dj-radio-kept");
  const found = el("ol", "dj-radio-list");
  const out = el("p", "muted");
  box.append(presets, form, kept, out, found);
  let mine = [];

  const row = (s) => {
    const li = el("li");
    const p = el("button", "", "▶");
    p.type = "button";
    p.title = t("dj.radio.play");
    p.addEventListener("click", () => play(`/v1/aurora/radio/${s.id}/stream`, `📻 ${s.name}`));
    const on = mine.some((m) => m.id === s.id);
    const star = el("button", "", on ? "★" : "☆");
    star.type = "button";
    star.title = t(on ? "dj.radio.unkeep" : "dj.radio.keep");
    star.addEventListener("click", async () => {
      try { mine = (await call("/v1/aurora/radio/favourites", { method: "POST", body: JSON.stringify({ station: s, on: !on }) })).favourites; show(); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
    const info = [s.tags && s.tags.split(",").slice(0, 3).join(", "), s.country, s.codec && `${s.codec}${s.bitrate ? ` ${s.bitrate}k` : ""}`].filter(Boolean).join(" · ");
    li.append(p, star, el("strong", "", ` ${s.name}`), el("span", "muted", info ? ` — ${info}` : ""));
    return li;
  };
  let last = [];
  const show = () => {
    kept.replaceChildren(...(mine.length ? [el("strong", "", `★ ${t("dj.radio.kept")}`), el("ol", "dj-radio-list")] : []));
    if (mine.length) kept.lastChild.append(...mine.map(row));
    found.replaceChildren(...last.map(row));
  };
  const look = async (params, label) => {
    out.textContent = `✻ ${t("dj.radio.looking")}`;
    try {
      last = (await call(`/v1/aurora/radio/search?${new URLSearchParams(params)}`)).stations;
      out.textContent = t("dj.radio.found", { n: last.length, what: label });
      show();
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); if (q.value.trim()) look({ q: q.value.trim() }, q.value.trim()); });
  call("/v1/aurora/radio").then((s) => {
    mine = s.favourites;
    for (const p of s.presets) {
      const b = el("button", "", p.label);
      b.type = "button";
      b.addEventListener("click", () => look({ tag: p.tag }, p.label));
      presets.append(b);
    }
    show();
  }).catch(() => {});
  return box;
}

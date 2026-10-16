// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → 🌌 Tonight (ROADMAP N30): the night (astronomical dark, the Moon, the forecast) and the whole catalogue
// ranked by the hours each object can be taken with the person's equipment (ast_skyplan); a row opens that object's
// night hour by hour. The catalogue is fetched by the server on the first ask (a few seconds, once).
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const KINDS = ["", "narrowband", "broadband", "hdr", "galaxy"];
const COLS = ["n", "name", "type", "size", "hours", "max", "moon", "fit", "set"];
const pct = (x) => `${Math.round(x * 100)}%`;

function controls(box, run) {
  const row = el("div", "sky-controls");
  const date = el("input");
  date.type = "date";
  const kind = el("select");
  KINDS.forEach((k) => { const o = el("option", "", t(`sky.kind.${k || "all"}`)); o.value = k; kind.append(o); });
  const alt = el("input");
  alt.type = "number"; alt.min = "0"; alt.max = "80"; alt.value = "30"; alt.title = t("sky.min_alt");
  const go = el("button", "btn", `🔭 ${t("sky.go")}`);
  go.type = "button";
  go.addEventListener("click", () => run({ date: date.value, kind: kind.value, min_alt: alt.value }));
  row.append(el("label", "", t("sky.date")), date, el("label", "", t("sky.kind")), kind,
    el("label", "", t("sky.min_alt")), alt, go);
  box.append(row);
}

function nightCard(d) {
  const n = d.night;
  const card = el("div", "sky-night");
  const lines = [`📍 ${d.site.lat}, ${d.site.lon} (${d.site.from}) · ${d.date}`];
  if (!n.dusk) lines.push(t("sky.never_dark"));
  else {
    lines.push(`🌑 ${t("sky.dark", { from: n.dusk, to: n.dawn, h: n.dark_h })}`);
    lines.push(`🌙 ${t("sky.moon", { lit: pct(n.moon_lit), h: n.moon_up_dark_h })}`);
    if (n.cloud_mean != null) lines.push(`☁️ ${t("sky.clouds", { c: n.cloud_mean, h: n.clear_dark_h })}`);
    if (n.seeing.length) lines.push(`👁️ ${n.seeing.map((s) => `${s.at} ${s.seeing} · T${s.transparency}`).join(" · ")}`);
    if (n.forecast_errors.length) lines.push(`⚠️ ${n.forecast_errors.join(", ")}`);
  }
  if (d.field) lines.push(`🖼️ ${t("sky.field", { w: d.field.w_deg, h: d.field.h_deg, s: d.field.scale })}`);
  lines.forEach((x) => card.append(el("div", "", x)));
  if (d.clouds_ignored) card.append(el("div", "warn", `⚠️ ${t("sky.clouds_ignored")}`));
  return card;
}

function hourly(d) {
  // the object's altitude through the night: one bar an hour, dark hours solid, the usable ones marked
  const wrap = el("div", "sky-hours");
  for (const h of d.hourly || []) {
    const bar = el("div", `sky-hour${h.usable ? " ok" : ""}${h.dark ? "" : " twilight"}`);
    bar.title = `${h.at} · ${h.alt}°` + (h.cloud != null ? ` · ☁️ ${h.cloud}%` : "") + ` · 🌙 ${h.moon_alt}°`;
    const fill = el("i");
    fill.style.height = `${Math.max(0, h.alt) / 90 * 100}%`;
    bar.append(fill, el("small", "", h.at.slice(0, 2)));
    wrap.append(bar);
  }
  return wrap;
}

function table(d, open) {
  const tb = el("table", "an-table sky-table");
  const head = el("tr");
  for (const k of COLS) head.append(el("th", "", t(`sky.col.${k}`)));
  tb.append(head);
  d.targets.forEach((r, i) => {
    const tr = el("tr", "sky-row");
    const names = [...r.common, ...r.aliases].join(", ");
    const cells = [String(i + 1), `${r.name}${names ? ` · ${names}` : ""}`, `${r.type} · ${t(`sky.kind.${r.kind}`)}`,
      r.size_arcmin[0] ? `${r.size_arcmin[0]}′` : "—", `${r.hours} h${r.from ? ` · ${r.from}–${r.to}` : ""}`,
      `${r.max_alt}° · ${r.max_at}`, `${r.moon_sep}°`, r.fit.words, r.set || "—"];
    cells.forEach((c, k) => { const td = el("td", "", c); td.dataset.label = t(`sky.col.${COLS[k]}`); tr.append(td); });
    tr.title = t("sky.open");
    tr.addEventListener("click", () => open(r.name, tr));
    tb.append(tr);
  });
  const wrap = el("div", "an-wrap");
  wrap.append(tb);
  return wrap;
}

export async function skyTab(box) {
  if (box.dataset.ready) return;
  box.dataset.ready = "1";
  box.replaceChildren(el("p", "muted", t("sky.hint")));
  const out = el("div", "sky-out");
  const one = el("div", "sky-one");
  let last = {};
  // the object's night opens right under its row (a phone's list is long: at the bottom it was never seen)
  const open = async (name, row) => {
    const at = el("tr", "sky-detail");
    const cell = el("td");
    cell.colSpan = COLS.length;
    cell.append(one);
    at.append(cell);
    row.parentNode.querySelectorAll(".sky-detail").forEach((x) => x.remove());
    row.after(at);
    one.replaceChildren(el("p", "muted", `⏳ ${name}`));
    try {
      const q = new URLSearchParams({ ...last, object: name, limit: 1 });
      const d = await call(`/v1/aurora/astro/sky?${q}`);
      if (d.error) { one.replaceChildren(el("p", "warn", d.error)); return; }
      const r = d.targets[0];
      one.replaceChildren(el("h4", "", `🎯 ${r.name} · ${r.hours} h · ${r.fit.words}`), hourly(d));
      at.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) { one.replaceChildren(el("p", "warn", e.message)); }
  };
  const run = async (p = {}) => {
    last = Object.fromEntries(Object.entries(p).filter(([, v]) => v !== "" && v != null));
    out.replaceChildren(el("p", "muted", `⏳ ${t("sky.wait")}`));
    one.replaceChildren();
    let d;
    try { d = await call(`/v1/aurora/astro/sky?${new URLSearchParams(last)}`); } catch (e) { out.replaceChildren(el("p", "warn", e.message)); return; }
    if (d.error && !d.night) { out.replaceChildren(el("p", "warn", d.error)); return; }
    out.replaceChildren(nightCard(d));
    if (d.targets?.length) out.append(table(d, open), el("p", "muted", t("sky.count", { n: d.candidates, of: d.catalogue })));
    else if (d.night.dusk) out.append(el("p", "muted", t("sky.none")));
  };
  controls(box, run);
  box.append(out, one);
  run();
}

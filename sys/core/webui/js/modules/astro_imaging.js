// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → 🎯 Ripresa (ROADMAP N28; owner, 17 Oct: «per l'oggetto selezionato i valori ottimali di ripresa sarebbero
// X, Y, Z; in base alla tua libreria dark ti consiglio F, G, H… per gli HDR 1600 g, 20 o»): the object chosen and its
// settings — the best, and the best with the darks the person has — the sets for each kind of object, the sensor
// measured at each gain (with what PixInsight's SubframeSelector wants) and the sky of each filter (api/astro →
// ast_sensor). Nothing is set on the telescope's PC.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { settingsForm } from "./settings_form.js";

const n = (x, d = 2) => (x == null ? "—" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d }));
const set = (s) => (s ? `gain ${n(s.gain, 0)} · offset ${n(s.offset, 0)} · ${n(s.exposure_s, 0)} s` : "—");
const KINDS = ["narrowband", "broadband", "hdr"];

function kindBlock(k, v) {
  const box = el("div", "im-kind");
  box.append(el("h4", "", t(`im.k.${k}`)), el("p", "muted", t(`im.kh.${k}`)));
  if (k === "hdr") {
    box.append(el("p", "", v.exposures.length ? t("im.hdr", { g: n(v.gain, 0), o: n(v.offset, 0), e: v.exposures.map((x) => `${n(x, 0)} s`).join(" · "), l: v.lights_each })
      : t("im.hdr_none")));
    return box;
  }
  if (!v.best) {
    box.append(el("p", "warn", t(v.rate ? "im.no_sensor" : `im.no_sky.${k}`)));
    return box;
  }
  box.append(el("p", "", `⭐ ${t("im.best")}: ${set(v.best)}`),
    el("p", "muted", t("im.why", { tmin: v.best.t_min, floor: v.best.floor_s, rn: n(v.best.read_noise_e), sky: n(v.rate, 3), f: v.filters.join(", ") })));
  if (v.with_darks) {
    const same = v.with_darks.gain === v.best.gain && v.with_darks.offset === v.best.offset && v.with_darks.exposure_s === v.best.exposure_s;
    box.append(el("p", "", `🌑 ${t("im.with_darks")}: ${set(v.with_darks)}${same ? " ✅" : ""}`));
    if (!same) box.append(el("p", "muted", t("im.make", { s: set(v.best) })));
  } else {
    box.append(el("p", "warn", `🌑 ${t("im.no_darks", { s: set(v.best) })}`));
  }
  return box;
}

function sensorTable(d) {
  const wrap = el("div", "an-wrap");
  const table = el("table", "an-table");
  const head = el("tr");
  for (const k of ["gain", "offset", "eadu", "rn", "fw", "bias", "zero", "date"]) head.append(el("th", "", t(`im.c.${k}`)));
  table.append(head);
  for (const s of d.sensors) {
    const tr = el("tr");
    [n(s.gain, 0), n(s.offset, 0), n(s.gain_e_adu, 3), `${n(s.read_noise_e)} e⁻`, `${n(s.full_well_e / 1000, 1)} ke⁻`, `${n(s.bias_adu, 0)} ADU`,
      s.zero_share > 0.0001 ? `⚠️ ${n(s.zero_share * 100, 2)} %` : "✅ 0", s.date].forEach((x) => tr.append(el("td", "", x)));
    table.append(tr);
  }
  wrap.append(table);
  const box = el("div");
  box.append(wrap);
  for (const s of d.sensors) {
    box.append(el("p", "muted", `🧪 PixInsight → SubframeSelector (gain ${n(s.gain, 0)}): ${t("im.sfs", { g: n(s.gain_e_adu, 3) })}`));
  }
  return box;
}

function skyTable(d) {
  const ul = el("ul", "an-findings");
  for (const s of d.sky) {
    const per = Object.entries(s.e_s).map(([c, v]) => `${c} ${n(v, 3)}`).join(" · ");
    ul.append(el("li", "", `🌌 ${s.filter || "—"} · ${s.date} · ${n(s.exposure_s, 0)} s · ${per} e⁻/s/px (${t("im.weakest")} ${s.weakest})`));
  }
  if (!d.sky.length) ul.append(el("li", "muted", t("im.sky_none")));
  return ul;
}

export async function imagingTab(box, object = "") {
  box.replaceChildren(el("p", "muted", "…"));
  let d;
  try { d = await call(`/v1/aurora/astro/imaging${object ? `?object=${encodeURIComponent(object)}` : ""}`); }
  catch (e) { box.replaceChildren(el("p", "warn", e.message)); return; }
  box.replaceChildren(el("p", "muted", t("im.hint")));
  if (!d.frames_dir) {
    settingsForm(["AURORA_ASTRO_FRAMES_DIR"], { title: `🗂️ ${t("im.frames_dir")}`, onSaved: () => imagingTab(box, object) })
      .then((f) => box.append(f)).catch(() => {});
  }
  // the object: one of the sequences', or any name written
  const pick = el("div", "im-pick");
  const input = el("input");
  Object.assign(input, { value: object, placeholder: t("im.object_ph") });
  input.setAttribute("list", "im-objects");
  const list = el("datalist");
  list.id = "im-objects";
  for (const o of d.objects || []) { const op = el("option"); op.value = o; list.append(op); }
  const go = el("button", "btn", `🎯 ${t("im.go")}`);
  go.type = "button";
  go.addEventListener("click", () => imagingTab(box, input.value.trim()));
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") go.click(); });
  pick.append(input, list, go);
  box.append(el("h3", "setting-cat", `🎯 ${t("im.object")}`), pick);
  if (d.object) {
    const o = d.object, k = d.kinds[o.kind];
    const sel = el("select");
    for (const c of KINDS) { const op = el("option", "", t(`im.k.${c}`)); op.value = c; sel.append(op); }
    sel.value = o.kind;
    sel.addEventListener("change", () => call("/v1/aurora/astro/imaging", { method: "PUT", body: JSON.stringify({ object: o.name, kind: sel.value }) })
      .then(() => imagingTab(box, o.name)).catch((e) => box.prepend(el("p", "warn", e.message))));
    const row = el("p", "");
    row.append(`${o.name}: `, sel, el("span", "muted", o.guessed ? ` ${t("im.guessed")}` : ""));
    box.append(row, kindBlock(o.kind, k));
  }
  box.append(el("h3", "setting-cat", `📦 ${t("im.sets")}`), el("p", "muted", t("im.overhead", { o: d.overhead_s, f: d.floor_s })));
  for (const k of KINDS) box.append(kindBlock(k, d.kinds[k]));
  box.append(el("h3", "setting-cat", `📷 ${t("im.sensor")}`));
  box.append(d.sensors.length ? sensorTable(d) : el("p", "muted", t("im.sensor_none")));
  if (d.missing_gains?.length) box.append(el("p", "warn", t("im.missing", { g: d.missing_gains.map((x) => n(x, 0)).join(", ") })));
  box.append(el("p", "muted", t("im.how")));
  box.append(el("h3", "setting-cat", `🌌 ${t("im.sky")}`), skyTable(d));
  for (const e of d.errors || []) box.append(el("p", "warn", e));
}

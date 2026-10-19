// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → 📜 the nights already guided (ROADMAP N28): PHD2's guide logs of the astro folder read back by the API
// (ast_guidelog): each night's sessions with their RMS, and what Aurora reads in them — said in words here, from the
// codes and numbers the server sends. Observations and proposals: nothing is changed on the telescope's PC.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { fmtDate } from "../dates.js";

const ICON = { high: "🛑", mid: "⚠️", low: "💡" };
const f = (x, d = 2) => (x == null ? "—" : Number(x).toFixed(d));

function finding(x) {
  const k = `an.f.${x.code}`;
  if (x.min != null) x = { ...x, mm: Math.abs(x.min), side: t(x.min < 0 ? "an.before" : "an.after") };
  let s = t(k, x);
  if (x.code === "runaway_meridian" && x.flip_after != null) s += ` ${t("an.f.flip_hint", x)}`;
  return el("li", `an-${x.level}`, `${ICON[x.level] || "•"} ${x.at ? `${x.at} · ` : ""}${s}`);
}

function sessions(n, scale) {
  const wrap = el("div", "an-wrap");
  const table = el("table", "an-table");
  const head = el("tr");
  for (const k of ["start", "min", "ra", "dec", "total", "snr", "lost", "dither", "exp", "pier"]) head.append(el("th", "", t(`an.col.${k}`)));
  table.append(head);
  for (const s of n.sessions) {
    const r = s.rms, tr = el("tr", s.assistant ? "muted" : "");
    const ok = scale && r.total != null ? (r.total <= scale ? "✅ " : "⚠️ ") : "";
    const cells = [s.start.slice(11, 16) + (s.assistant ? " 🧪" : ""), f(s.minutes, 0), `${f(r.ra)}″`, `${f(r.dec)}″`,
      `${ok}${f(r.total)}″`, f(s.snr, 0), String(s.lost), String(s.dithers),
      s.settings.exposure_ms ? `${s.settings.exposure_ms} ms` : "—", s.settings.pier || "—"];
    cells.forEach((c) => tr.append(el("td", "", c)));
    table.append(tr);
  }
  wrap.append(table);
  return wrap;
}

function night(n, scale, open) {
  const d = el("details", "an-night");
  d.open = open;
  const minutes = n.sessions.filter((s) => !s.assistant).reduce((a, s) => a + s.minutes, 0);
  const best = Math.min(...n.sessions.filter((s) => !s.assistant && s.minutes >= 10 && s.rms.total != null).map((s) => s.rms.total));
  const worst = n.findings.reduce((a, x) => (a === "high" || x.level === "high" ? "high" : x.level === "mid" ? "mid" : a), "");
  d.append(el("summary", "", `${ICON[worst] || "✅"} ${fmtDate(n.night)} · ${t("an.guided", { m: f(minutes, 0) })}` +
    (Number.isFinite(best) ? ` · ${t("an.best", { r: f(best) })}` : "") + ` · ${n.file}`));
  d.append(el("h4", "", `👁️ ${t("an.seen")}`));
  const ul = el("ul", "an-findings");
  ul.append(...(n.findings.length ? n.findings.map(finding) : [el("li", "muted", t("an.nothing"))]));
  d.append(ul);
  if (n.advice_from && n.advice_from !== n.night) d.append(el("p", "muted", t("an.advice_from", { d: n.advice_from })));
  d.append(sessions(n, scale));
  const cal = n.calibrations.map((c) => `${c.axis} ${f(c.rate, 2)} px/s, ${f(c.angle, 1)}°`).join(" · ");
  if (cal) d.append(el("p", "muted", `🎯 ${t("an.calibration")}: ${cal}`));
  return d;
}

export async function nightsTab(box) {
  box.replaceChildren(el("p", "muted", t("an.hint")));
  let d;
  try { d = await call("/v1/aurora/astro/nights"); } catch (e) { box.append(el("p", "warn", e.message)); return; }
  if (!d.nights.length) { box.append(el("p", "muted", t("an.none"))); return; }
  if (d.scale) box.append(el("p", "muted", t("an.scale", { s: f(d.scale) })));
  d.nights.forEach((n, i) => box.append(night(n, d.scale, i === 0)));
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → 📈 the guiding live (ROADMAP N28; owner, 2026-10-16: «grafici stile PHD2, quello che sta facendo Aurora
// per risolvere i problemi di inseguimento»): PHD2's guide steps read from its own event server (api/astro, ast_phd2:
// read only), drawn as PHD2 draws them — RA blue, DEC red, in arcseconds, the corrections as bars underneath — with
// the RMS, the events that matter, and what Aurora sees in them. Asked every 2 s while the tab is in sight.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { tunerBox } from "./astro_tuner.js";
import { mountBox } from "./astro_mount.js";
import { shootBox } from "./astro_shoot.js";

const RA = "#4aa3ff", DEC = "#ff6b6b";
const f = (x, d = 2) => (x == null ? "—" : Number(x).toFixed(d));

function draw(canvas, steps) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const g = canvas.getContext("2d");
  g.scale(dpr, dpr);
  const css = getComputedStyle(document.body);
  const line = css.getPropertyValue("--line").trim() || "rgba(255,255,255,.2)";
  const muted = css.getPropertyValue("--muted").trim() || "#999";
  g.clearRect(0, 0, w, h);
  const plot = h * 0.78, bars = h - plot;              // the errors above, the corrections below (PHD2's way)
  const peak = Math.max(2, ...steps.map((s) => Math.max(Math.abs(s.ra), Math.abs(s.dec))));
  const y = (v) => plot / 2 - (v / peak) * (plot / 2 - 6);
  g.strokeStyle = line;
  g.lineWidth = 1;
  g.fillStyle = muted;
  g.font = "11px sans-serif";
  for (const v of [-peak, -peak / 2, 0, peak / 2, peak]) {        // the grid in arcseconds
    g.beginPath(); g.moveTo(34, y(v)); g.lineTo(w, y(v)); g.stroke();
    g.fillText(`${v > 0 ? "+" : ""}${v.toFixed(1)}″`, 0, y(v) + 4);
  }
  if (!steps.length) return;
  const x = (i) => 34 + (i / Math.max(1, steps.length - 1)) * (w - 38);
  const maxMs = Math.max(200, ...steps.map((s) => Math.max(Math.abs(s.ra_ms), Math.abs(s.dec_ms))));
  steps.forEach((s, i) => {                            // the corrections, RA above the middle of the band, DEC below
    const mid = plot + bars / 2, k = (bars / 2 - 2) / maxMs;
    g.fillStyle = RA; g.fillRect(x(i) - 1, mid - Math.max(0, s.ra_ms * k), 2, Math.abs(s.ra_ms * k));
    g.fillStyle = DEC; g.fillRect(x(i) + 1, mid, 2, Math.abs(s.dec_ms * k));
  });
  for (const [key, color] of [["ra", RA], ["dec", DEC]]) {
    g.strokeStyle = color;
    g.lineWidth = 1.6;
    g.beginPath();
    steps.forEach((s, i) => (i ? g.lineTo(x(i), y(s[key])) : g.moveTo(x(i), y(s[key]))));
    g.stroke();
  }
}

// what Aurora reads in the steps, in words — observations, never a change (proposals come with the owner's limits)
function seen(d, imaging) {
  const out = [], s = d.steps, r = d.rms;
  if (!s.length) return out;
  if (r.total != null && imaging) {
    out.push(r.total <= imaging ? t("al.good", { r: f(r.total), s: f(imaging) }) : t("al.over", { r: f(r.total), s: f(imaging) }));
  }
  const last = s.slice(-60);
  const meanDec = last.reduce((a, b) => a + b.dec, 0) / last.length;
  if (r.dec && Math.abs(meanDec) > Math.max(0.3, r.dec * 0.8)) out.push(t("al.dec_drift", { m: f(meanDec) }));
  if (r.ra && r.dec && r.ra > 2 * r.dec) out.push(t("al.ra_high"));
  const lost = d.events.filter((e) => e.event === "StarLost").length;
  if (lost) out.push(t("al.lost", { n: lost }));
  const snr = s[s.length - 1].snr;
  if (snr != null && snr < 10) out.push(t("al.snr", { v: f(snr, 0) }));
  return out;
}

export function liveTab(box, imagingScale) {
  // one screen, in blocks (owner, 20 Oct: «tutto sotto controllo in una unica videata… la pagina comincia ad essere
  // incasinata»): the shooting first, then the guiding, the mount, the tuner; the events folded away
  box.innerHTML = `<p class="muted" data-i18n="al.hint"></p>
    <section class="al-sec"><h3>📸 <span data-i18n="sh.title"></span></h3><div class="al-shoot"></div></section>
    <section class="al-sec"><h3>🧭 <span data-i18n="al.guide"></span></h3><div class="al-state"></div>
      <div class="al-tiles"></div><canvas class="al-chart" aria-label="guiding"></canvas>
      <div class="al-legend"><span style="color:${RA}">━ RA</span> <span style="color:${DEC}">━ DEC</span></div>
      <h4>👁️ <span data-i18n="al.seen"></span></h4><ul class="al-seen"></ul>
      <details class="al-more"><summary>📋 <span data-i18n="al.events"></span></summary><div class="al-events"></div></details></section>
    <section class="al-sec"><h3>🔭 <span data-i18n="am.title"></span></h3><div class="al-mount"></div></section>
    <section class="al-sec"><div class="al-tuner"></div></section>`;
  box.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  let timer = null, ticks = 0;
  const tuner = tunerBox(box.querySelector(".al-tuner"));
  const shoot = shootBox(box.querySelector(".al-shoot"));
  const mount = mountBox(box.querySelector(".al-mount"), shoot.update);
  const tick = async () => {
    let d;
    try { d = await call("/v1/aurora/astro/live"); } catch (e) { box.querySelector(".al-state").textContent = e.message; return; }
    const st = box.querySelector(".al-state");
    st.className = `al-state ${d.connected ? "ok" : "warn"}`;
    st.textContent = d.connected ? t("al.connected", { h: d.host, v: d.version || "?", s: d.state || "—" })
      : t("al.not_connected", { h: d.host || "?", e: d.error || "" });
    const r = d.rms || {};
    const tile = (k, v, c = "") => { const x = el("div", "al-tile"); x.append(el("small", "muted", k), el("strong", c, v)); return x; };
    box.querySelector(".al-tiles").replaceChildren(tile("RMS RA", `${f(r.ra)}″`), tile("RMS DEC", `${f(r.dec)}″`),
      tile(t("al.total"), `${f(r.total)}″`), tile(t("al.peak"), `${f(r.peak_ra)}″ / ${f(r.peak_dec)}″`),
      tile(t("al.scale"), d.scale ? `${f(d.scale)}″/px` : "—"), tile(t("al.steps"), String(r.n || 0)));
    draw(box.querySelector(".al-chart"), (d.steps || []).slice(-240));
    const s = seen(d, imagingScale);
    box.querySelector(".al-seen").replaceChildren(...(s.length ? s.map((x) => el("li", "", x)) : [el("li", "muted", t("al.nothing"))]));
    box.querySelector(".al-events").replaceChildren(...(d.events || []).slice().reverse().map((e) =>
      el("div", "muted", `${new Date(e.t * 1000).toLocaleTimeString()} · ${e.event}${e.Error || e.Msg ? ` — ${e.Error || e.Msg}` : ""}`)));
  };
  return {
    start() { if (!timer) { tick(); timer = setInterval(() => {
      // only while the tab is in sight: another page or tab, and nobody asks (the server stops its watcher by itself)
      if (document.visibilityState === "visible" && box.offsetParent !== null) {
        ++ticks;
        if (ticks % 2 === 0) tick();                           // PHD2 every 2 s
        if (ticks % 10 === 0) tuner.refresh();                 // the tuner's state every 10 s
        if (ticks % 4 === 0) mount.refresh();                  // camera, focuser, guider, sequence every 4 s
        else mount.where();                                    // where the mount points every second (owner, 17 Oct)
      }
    }, 1000); } },
    stop() { clearInterval(timer); timer = null; },
  };
}

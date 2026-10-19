// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → 📈 → 🔭 where the mount points (ROADMAP N28; owner, 16 Oct: «rappresentazione del telescopio e montatura
// che mostra dove sta puntando»): N.I.N.A.'s Advanced API read by the server (ast_nina, the site dropped). Two drawings:
// the German mount in 3D (astro_mount3d: the tube along the pointing, on its side of the pier, the counterweight
// opposite; drag to turn it) — and the sky, altitude and azimuth, with the meridian.
// Then the camera, the focuser, the guider and the sequence in one line each.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { mount3d } from "./astro_mount3d.js";

const f = (x, d = 1) => (x == null ? "—" : Number(x).toFixed(d));

function colors() {
  const css = getComputedStyle(document.body);
  return { line: css.getPropertyValue("--line").trim() || "rgba(255,255,255,.25)", ink: css.getPropertyValue("--text").trim() || "#ddd",
    muted: css.getPropertyValue("--muted").trim() || "#999", target: "#ff6b6b" };
}

function setup(canvas) {
  const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const g = canvas.getContext("2d");
  g.scale(dpr, dpr);
  g.clearRect(0, 0, w, h);
  g.font = "12px sans-serif";
  return { g, w, h };
}

// the sky from above: the horizon the outer ring, the zenith the centre, north up, east on the left (as on a planisphere)
export function drawSky(canvas, m) {
  const { g, w, h } = setup(canvas), c = colors();
  const cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2 - 18;
  g.strokeStyle = c.line; g.lineWidth = 1;
  for (const alt of [0, 30, 60]) { g.beginPath(); g.arc(cx, cy, r * (1 - alt / 90), 0, Math.PI * 2); g.stroke(); }
  g.setLineDash([4, 4]); g.beginPath(); g.moveTo(cx, cy - r); g.lineTo(cx, cy + r); g.stroke(); g.setLineDash([]);   // the meridian
  g.fillStyle = c.muted;
  for (const [s, x, y] of [["N", cx - 4, cy - r - 4], ["S", cx - 4, cy + r + 14], [t("am.e"), cx - r - 14, cy + 4], [t("am.w"), cx + r + 5, cy + 4]]) g.fillText(s, x, y);
  if (m.alt_deg == null || m.az_deg == null) return;
  const rr = r * (1 - Math.max(-10, m.alt_deg) / 90), az = (m.az_deg * Math.PI) / 180;
  const x = cx - Math.sin(az) * rr, y = cy - Math.cos(az) * rr;
  g.fillStyle = m.alt_deg < 0 ? c.muted : c.target;
  g.beginPath(); g.arc(x, y, 7, 0, Math.PI * 2); g.fill();
}

export function mountBox(box, onData = null) {   // onData: N.I.N.A.'s state, for the shooting box
  box.innerHTML = `<div class="am-state muted"></div>
    <div class="am-views"><figure><canvas class="am-mount" aria-label="mount"></canvas><figcaption data-i18n="am.mount"></figcaption></figure>
    <figure><canvas class="am-sky" aria-label="sky"></canvas><figcaption data-i18n="am.sky"></figcaption></figure></div>
    <ul class="am-lines"></ul>`;
  box.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  const draw3d = mount3d(box.querySelector(".am-mount"));
  // the drawing moves smoothly to each new position (asked every second): from what is shown to what was read, in
  // ~1 s; the hour angle the short way round; a flip (the other side of the pier) is shown at once
  let shown = null, goal = null, lat = 45, t0 = 0, raf = 0;
  const KEYS = ["ha_h", "dec_deg", "alt_deg", "az_deg"];
  const step = (now) => {
    const k = Math.min(1, (now - t0) / 950);
    const m = { ...goal };
    for (const key of KEYS) {
      if (shown[key] == null || goal[key] == null) continue;
      let d = goal[key] - shown[key];
      if (key === "ha_h") d = ((d + 36) % 24) - 12;
      if (key === "az_deg") d = ((d + 540) % 360) - 180;
      m[key] = shown[key] + d * k;
    }
    draw3d(m, lat);
    drawSky(box.querySelector(".am-sky"), m);
    if (k < 1) raf = requestAnimationFrame(step); else { shown = m; raf = 0; }
  };
  const moveTo = (m) => {
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    if (!shown || shown.pier !== m.pier || !m.connected) { shown = goal = m; draw3d(m, lat); drawSky(box.querySelector(".am-sky"), m); return; }
    if (KEYS.every((k) => shown[k] === m[k]) && shown.tracking === m.tracking && shown.slewing === m.slewing) return;   // still: no redraw
    goal = m;
    t0 = performance.now();
    raf = requestAnimationFrame(step);
  };
  const where = async () => {
    let d;
    try { d = await call("/v1/aurora/astro/nina/mount"); } catch { return; }
    if (d.reachable && d.mount) moveTo(d.mount);
  };
  const refresh = async () => {
    let d;
    try { d = await call("/v1/aurora/astro/nina"); } catch (e) { box.querySelector(".am-state").textContent = e.message; onData?.(null); return; }
    onData?.(d);
    const st = box.querySelector(".am-state");
    if (!d.reachable) { st.textContent = t("am.off", { e: d.error || "" }); return; }
    const m = d.mount || {};
    const what = m.parked ? t("am.parked") : m.slewing ? t("am.slewing") : m.tracking ? t("am.tracking") : t("am.stopped");
    st.textContent = `${what} · RA ${f(m.ra_h, 2)} h · Dec ${f(m.dec_deg)}° · ${t("am.ha")} ${f(m.ha_h, 2)} h · ${t("am.alt")} ${f(m.alt_deg)}° · ` +
      `${t("am.pier")} ${t(`am.pier.${m.pier || "unknown"}`)}${m.flip_h != null ? ` · ${t("am.flip", { m: Math.round(m.flip_h * 60) })}` : ""}`;
    lat = d.lat ?? 45;
    moveTo(m);
    const c = d.camera || {}, fo = d.focuser || {}, gu = d.guider || {}, sq = d.sequence || {};
    box.querySelector(".am-lines").replaceChildren(
      el("li", "", `📷 ${c.name || "—"}: ${c.state || "—"}`),
      el("li", "", `🎯 ${t("am.focuser")}: ${fo.position ?? "—"} · ${f(fo.temp_c)} °C${fo.moving ? ` · ${t("am.moving")}` : ""}`),
      el("li", "", `🧭 PHD2: ${gu.state || "—"}${gu.rms?.total ? ` · RMS ${f(gu.rms.total, 2)}″` : ""}`),
      el("li", "", `🗂️ ${t("am.sequence")}: ${sq.active ? sq.running.join(" › ") : t("am.idle")}`));
  };
  refresh();
  return { refresh, where };
}

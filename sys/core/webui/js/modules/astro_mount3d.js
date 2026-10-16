// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 the German equatorial mount in 3D (owner, 16 Oct: «più simile a come viene mostrato in ASIAIR… simile 3D»): a small
// renderer of its own on a 2D canvas — cylinders and boxes as shaded polygons, painted far to near — no library.
// The pose is the mount's own: the polar axis tilted by the latitude (whole degrees, from the profile), the tube along
// the pointing (hour angle, declination), on its side of the pier, the counterweight opposite. Drag to turn the view.
//
// World: x east, y north, z up. Equatorial: Ze the pole (0, cos φ, sin φ), Xe the meridian on the equator
// (0, −sin φ, cos φ), Ye = Ze × Xe = east; pointing d = cos δ cos H·Xe − cos δ sin H·Ye + sin δ·Ze (H > 0 west).
import { t } from "../i18n.js";

const V = {
  add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]], sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
  mul: (a, k) => [a[0] * k, a[1] * k, a[2] * k], dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  norm: (a) => { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; },
};

// the mount's pose: the pivot, the pole, the pointing, the side the tube sits on (unit vectors in the world)
export function pose(m, latDeg = 45) {
  const f = (latDeg * Math.PI) / 180;
  const Ze = [0, Math.cos(f), Math.sin(f)], Xe = [0, -Math.sin(f), Math.cos(f)], Ye = [1, 0, 0];
  const parked = m.parked || m.ha_h == null || Math.abs(m.dec_deg ?? 90) > 89.5;
  const H = ((parked ? 0 : m.ha_h) * 15 * Math.PI) / 180, D = ((parked ? 90 : m.dec_deg) * Math.PI) / 180;
  const d = V.add(V.add(V.mul(Xe, Math.cos(D) * Math.cos(H)), V.mul(Ye, -Math.cos(D) * Math.sin(H))), V.mul(Ze, Math.sin(D)));
  let w = V.cross(Ze, d);
  const side = m.pier === "west" ? -1 : 1;
  // at the pole the cross product vanishes: the home position, counterweight down (the tube's side along Xe)
  w = Math.hypot(...w) < 0.05 ? Xe : V.mul(V.norm(w), side);
  return { Ze, d, w, O: [0, 0, 1.15] };
}

function frame(axis) {                                  // two unit vectors across an axis
  const a = V.norm(axis), t = Math.abs(a[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  const u = V.norm(V.cross(a, t));
  return [u, V.cross(a, u)];
}

function cylinder(out, p0, p1, r, color, n = 14) {
  const ax = V.sub(p1, p0), [u, v] = frame(ax);
  const ring = (c) => Array.from({ length: n }, (_, i) => {
    const t = (i / n) * Math.PI * 2;
    return V.add(c, V.add(V.mul(u, Math.cos(t) * r), V.mul(v, Math.sin(t) * r)));
  });
  const a = ring(p0), b = ring(p1);
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const mid = V.mul(V.add(V.add(a[i], a[j]), V.add(b[i], b[j])), 0.25);
    const normal = V.norm(V.sub(mid, V.add(p0, V.mul(V.norm(ax), V.dot(V.sub(mid, p0), V.norm(ax))))));
    out.push({ pts: [a[i], a[j], b[j], b[i]], color, normal });
  }
  out.push({ pts: a.slice().reverse(), color, normal: V.mul(V.norm(ax), -1) });
  out.push({ pts: b, color, normal: V.norm(ax) });
}

function box(out, c, half, color) {
  const [hx, hy, hz] = half;
  const P = (x, y, z) => [c[0] + x * hx, c[1] + y * hy, c[2] + z * hz];
  const faces = [[[1, -1, -1], [1, 1, -1], [1, 1, 1], [1, -1, 1], [1, 0, 0]], [[-1, -1, -1], [-1, -1, 1], [-1, 1, 1], [-1, 1, -1], [-1, 0, 0]],
    [[-1, 1, -1], [-1, 1, 1], [1, 1, 1], [1, 1, -1], [0, 1, 0]], [[-1, -1, -1], [1, -1, -1], [1, -1, 1], [-1, -1, 1], [0, -1, 0]],
    [[-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1], [0, 0, 1]], [[-1, -1, -1], [-1, 1, -1], [1, 1, -1], [1, -1, -1], [0, 0, -1]]];
  for (const f of faces) out.push({ pts: f.slice(0, 4).map((q) => P(...q)), color, normal: f[4] });
}

// the scene: tripod, pier head, RA housing along the pole, DEC housing across, counterweight, the tube and its guide scope
export function scene(m, lat) {
  const { Ze, d, w, O } = pose(m, lat), out = [];
  const metal = [150, 156, 166], dark = [70, 74, 82], red = [178, 48, 48], white = [226, 230, 236], blue = [74, 163, 255];
  for (const a of [90, 210, 330]) {                      // the tripod: three legs from the head to the ground
    const r = (a * Math.PI) / 180;
    cylinder(out, [0, 0, 0.82], [Math.cos(r) * 0.75, Math.sin(r) * 0.75, 0], 0.035, dark, 6);
  }
  cylinder(out, [0, 0, 0.78], [0, 0, 0.95], 0.17, dark);
  box(out, [0, 0, 1.03], [0.11, 0.11, 0.08], metal);
  const top = V.add(O, V.mul(Ze, 0.22));
  cylinder(out, V.sub(O, V.mul(Ze, 0.18)), top, 0.11, red);                       // the RA housing along the pole
  const decC = V.add(top, V.mul(Ze, 0.05));
  cylinder(out, V.sub(decC, V.mul(w, 0.12)), V.add(decC, V.mul(w, 0.22)), 0.095, red);   // the DEC housing
  cylinder(out, V.sub(decC, V.mul(w, 0.12)), V.sub(decC, V.mul(w, 0.78)), 0.022, metal, 8);   // the counterweight shaft
  cylinder(out, V.sub(decC, V.mul(w, 0.5)), V.sub(decC, V.mul(w, 0.64)), 0.13, metal);     // the counterweight
  const C = V.add(decC, V.mul(w, 0.42));                                          // the tube's centre
  box(out, V.add(decC, V.mul(w, 0.25)), [0.06, 0.06, 0.06], dark);                // the saddle (an axis-aligned block)
  cylinder(out, V.sub(C, V.mul(d, 0.62)), V.add(C, V.mul(d, 0.78)), 0.17, white, 18);   // the tube (a Newtonian, fat)
  cylinder(out, V.add(C, V.mul(d, 0.7)), V.add(C, V.mul(d, 0.8)), 0.18, blue, 18);      // its front ring: where it points
  const g = V.add(C, V.mul(w, 0.25));                                             // the guide scope, on top of the tube
  cylinder(out, V.sub(g, V.mul(d, 0.2)), V.add(g, V.mul(d, 0.3)), 0.045, dark, 10);
  return out;
}

export function render(canvas, m, view = { yaw: -45, pitch: 18 }, lat = 45) {
  const dpr = window.devicePixelRatio || 1, W = canvas.clientWidth, Hh = canvas.clientHeight;
  canvas.width = W * dpr;
  canvas.height = Hh * dpr;
  const g = canvas.getContext("2d");
  g.scale(dpr, dpr);
  g.clearRect(0, 0, W, Hh);
  const y = (view.yaw * Math.PI) / 180, p = (view.pitch * Math.PI) / 180;
  // the camera looks at the mount's head from the south-east, a little above; drag turns yaw and pitch
  const cam = (q) => {
    const x0 = q[0], y0 = q[1], z0 = q[2] - 0.9;
    const x1 = x0 * Math.cos(y) - y0 * Math.sin(y), y1 = x0 * Math.sin(y) + y0 * Math.cos(y);
    const y2 = y1 * Math.cos(p) - z0 * Math.sin(p), z2 = y1 * Math.sin(p) + z0 * Math.cos(p);   // looking down by p
    return [x1, y2, z2];                                 // x right, y depth (into the screen), z up
  };
  const s = Math.min(W, Hh) * 0.3, dist = 5;
  const proj = (c) => { const k = dist / (dist + c[1]); return [W / 2 + c[0] * s * k, Hh * 0.5 - c[2] * s * k]; };
  const css = getComputedStyle(document.body), line = css.getPropertyValue("--line").trim() || "rgba(255,255,255,.2)";
  const muted = css.getPropertyValue("--muted").trim() || "#999";
  // the ground: a ring with the cardinal points
  g.strokeStyle = line; g.lineWidth = 1; g.beginPath();
  for (let i = 0; i <= 48; i++) {
    const a = (i / 48) * Math.PI * 2, q = proj(cam([Math.cos(a) * 1.1, Math.sin(a) * 1.1, 0]));
    i ? g.lineTo(...q) : g.moveTo(...q);
  }
  g.stroke();
  g.fillStyle = muted; g.font = "12px sans-serif";
  for (const [label, q] of [["N", [0, 1.25, 0]], ["S", [0, -1.25, 0]], [t("am.e"), [1.25, 0, 0]], [t("am.w"), [-1.25, 0, 0]]]) {
    const [x, yy] = proj(cam(q)); g.fillText(label, x - 4, yy + 4);
  }
  const light = V.norm([0.4, -0.6, 0.8]);
  const faces = scene(m, lat).map((f) => {
    const cs = f.pts.map(cam);
    return { f, cs, depth: cs.reduce((a, c) => a + c[1], 0) / cs.length };
  }).sort((a, b) => b.depth - a.depth);
  for (const { f, cs } of faces) {
    const n = cam(V.add(f.normal, [0, 0, 0.9]));         // the normal turned with the camera (a direction: no offset)
    if (n[1] > 0.05) continue;                            // facing away
    const k = 0.35 + 0.65 * Math.max(0, V.dot(V.norm(f.normal), light));
    g.fillStyle = `rgb(${f.color.map((c) => Math.round(c * k)).join(",")})`;
    g.beginPath();
    cs.forEach((c, i) => (i ? g.lineTo(...proj(c)) : g.moveTo(...proj(c))));
    g.closePath(); g.fill();
  }
}

// a canvas that draws the mount and turns with the pointer; returns draw(m, lat)
export function mount3d(canvas) {
  const view = { yaw: -45, pitch: 18 };
  let last = null, drag = null;
  canvas.style.touchAction = "none";
  canvas.addEventListener("pointerdown", (e) => { drag = [e.clientX, e.clientY]; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    view.yaw -= (e.clientX - drag[0]) * 0.5;
    view.pitch = Math.max(-5, Math.min(80, view.pitch + (e.clientY - drag[1]) * 0.4));
    drag = [e.clientX, e.clientY];
    if (last) render(canvas, last.m, view, last.lat);
  });
  canvas.addEventListener("pointerup", () => { drag = null; });
  return (m, lat) => { last = { m, lat }; render(canvas, m, view, lat); };
}

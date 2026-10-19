// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧠 The brain in 3D (owner, 2026-10-20: «creerei proprio il cervello 3d, al momento si spostano solo le sinapsi»):
// its own shape made thick from the side view the nodes live in, its surface lit, the nodes inside it at a depth that
// changes smoothly; held by a finger or the mouse it turns on two axes, let go it glides and comes back to the front.

// the brain's thickness at a point of its side view: half its width there (an ellipsoid a part, folds on the surface)
const BODY = { cx: 0.53, cy: 0.29, rx: 0.42, ry: 0.27, half: 0.36 };
export function halfWidth(x, y, lobe) {
  if (lobe === "stem") return 0.05;
  if (lobe === "cerebellum") {
    const d = ((x - 0.72) / 0.16) ** 2 + ((y - 0.58) / 0.1) ** 2;
    return 0.2 * Math.sqrt(Math.max(0.05, 1 - d));
  }
  const d = ((x - BODY.cx) / BODY.rx) ** 2 + ((y - BODY.cy) / BODY.ry) ** 2;
  return BODY.half * Math.sqrt(Math.max(0.04, 1 - d)) * (1 + 0.05 * Math.sin(x * 95) * Math.sin(y * 80));
}

// the surface: points of the outline on both sides (the hemispheres' outer faces), each with its normal for the light
function shellOf(lobeAt, TALL, step = 0.011) {
  const pts = [];
  for (let x = 0; x <= 1; x += step) {
    for (let y = 0; y <= TALL; y += step) {
      const lobe = lobeAt(x, y);
      if (!lobe) continue;
      const h = halfWidth(x, y, lobe), ex = lobe === "cerebrum" || !["stem", "cerebellum"].includes(lobe);
      const nx = ex ? (x - BODY.cx) / BODY.rx ** 2 : (x - 0.72) / 0.0256, ny = ex ? (y - BODY.cy) / BODY.ry ** 2 : (y - 0.58) / 0.01;
      for (const side of [-1, 1]) {
        const nz = side / Math.max(0.05, h) * 0.6;
        const l = Math.hypot(nx, ny, nz) || 1;
        pts.push([x, y, side * h, nx / l, ny / l, nz / l]);
      }
    }
  }
  return pts;
}

// the turn of one canvas: `W()` its width now; frame(ctx) moves the view and draws the body, proj the nodes' places
export function turnable(canvas, g, lobeAt, TALL, W) {
  // owner, 2026-10-20: «tieni premuto con il dito sul cellulare o con il mouse e lo sposti nei vari lati senza che le
  // animazioni si rompano»: a drag turns the view on two axes, a release lets it glide and come back to the front,
  // where the drawing behind fits again. Pulses and lights follow the turned nodes: they are drawn where the nodes are.
  if (!g.depth) {
    const cx = g.nodes.reduce((s, n) => s + n.x, 0) / g.nodes.length, cy = g.nodes.reduce((s, n) => s + n.y, 0) / g.nodes.length;
    g.centre = [cx, cy];
    // a depth that changes smoothly over the brain (a folded sheet inside it): nodes near each other stay near in
    // 3D, so their synapses stay short whatever the turn (a random side each crossed the brain from side to side)
    g.depth = g.nodes.map((n) => {
      const f = 0.55 * Math.sin(n.x * 11 + 1.3) * Math.cos(n.y * 13 - 0.4) + 0.3 * Math.sin(n.x * 23 + n.y * 17);
      return f * halfWidth(n.x, n.y, lobeAt(n.x, n.y));
    });
    g.shell = shellOf(lobeAt, TALL, W() < 360 ? 0.016 : 0.011);
  }
  const view = { yaw: 0, pitch: 0, vy: 0, vp: 0, held: false, shown: 1 };   // shown: the drawing behind, 0 … 1
  const proj = g.nodes.map(() => [0, 0, 1]);           // each node's place on the screen and its nearness (0.6 … 1.3)
  const LIGHT = [-0.35, -0.55, 0.76];                  // from the viewer's upper left
  const project = () => {
    const [cx, cy] = g.centre, cyw = Math.cos(view.yaw), syw = Math.sin(view.yaw);
    const cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
    g.nodes.forEach((n, i) => {
      const x = n.x - cx, y = n.y - cy, z = g.depth[i];
      const x1 = x * cyw + z * syw, z1 = -x * syw + z * cyw;           // around the vertical axis
      const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp;              // then around the horizontal one
      const near = 1 + z2 * 1.4;
      proj[i][0] = cx + x1; proj[i][1] = cy + y2; proj[i][2] = Math.max(0.6, Math.min(1.3, near));
    });
  };
  // the brain itself, turned with the nodes: its surface lit from the front, the far side faint
  const body = (ctx) => {
    const [cx, cy] = g.centre, cyw = Math.cos(view.yaw), syw = Math.sin(view.yaw);
    const cp = Math.cos(view.pitch), sp = Math.sin(view.pitch), s = Math.max(1.2, W() / 260);
    for (const [x0, y0, z0, nx, ny, nz] of g.shell) {
      const x = x0 - cx, y = y0 - cy;
      const x1 = x * cyw + z0 * syw, z1 = -x * syw + z0 * cyw, y2 = y * cp - z1 * sp;
      const mx = nx * cyw + nz * syw, mz1 = -nx * syw + nz * cyw, my = ny * cp - mz1 * sp, mz = ny * sp + mz1 * cp;
      const lit = Math.max(0, mx * LIGHT[0] + my * LIGHT[1] + mz * LIGHT[2]);
      const a = mz > 0 ? 0.06 + 0.3 * lit : 0.035;
      ctx.fillStyle = `rgba(${mz > 0 ? Math.round(120 + 110 * lit) : 90},${mz > 0 ? Math.round(140 + 100 * lit) : 105},${mz > 0 ? 235 : 170},${a})`;
      ctx.fillRect((cx + x1) * W() - s / 2, (cy + y2) * W() - s / 2, s, s);
    }
  };
  let grab = null;
  canvas.addEventListener("pointerdown", (e) => {
    grab = { x: e.clientX, y: e.clientY, t: performance.now() };
    view.held = true;
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add("turning");
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!grab) return;
    const dt = Math.max(8, performance.now() - grab.t), dx = (e.clientX - grab.x) / Math.max(120, W()), dy = (e.clientY - grab.y) / Math.max(120, W());
    view.yaw += dx * Math.PI * 1.4;
    view.pitch = Math.max(-1.2, Math.min(1.2, view.pitch - dy * Math.PI * 1.4));    // up turns the top away
    view.vy = (dx * Math.PI * 1.4) / dt * 16; view.vp = (-dy * Math.PI * 1.4) / dt * 16;
    grab = { x: e.clientX, y: e.clientY, t: performance.now() };
  });
  const release = () => { grab = null; view.held = false; canvas.classList.remove("turning"); };
  canvas.addEventListener("pointerup", release);
  canvas.addEventListener("pointercancel", release);
  const frame = (ctx) => {
    if (!view.held) {                                   // a glide, then home to the front
      view.yaw += view.vy; view.pitch += view.vp;
      view.vy *= 0.92; view.vp *= 0.92;
      if (Math.abs(view.vy) + Math.abs(view.vp) < 0.002) {
        const home = Math.round(view.yaw / 6.283) * 6.283;
        view.yaw += (home - view.yaw) * 0.06; view.pitch *= 0.94;
      }
    }
    project();
    body(ctx);
    // a touch or a click shows the virtual structure alone (owner, 2026-10-20: «come clicco o tengo premuto venga
    // rimosso per far vedere una struttura virtuale»): the drawing goes at once, comes back slowly from the front
    const want = view.held ? 0 : Math.max(0, Math.cos(view.yaw) * Math.cos(view.pitch)) ** 6;
    view.shown = want < view.shown ? want : view.shown + (want - view.shown) * 0.05;
  };
  return { proj, frame, front: () => view.shown };
}

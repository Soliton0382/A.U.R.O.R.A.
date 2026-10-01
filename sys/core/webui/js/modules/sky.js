// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The sky behind everything: Aurora's face in a circle, stars around it.
// Idle: stars twinkle and now and then one lights up softly.
// Thinking: around invisible black holes, groups of nearby stars light up and start orbiting
// (gravity ∝ 1/r², nearly circular orbits: inner stars turn faster, the group swirls, with
// luminous trails). When the thinking ends the orbits dissolve and every star flies home.
import { bus } from "../bus.js";

const FACE = { big: "/static/assets/aurora_face_bg.webp", small: "/static/assets/aurora_face_bg_s.webp" };
const STAR_RGB = "214,226,255";
const FLY_RGB = "190,255,90";          // firefly: warm yellow-green
const MAX_HOLES = 4;                    // black holes (groups) at the same time
const HOLE_LIFE = [9, 16];              // seconds a group orbits before dispersing (a new one appears)
const TRAIL = 10;                       // positions kept for the luminous trail

function sprite(rgb, size, core = 1) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, `rgba(${rgb},${core})`);
  grad.addColorStop(0.18, `rgba(${rgb},${0.85 * core})`);
  grad.addColorStop(0.45, `rgba(${rgb},0.22)`);
  grad.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  return c;
}

const rand = (a, b) => a + Math.random() * (b - a);

export default {
  id: "sky",
  slot: "background",

  mount(root) {
    const canvas = document.createElement("canvas");
    canvas.className = "sky";
    root.append(canvas);
    const g = canvas.getContext("2d");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const starSprite = sprite(STAR_RGB, 32);
    const flySprite = sprite(FLY_RGB, 64, 0.75);
    const face = new Image();
    face.src = innerWidth < 820 ? FACE.small : FACE.big;

    let W = 0, H = 0, cx = 0, cy = 0, R = 0;
    let stars = [], holes = [];
    let thinking = false, nextHole = 0, ringGlow = 0, raf = 0, last = performance.now();

    function layout() {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      W = innerWidth; H = innerHeight;
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      cx = W / 2; cy = H * 0.45;
      R = Math.min(W, H) * (W < 820 ? 0.34 : 0.27);
      const n = Math.max(90, Math.min(300, Math.round((W * H) / 7000)));
      holes = [];
      stars = Array.from({ length: n }, () => {
        let x, y;
        do { x = Math.random() * W; y = Math.random() * H; } while (Math.hypot(x - cx, y - cy) < R * 1.08);
        return { hx: x, hy: y, x, y, vx: 0, vy: 0, r: 0.5 + Math.random() * 1.3, base: 0.12 + Math.random() * 0.35,
          ph: Math.random() * 6.28, sp: 0.4 + Math.random() * 1.2, glow: 0, hole: null, homing: false,
          lit: 0, blink: rand(0.6, 1.4), trail: [] };
      });
    }

    const outsideFace = (x, y, margin) => Math.hypot(x - cx, y - cy) > R + margin;

    // A black hole: an invisible point in the sky; the free stars around it start to orbit.
    function spawnHole(now) {
      const margin = Math.min(W, H) * 0.12;
      let x, y, tries = 0;
      do { x = rand(margin, W - margin); y = rand(margin, H - margin); tries++; }
      while (!outsideFace(x, y, 150) && tries < 30);
      const reach = Math.min(W, H) * (W < 820 ? 0.22 : 0.16);
      const members = stars.filter((s) => !s.hole && !s.homing && Math.hypot(s.x - x, s.y - y) < reach);
      if (members.length < 4) return;
      const period = rand(5, 9);                                     // seconds per orbit at r = reach/2
      const r0 = reach / 2;
      const hole = { x, y, gm: (2 * Math.PI * r0 / period) ** 2 * r0, spin: Math.random() < 0.5 ? 1 : -1,
        until: now + rand(...HOLE_LIFE) * 1000 };
      for (const s of members.slice(0, 18)) {
        const dx = s.x - x, dy = s.y - y, r = Math.max(Math.hypot(dx, dy), 12);
        const v = Math.sqrt(hole.gm / r) * rand(0.85, 1.05);          // nearly circular, a little eccentric
        s.vx = (-dy / r) * v * hole.spin; s.vy = (dx / r) * v * hole.spin;
        s.hole = hole; s.lit = 0; s.trail = [];
      }
      holes.push(hole);
    }

    function release(s) { s.hole = null; s.homing = true; }

    function step(dt, now) {
      ringGlow += ((thinking ? 1 : 0) - ringGlow) * Math.min(1, dt * 1.5);
      if (thinking && !reduced && now > nextHole && holes.length < MAX_HOLES) {
        spawnHole(now);
        nextHole = now + rand(700, 1500);
      }
      // groups disperse when they have orbited long enough, or when the thinking ends
      holes = holes.filter((h) => {
        if (thinking && now < h.until) return true;
        for (const s of stars) if (s.hole === h) release(s);
        return false;
      });
      const sub = 4, h = dt / sub;
      for (const s of stars) {
        if (s.hole) {
          s.lit = Math.min(1, s.lit + dt * 1.2);
          for (let i = 0; i < sub; i++) {                            // semi-implicit Euler, soft core
            const dx = s.hole.x - s.x, dy = s.hole.y - s.y;
            const r2 = dx * dx + dy * dy + 144, r = Math.sqrt(r2), a = s.hole.gm / r2;
            s.vx += (dx / r) * a * h; s.vy += (dy / r) * a * h;
            s.x += s.vx * h; s.y += s.vy * h;
          }
          s.trail.push(s.x, s.y);
          if (s.trail.length > TRAIL * 2) s.trail.splice(0, 2);
        } else if (s.homing) {
          const k = Math.min(1, dt * 1.4);
          s.x += (s.hx - s.x) * k; s.y += (s.hy - s.y) * k;
          s.lit = Math.max(0, s.lit - dt * 0.5);
          s.trail.push(s.x, s.y);
          if (s.trail.length > TRAIL * 2) s.trail.splice(0, 2);
          if (Math.hypot(s.x - s.hx, s.y - s.hy) < 0.6 && s.lit < 0.05) {
            s.x = s.hx; s.y = s.hy; s.homing = false; s.trail = []; s.glow = 0.5;
          }
        } else {
          if (s.glow <= 0 && Math.random() < dt * 0.012) s.glow = 1;   // a rare, soft ignition
          s.glow = Math.max(0, s.glow - dt * 0.45);
        }
      }
    }

    function drawFace(time) {
      const bg = g.createRadialGradient(cx, cy, R * 0.6, cx, cy, Math.max(W, H) * 0.8);
      bg.addColorStop(0, "#0b1230"); bg.addColorStop(1, "#020617");
      g.fillStyle = bg; g.fillRect(0, 0, W, H);
      const halo = g.createRadialGradient(cx, cy, R * 0.9, cx, cy, R * (1.5 + 0.25 * ringGlow));
      halo.addColorStop(0, `rgba(122,162,255,${0.20 + 0.25 * ringGlow})`); halo.addColorStop(1, "rgba(122,162,255,0)");
      g.fillStyle = halo; g.beginPath(); g.arc(cx, cy, R * 1.8, 0, 6.2832); g.fill();
      if (face.complete && face.naturalWidth) {
        g.save(); g.beginPath(); g.arc(cx, cy, R, 0, 6.2832); g.clip();
        const k = (R * 2) / Math.min(face.naturalWidth, face.naturalHeight) * 1.02;
        g.globalAlpha = 0.9;
        g.drawImage(face, cx - (face.naturalWidth * k) / 2, cy - (face.naturalHeight * k) * 0.42,
          face.naturalWidth * k, face.naturalHeight * k);
        const vig = g.createRadialGradient(cx, cy, R * 0.55, cx, cy, R);
        vig.addColorStop(0, "rgba(2,6,23,0)"); vig.addColorStop(1, "rgba(2,6,23,0.55)");
        g.globalAlpha = 1; g.fillStyle = vig; g.fillRect(cx - R, cy - R, R * 2, R * 2);
        g.restore();
      }
      g.lineWidth = 1.5;
      g.strokeStyle = `rgba(160,190,255,${0.35 + 0.35 * ringGlow + 0.1 * Math.sin(time * 1.3)})`;
      g.beginPath(); g.arc(cx, cy, R + 2, 0, 6.2832); g.stroke();
    }

    function draw(now) {
      const time = now / 1000;
      g.clearRect(0, 0, W, H);
      drawFace(time);
      g.globalCompositeOperation = "lighter";
      for (const s of stars) {
        const flying = s.hole || s.homing;
        if (flying && s.lit > 0.02) {
          const blink = 0.6 + 0.4 * Math.sin(time * s.blink * 6.28 + s.ph);
          // trail: fading dots along the last positions
          for (let i = 0; i + 1 < s.trail.length; i += 2) {
            const f = (i / s.trail.length) * s.lit;
            const size = 3 + 6 * f;
            g.globalAlpha = 0.35 * f;
            g.drawImage(flySprite, s.trail[i] - size / 2, s.trail[i + 1] - size / 2, size, size);
          }
          const size = 12 + 12 * blink * s.lit;
          g.globalAlpha = Math.min(1, s.lit * blink);
          g.drawImage(flySprite, s.x - size / 2, s.y - size / 2, size, size);
        } else {
          const tw = s.base * (0.65 + 0.35 * Math.sin(time * s.sp + s.ph));
          const a = Math.min(1, tw + s.glow * 0.7);
          const size = 5 + s.r * 4 + s.glow * 8;
          g.globalAlpha = a; g.drawImage(starSprite, s.x - size / 2, s.y - size / 2, size, size);
        }
      }
      g.globalAlpha = 1; g.globalCompositeOperation = "source-over";
    }

    let lastStat = 0;
    function frame(now) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      step(dt, now);
      draw(now);
      if (now - lastStat > 500) {                 // for checks: how many holes and orbiting stars
        lastStat = now;
        canvas.dataset.holes = holes.length;
        canvas.dataset.orbiting = stars.filter((s) => s.hole).length;
        canvas.dataset.homing = stars.filter((s) => s.homing).length;
        canvas.dataset.thinking = thinking ? "1" : "0";
      }
      raf = requestAnimationFrame(frame);
    }
    const start = () => { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } };
    const stop = () => { cancelAnimationFrame(raf); raf = 0; };

    layout();
    face.onload = () => draw(performance.now());
    addEventListener("resize", () => { layout(); if (reduced) draw(performance.now()); });
    document.addEventListener("visibilitychange", () => (document.hidden || reduced ? stop() : start()));
    bus.on("thinking", ({ active }) => {
      thinking = active;
      if (active) nextHole = 0;
      if (reduced) { ringGlow = active ? 1 : 0; draw(performance.now()); }
    });
    if (reduced) draw(performance.now()); else start();
  },
};

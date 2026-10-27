// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🌈 The player's MilkDrop (owner, 2026-10-27: «il milkdrop è bellissimo mi mancava… aggiungi altri milkdrop, li adoro…
// trasformerei le stelle in milkdrop»): presets drawn on the visualiser's canvas from the music — the spectrum in 48
// bands, the wave, the bass and the highs — most of them on MilkDrop's own trick, the last frame turned and zoomed
// under the new one. Each takes `now` (ms) and the hue that the music moves.
export const PRESETS = ["rings", "tunnel", "kaleido", "plasma", "spiral", "stars", "lasers", "burst", "fire", "synthwave", "vortex", "nebula"];

export function milkdrop(canvas) {
  const g = canvas.getContext("2d");
  const small = document.createElement("canvas");  // the plasma, drawn small and stretched
  small.width = 96; small.height = 54;
  const gs = small.getContext("2d"), img = gs.createImageData(96, 54);
  const stars = [], blobs = [];
  const feedback = (w, h, rot, zoom, fade, dy = 0) => {   // the last frame, turned and zoomed, under the new one
    g.save(); g.globalAlpha = fade; g.translate(w / 2, h / 2 + dy); g.rotate(rot); g.scale(zoom, zoom);
    g.drawImage(canvas, -w / 2, -h / 2); g.restore();
  };
  const dim = (a) => { g.fillStyle = `rgba(0,0,0,${a})`; g.fillRect(0, 0, canvas.width, canvas.height); };

  return function draw(name, w, h, m) {
    if (!w || !h || !canvas.width || !canvas.height) return;   // hidden (another page, a closed panel): nothing to draw
    const { b, wave, live, bass, treble, now, hue } = m;
    const dpr = window.devicePixelRatio || 1, n = wave ? wave.length : 1, S = Math.min(w, h);
    const wv = (k) => (live && wave ? (wave[Math.floor(k) % n] - 128) / 128 : 0);
    if (name === "rings") {
      feedback(w, h, 0.004 + bass * 0.02, 1.012 + bass * 0.05, 0.93); dim(0.06);
      const r0 = S * (0.16 + bass * 0.18);
      g.lineWidth = 2.5 * dpr;
      for (let ring = 0; ring < 2; ring++) {
        g.strokeStyle = `hsla(${(hue + ring * 140) % 360},100%,${55 + treble * 30}%,.9)`;
        g.beginPath();
        for (let i = 0; i <= 360; i += 2) {
          const r = r0 * (1 + ring * 0.6) + wv((i / 360) * (n - 1)) * r0 * 0.9, a = (i * Math.PI) / 180 + hue / 60;
          const x = w / 2 + Math.cos(a) * r, y = h / 2 + Math.sin(a) * r;
          i ? g.lineTo(x, y) : g.moveTo(x, y);
        }
        g.stroke();
      }
    } else if (name === "tunnel") {                   // squares flying at you, the beat speeding them
      feedback(w, h, -0.01 - bass * 0.03, 1.04 + bass * 0.1, 0.9); dim(0.08);
      const s = S * (0.08 + bass * 0.12);
      g.lineWidth = 3 * dpr; g.strokeStyle = `hsl(${hue},100%,${50 + treble * 40}%)`;
      g.save(); g.translate(w / 2, h / 2); g.rotate(hue / 40); g.strokeRect(-s, -s, 2 * s, 2 * s); g.restore();
    } else if (name === "kaleido") {                  // the wave in six mirrored slices
      feedback(w, h, 0.006, 0.985, 0.88);
      g.save(); g.translate(w / 2, h / 2); g.lineWidth = 2 * dpr;
      for (let k = 0; k < 6; k++) {
        g.rotate(Math.PI / 3);
        g.strokeStyle = `hsla(${(hue + k * 60) % 360},100%,60%,.85)`;
        g.beginPath();
        for (let i = 0; i < 128; i++) { const x = (i / 128) * S * 0.48, y = wv(i * 8) * S * (0.12 + bass * 0.2) * (k % 2 ? -1 : 1); i ? g.lineTo(x, y) : g.moveTo(x, y); }
        g.stroke();
      }
      g.restore();
    } else if (name === "plasma") {                   // a colour field folding with the bass and the highs
      const T = now / 1000, d = img.data;
      for (let y = 0; y < 54; y++) for (let x = 0; x < 96; x++) {
        const v = Math.sin(x / (8 - bass * 4) + T) + Math.sin(y / 6 + T * 1.3) + Math.sin((x + y) / (10 + treble * 6) + T * 0.7)
          + Math.sin(Math.hypot(x - 48, y - 27) / (5 - bass * 2) - T * 2);
        const hh = (hue + v * 45 + 360) % 360, c = 1 - Math.abs(((hh / 60) % 2) - 1);
        const [r, gg, bb] = hh < 60 ? [1, c, 0] : hh < 120 ? [c, 1, 0] : hh < 180 ? [0, 1, c] : hh < 240 ? [0, c, 1] : hh < 300 ? [c, 0, 1] : [1, 0, c];
        const L = 0.45 + 0.5 * Math.abs(Math.sin(v)), o = (y * 96 + x) * 4;
        d[o] = r * 255 * L; d[o + 1] = gg * 255 * L; d[o + 2] = bb * 255 * L; d[o + 3] = 255;
      }
      gs.putImageData(img, 0, 0);
      g.imageSmoothingEnabled = true; g.drawImage(small, 0, 0, w, h);
    } else if (name === "spiral") {                   // the spectrum thrown out along turning arms
      feedback(w, h, 0.02 + bass * 0.04, 1.006, 0.92); dim(0.05);
      for (let i = 0; i < 48; i++) {
        const a = i * 0.45 + hue / 20, r = (i / 48) * S * 0.5;
        g.fillStyle = `hsl(${(hue + i * 7) % 360},100%,${45 + b[i] * 45}%)`;
        g.beginPath(); g.arc(w / 2 + Math.cos(a) * r, h / 2 + Math.sin(a) * r, (1 + b[i] * 9) * dpr, 0, Math.PI * 2); g.fill();
      }
    } else if (name === "stars") {                    // a starfield the beat pushes out, with trails
      feedback(w, h, 0.002, 1.01 + bass * 0.03, 0.75); dim(0.12);
      while (stars.length < 420) stars.push({ x: (Math.random() - 0.5) * w, y: (Math.random() - 0.5) * h, z: Math.random() * w });
      for (const s of stars) {
        s.z -= 2 + bass * 40;
        if (s.z <= 1) { s.x = (Math.random() - 0.5) * w; s.y = (Math.random() - 0.5) * h; s.z = w; }
        const k = 128 / s.z, x = w / 2 + s.x * k, y = h / 2 + s.y * k, r = Math.max(0.6, (1 - s.z / w) * 3.2) * dpr;
        g.fillStyle = `hsl(${(hue + s.z / 4) % 360},90%,${60 + treble * 30}%)`;
        g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
      }
    } else if (name === "lasers") {                   // beams from the middle, one per band, turning
      feedback(w, h, 0.01, 0.98, 0.82); dim(0.1);
      g.save(); g.translate(w / 2, h / 2); g.globalCompositeOperation = "lighter"; g.lineCap = "round";
      for (let i = 0; i < 24; i++) {
        const v = b[i * 2], a = (i / 24) * Math.PI * 2 + now / 2200;
        if (v < 0.08) continue;
        g.strokeStyle = `hsla(${(hue + i * 15) % 360},100%,60%,${0.25 + v * 0.7})`; g.lineWidth = (1 + v * 5) * dpr;
        g.beginPath(); g.moveTo(0, 0); g.lineTo(Math.cos(a) * S * (0.2 + v * 0.8), Math.sin(a) * S * (0.2 + v * 0.8)); g.stroke();
      }
      g.restore();
    } else if (name === "burst") {                    // the spectrum as a flower that bursts on the kick
      feedback(w, h, -0.006, 1.03 + bass * 0.06, 0.86); dim(0.09);
      g.save(); g.translate(w / 2, h / 2);
      for (let i = 0; i < 96; i++) {
        const v = b[i % 48], a = (i / 96) * Math.PI * 2, r1 = S * 0.08, r2 = r1 + v * S * 0.42;
        g.strokeStyle = `hsl(${(hue + i * 4) % 360},100%,${45 + v * 40}%)`; g.lineWidth = 2.2 * dpr;
        g.beginPath(); g.moveTo(Math.cos(a) * r1, Math.sin(a) * r1); g.lineTo(Math.cos(a) * r2, Math.sin(a) * r2); g.stroke();
      }
      g.restore();
    } else if (name === "fire") {                     // flames rising from the spectrum, the frame drifting up
      feedback(w, h, 0, 1.012, 0.94, -3 * dpr); dim(0.04);
      const bw = w / 48;
      for (let i = 0; i < 48; i++) {
        const v = b[i], x = i * bw + bw / 2;
        const grad = g.createRadialGradient(x, h, 0, x, h, (20 + v * h * 0.5));
        grad.addColorStop(0, `hsla(${45 + v * 15},100%,65%,${0.4 + v * 0.6})`); grad.addColorStop(0.5, "hsla(15,100%,45%,.5)"); grad.addColorStop(1, "hsla(0,100%,20%,0)");
        g.fillStyle = grad; g.fillRect(x - bw * 2, h - (20 + v * h * 0.5), bw * 4, 20 + v * h * 0.5);
      }
    } else if (name === "synthwave") {                // an 80s sun and a grid running at you on the beat
      const sky = g.createLinearGradient(0, 0, 0, h);
      sky.addColorStop(0, "#12002b"); sky.addColorStop(0.55, "#4a0e5c"); sky.addColorStop(0.56, "#090014"); sky.addColorStop(1, "#000");
      g.fillStyle = sky; g.fillRect(0, 0, w, h);
      const hz = h * 0.56, sr = S * (0.22 + bass * 0.08);
      const sun = g.createLinearGradient(0, hz - sr, 0, hz);
      sun.addColorStop(0, "#ffe65c"); sun.addColorStop(1, "#ff2e88");
      g.fillStyle = sun; g.beginPath(); g.arc(w / 2, hz, sr, Math.PI, 0); g.fill();
      g.fillStyle = "#090014";
      for (let k = 0; k < 6; k++) g.fillRect(w / 2 - sr, hz - sr * (0.12 + k * 0.14), sr * 2, sr * 0.03 * (k + 1));
      g.strokeStyle = `hsla(${300 + treble * 40},100%,60%,.85)`; g.lineWidth = 1.5 * dpr;
      const run = (now / 1000) * (0.4 + bass * 1.2) % 1;
      for (let k = 0; k < 14; k++) { const z = (k + run) / 14, y = hz + (h - hz) * z * z; g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
      for (let k = -12; k <= 12; k++) { g.beginPath(); g.moveTo(w / 2 + k * w * 0.02, hz); g.lineTo(w / 2 + k * w * 0.16, h); g.stroke(); }
      g.strokeStyle = "#7cf9ff"; g.beginPath();
      for (let i = 0; i < 200; i++) { const x = (i / 200) * w, y = hz * 0.35 + wv(i * 10) * h * 0.12; i ? g.lineTo(x, y) : g.moveTo(x, y); }
      g.stroke();
    } else if (name === "vortex") {                   // a whirlpool: hard rotation, small bright trails on the wave
      feedback(w, h, 0.06 + bass * 0.08, 0.97, 0.95); dim(0.03);
      g.save(); g.translate(w / 2, h / 2);
      for (let i = 0; i < 64; i++) {
        const a = (i / 64) * Math.PI * 2, r = S * (0.3 + wv(i * 30) * 0.15);
        g.fillStyle = `hsl(${(hue + i * 5) % 360},100%,${55 + treble * 35}%)`;
        g.beginPath(); g.arc(Math.cos(a) * r, Math.sin(a) * r, (1.2 + bass * 4) * dpr, 0, Math.PI * 2); g.fill();
      }
      g.restore();
    } else {                                          // nebula: soft clouds of colour drifting, swelling with the music
      feedback(w, h, 0.003, 1.004, 0.97); dim(0.025);
      while (blobs.length < 7) blobs.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.6, vy: (Math.random() - 0.5) * 0.6, k: blobs.length });
      g.globalCompositeOperation = "lighter";
      for (const o of blobs) {
        o.x = (o.x + o.vx * (1 + bass * 6) + w) % w; o.y = (o.y + o.vy * (1 + bass * 6) + h) % h;
        const v = b[(o.k * 6) % 48], r = S * (0.08 + v * 0.25);
        const gr = g.createRadialGradient(o.x, o.y, 0, o.x, o.y, r);
        gr.addColorStop(0, `hsla(${(hue + o.k * 50) % 360},100%,60%,${0.12 + v * 0.3})`); gr.addColorStop(1, "hsla(0,0%,0%,0)");
        g.fillStyle = gr; g.beginPath(); g.arc(o.x, o.y, r, 0, Math.PI * 2); g.fill();
      }
      g.globalCompositeOperation = "source-over";
    }
  };
}

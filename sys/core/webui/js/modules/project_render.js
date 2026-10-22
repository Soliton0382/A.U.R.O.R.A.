// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎨 A project's model seen built (ROADMAP N42, prj_view; owner, 23 Oct: «un Proof of concept che assembla tutto il
// progetto in una immagine realistica»): the parts the cad plugin drew, each in its material, in a studio light
// (project_render_gl). Drag to turn, wheel or two fingers to come closer; the exploded view slides the parts apart
// (exploded_<k>.stl, fetched the first time); a part can be hidden or given another material (kept on this device);
// 📷 saves the picture at twice the screen's size. A material guessed from the part's name is marked «stimato».
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { BG, makeRenderer } from "./project_render_gl.js";

// STL (text or binary) → the triangles' corners, and normals smoothed where faces meet at less than 40°
export function parseStl(buf) {
  const head = new TextDecoder().decode(new Uint8Array(buf, 0, Math.min(buf.byteLength, 512)));
  let pos;
  const dv = new DataView(buf);
  const n = buf.byteLength >= 84 ? dv.getUint32(80, true) : 0;
  if (n && 84 + n * 50 === buf.byteLength && !/^\s*solid[\s\S]*facet/.test(head)) {
    pos = new Float32Array(n * 9);
    for (let i = 0; i < n; i++) for (let j = 0; j < 9; j++) pos[i * 9 + j] = dv.getFloat32(84 + i * 50 + 12 + j * 4, true);
  } else {
    const text = new TextDecoder().decode(buf), out = [];
    const rx = /vertex\s+(\S+)\s+(\S+)\s+(\S+)/g;
    let m;
    while ((m = rx.exec(text))) out.push(+m[1], +m[2], +m[3]);
    pos = new Float32Array(out.length - (out.length % 9));
    pos.set(out.slice(0, pos.length));
  }
  const tri = pos.length / 9, face = new Float32Array(tri * 3), at = new Map();
  for (let i = 0; i < tri; i++) {
    const p = (k) => [pos[i * 9 + k * 3], pos[i * 9 + k * 3 + 1], pos[i * 9 + k * 3 + 2]];
    const [a, b, c] = [p(0), p(1), p(2)];
    const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    face.set([u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]], i * 3);   // area-weighted
    for (const q of [a, b, c]) {
      const key = q.map((x) => Math.round(x * 1e3)).join(",");
      if (!at.has(key)) at.set(key, []);
      at.get(key).push(i);
    }
  }
  const unit = (i) => { const l = Math.hypot(face[i * 3], face[i * 3 + 1], face[i * 3 + 2]) || 1; return [face[i * 3] / l, face[i * 3 + 1] / l, face[i * 3 + 2] / l]; };
  const nrm = new Float32Array(pos.length), cos = Math.cos((40 * Math.PI) / 180);
  for (let i = 0; i < tri; i++) {
    const me = unit(i);
    for (let k = 0; k < 3; k++) {
      const key = [0, 1, 2].map((j) => Math.round(pos[i * 9 + k * 3 + j] * 1e3)).join(",");
      const s = [0, 0, 0];
      for (const f of at.get(key)) {
        const o = unit(f);
        if (o[0] * me[0] + o[1] * me[1] + o[2] * me[2] >= cos) for (let j = 0; j < 3; j++) s[j] += face[f * 3 + j];
      }
      const l = Math.hypot(...s) || 1;
      nrm.set([s[0] / l, s[1] / l, s[2] / l], i * 9 + k * 3);
    }
  }
  return { pos, nrm };
}

const box3 = (pos) => {
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < pos.length; i += 3) for (let j = 0; j < 3; j++) { lo[j] = Math.min(lo[j], pos[i + j]); hi[j] = Math.max(hi[j], pos[i + j]); }
  return { lo, hi, c: lo.map((v, j) => (v + hi[j]) / 2) };
};

async function stl(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`${res.status}`);
  return parseStl(await res.arrayBuffer());
}

function modelView(project, model, materials) {
  const box = el("div", "rnd-box");
  const stage = el("div", "rnd-stage"), canvas = el("canvas", "rnd-canvas"), state = el("p", "muted rnd-state", t("prj.loading"));
  stage.append(canvas, state);
  const tools = el("div", "rnd-tools"), parts = el("div", "rnd-parts");
  box.append(stage, tools, parts);
  let gl;
  try { gl = makeRenderer(canvas); } catch { state.textContent = t("prj.render_nogl"); return box; }
  const keep = `aurora.prj.render.${project}.${model.model}`;
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(keep) || "{}"); } catch { /* defaults */ }
  const store = () => { try { localStorage.setItem(keep, JSON.stringify(saved)); } catch { /* not kept */ } };
  saved.mat ||= {}; saved.hide ||= {};
  let meshes = [], ready = false, explode = 0, exploded = null, light = saved.light ?? -0.8;
  const cam = { yaw: -0.9, pitch: 0.55, zoom: 1 };
  let dirty = false;
  const frame = () => {
    if (!ready || dirty) return;
    dirty = true;
    requestAnimationFrame(() => {
      dirty = false;
      const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
      for (const m of meshes) {
        m.offset = m.delta ? m.delta.map((v) => v * explode) : [0, 0, 0];
        if (!m.visible) continue;
        for (let j = 0; j < 3; j++) { lo[j] = Math.min(lo[j], m.box.lo[j] + m.offset[j]); hi[j] = Math.max(hi[j], m.box.hi[j] + m.offset[j]); }
      }
      if (!Number.isFinite(lo[0])) return;
      // the floor under what is shown, the view around it: the exploded parts never sink into the floor
      const at = lo.map((v, j) => (v + hi[j]) / 2), r = Math.hypot(...hi.map((v, j) => v - lo[j])) / 2;
      const d = (r / Math.sin(0.28)) * cam.zoom;
      const eye = [at[0] + d * Math.cos(cam.pitch) * Math.cos(cam.yaw), at[1] + d * Math.cos(cam.pitch) * Math.sin(cam.yaw), at[2] + d * Math.sin(cam.pitch)];
      gl.draw({ eye, at, fov: 0.56 }, { c: at, r, zmin: lo[2] }, light);
    });
  };
  const size = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(canvas.clientWidth * dpr);
    canvas.height = Math.round(canvas.clientHeight * dpr);
    frame();
  };
  new ResizeObserver(size).observe(canvas);
  // orbit: one pointer turns, two pinch; the wheel comes closer
  const down = new Map();
  canvas.addEventListener("pointerdown", (e) => { canvas.setPointerCapture(e.pointerId); down.set(e.pointerId, [e.clientX, e.clientY]); });
  canvas.addEventListener("pointerup", (e) => down.delete(e.pointerId));
  canvas.addEventListener("pointercancel", (e) => down.delete(e.pointerId));
  canvas.addEventListener("pointermove", (e) => {
    if (!down.has(e.pointerId)) return;
    const [x, y] = down.get(e.pointerId);
    if (down.size === 1) {
      cam.yaw -= (e.clientX - x) * 0.008;
      cam.pitch = Math.max(0.03, Math.min(1.5, cam.pitch + (e.clientY - y) * 0.006));
    } else if (down.size === 2) {
      const [o] = [...down.entries()].filter(([id]) => id !== e.pointerId).map(([, p]) => p);
      const before = Math.hypot(x - o[0], y - o[1]), now = Math.hypot(e.clientX - o[0], e.clientY - o[1]);
      if (before > 0 && now > 0) cam.zoom = Math.max(0.3, Math.min(3, cam.zoom * (before / now)));
    }
    down.set(e.pointerId, [e.clientX, e.clientY]);
    frame();
  });
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); cam.zoom = Math.max(0.3, Math.min(3, cam.zoom * Math.exp(e.deltaY * 0.001))); frame(); }, { passive: false });
  const look = (m, name) => {
    const [color, metal, rough] = materials[name] || materials.plastic_light;
    Object.assign(m, { color, metal, rough });
  };
  // the tools: exploded view, the light, the view again, the picture
  const slider = (label, min, max, value, on) => {
    const l = el("label", "rnd-slider");
    const i = el("input");
    Object.assign(i, { type: "range", min, max, value, step: 1 });
    i.addEventListener("input", () => on(Number(i.value)));
    l.append(el("span", "", label), i);
    return l;
  };
  tools.append(slider(t("prj.render_explode"), 0, 100, 0, async (v) => {
    if (v > 0 && !exploded) {
      exploded = Promise.all(model.parts.map(async (p) => {
        if (!p.exploded) return;
        try {
          const e = await stl(`/v1/aurora/projects/${project}/cad/${model.model}/part/${p.k}.stl?exploded=true`);
          const m = meshes.find((x) => x.part.k === p.k);
          if (!m) return;
          const a = m.box.c, b = box3(e.pos).c;
          m.delta = b.map((x, j) => x - a[j]);
        } catch { /* stays in place */ }
      }));
    }
    await exploded;
    explode = v / 100;
    frame();
  }), slider(t("prj.render_light"), -180, 180, Math.round((light * 180) / Math.PI), (v) => {
    light = (v * Math.PI) / 180; saved.light = light; store(); frame();
  }));
  const reset = el("button", "", t("prj.render_reset"));
  reset.addEventListener("click", () => { Object.assign(cam, { yaw: -0.9, pitch: 0.55, zoom: 1 }); frame(); });
  const shot = el("button", "approve", t("prj.render_shot"));
  shot.addEventListener("click", () => {
    const [w, h] = [canvas.width, canvas.height];
    canvas.width = w * 2; canvas.height = h * 2;
    dirty = false; frame();
    requestAnimationFrame(() => requestAnimationFrame(() => canvas.toBlob((b) => {
      const a = el("a");
      a.href = URL.createObjectURL(b);
      a.download = `${project}-${model.model}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      size();
    }, "image/png")));
  });
  tools.append(reset, shot);
  (async () => {
    const loaded = [];
    for (const [i, p] of model.parts.entries()) {
      state.textContent = t("prj.render_loading", { i: i + 1, n: model.parts.length });
      try { loaded.push({ ...(await stl(`/v1/aurora/projects/${project}/cad/${model.model}/part/${p.k}.stl`)), part: p }); } catch { /* left out */ }
    }
    if (!loaded.length) { state.textContent = t("prj.render_none"); return; }
    meshes = gl.setMeshes(loaded.map((m) => ({ pos: m.pos, nrm: m.nrm, color: [1, 1, 1], metal: 0, rough: 0.5, part: m.part })));
    ready = true;
    for (const m of meshes) {
      m.box = box3(m.pos);
      look(m, saved.mat[m.part.sign] || m.part.material);
      m.visible = !saved.hide[m.part.sign];
      const row = el("div", "rnd-part");
      const show = el("input");
      show.type = "checkbox"; show.checked = m.visible;
      show.addEventListener("change", () => { m.visible = show.checked; saved.hide[m.part.sign] = !show.checked; store(); frame(); });
      const pick = el("select");
      for (const name of Object.keys(materials)) {
        const o = el("option", "", t(`prj.mat_${name}`));
        o.value = name;
        pick.append(o);
      }
      pick.value = saved.mat[m.part.sign] || m.part.material;
      const guess = el("span", "muted", m.part.guessed && !saved.mat[m.part.sign] ? t("prj.render_guessed") : "");
      pick.addEventListener("change", () => { saved.mat[m.part.sign] = pick.value; guess.textContent = ""; store(); look(m, pick.value); frame(); });
      row.append(show, el("span", "", `${m.part.sign} · ${m.part.name}`), pick, guess);
      parts.append(row);
    }
    state.remove();
    size();
  })();
  return box;
}

export function renderView(name) {
  const box = el("div", "prj-render");
  box.append(el("p", "muted", t("prj.render_hint")));
  canvasBg(box);
  call(`/v1/aurora/projects/${name}/scene`).then(({ models, materials }) => {
    if (!models.length) { box.append(el("p", "muted", t("prj.render_none"))); return; }
    const chips = el("div", "prj-tabs"), pane = el("div");
    const pick = (i) => {
      chips.querySelectorAll("button").forEach((b, k) => b.classList.toggle("on", k === i));
      pane.replaceChildren(modelView(name, models[i], materials));
    };
    models.forEach((m, i) => {
      const b = el("button", "cat-chip", `🧊 ${m.model}`);
      b.type = "button";
      b.addEventListener("click", () => pick(i));
      chips.append(b);
    });
    if (models.length > 1) box.append(chips);
    box.append(pane);
    pick(0);
  }).catch((e) => box.append(el("p", "error", t("ev.error", { m: e.message }))));
  return box;
}

// the stage behind the canvas has the backdrop's colour (BG is the screen's value: the floor fades into it after the tone map), so the page does not flash while the parts load
function canvasBg(box) {
  box.style.setProperty("--rnd-bg", `rgb(${BG.map((v) => Math.round(255 * v)).join(",")})`);
}

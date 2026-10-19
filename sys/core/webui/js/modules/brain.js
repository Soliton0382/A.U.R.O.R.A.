// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧠 What Aurora is doing, drawn as a brain (owner, 2026-10-15: «un bel cervello tipo cervello umano pieno di sinapsi e
// collegamenti che si illuminano in base a quello che sta facendo aurora… un widget attivabile come pop up… per una
// presentazione»). Not a function of hers: a picture of her work. A human brain seen from the left, a few hundred
// neurons joined to their nearest ones; each step of a run (the activity feed's run.begin, then the run's own events)
// lights its area — deciding in the frontal lobe, words in the language area, memory and the vault in the temporal
// lobe, checks in the parietal, pictures in the occipital, the agent in the motor strip, its tools in the cerebellum,
// what she does by herself (dreams, harvest, the sentinel) in the brainstem — and a signal runs along the synapses from
// the area of the step before. Only the names of the events are read, never what they carry. ▶ plays a typical
// question when nothing is running; ⛶ fills the screen.
import { call, followRun, stream } from "../api.js";
import { el, useCss } from "../dom.js";
import * as i18n from "../i18n.js";
import { FISSURES, GYRI, LOBES, OUTLINE, VIEW } from "./brain_gray.js";
import { turnable } from "./brain_3d.js";

const t = i18n.t;
const OPEN = "aurora.brain";
const SPOT = "aurora.brain.at";                       // where the panel was left (this browser)
// the areas: a hub (x, y in the figure, 1 × 0.715, the face to the left) and a colour of their own
const AREAS = {
  frontal: { x: 0.215, y: 0.225, rgb: "122,162,255", icon: "🧭" },
  language: { x: 0.283, y: 0.381, rgb: "190,140,255", icon: "💬" },
  motor: { x: 0.459, y: 0.137, rgb: "255,170,90", icon: "🛠️" },
  parietal: { x: 0.645, y: 0.215, rgb: "120,230,200", icon: "✅" },
  occipital: { x: 0.879, y: 0.371, rgb: "255,120,170", icon: "👁️" },
  temporal: { x: 0.508, y: 0.459, rgb: "130,210,255", icon: "📚" },
  cerebellum: { x: 0.713, y: 0.586, rgb: "250,215,110", icon: "🔧" },
  stem: { x: 0.576, y: 0.645, rgb: "160,255,140", icon: "🌙" },
};
// an event's name → its area (the first that fits)
const MAP = [
  [/^(route|think|question|pivot$|abstain|self|run\.(alone|start|begin)|lessons)/, "frontal"],
  [/^(translate|pivot\.back|synthesis|answer)/, "language"],
  [/^(retrieval|read\.(memory|pages|web)|memory|about|acquire|shadow)/, "temporal"],
  [/^(gate|verify|deduce|grid|read\.reasoning|custom)/, "parietal"],
  [/^(image|video|attach\.(image|video)|story|dj)/, "occipital"],
  [/^(tool|plugin)/, "cerebellum"],
  [/^(agent|approval|forge|change|project|routine|react)/, "motor"],
  [/^(rem|backup|update|sentinel|security|home|health|harvest|calendar|diet|notify|cloudflare|video)/, "stem"],
];
const areaOf = (name) => (MAP.find(([rx]) => rx.test(name)) || [])[1] || null;
// ▶: a question as it usually goes (route, the vault, the gate, reading, writing, the checks)
const DEMO = ["route", "translate", "retrieval.hits", "gate", "read.memory", "think", "grid.rule", "synthesis",
  "synthesis.delta", "verify.keep", "pivot.back", "answer.final", "tool.call", "agent.start", "image.plan", "rem.start"];

// The brain from the left, traced from Gray's Anatomy (brain_gray.js), in the figure's own proportions: x from 0 to 1,
// y from 0 to 0.715 (1024 × 732). Each point's lobe is read from the lobes drawn in their order, once.
const S = 1 / VIEW[0];
const TALL = VIEW[1] / VIEW[0];
const P2 = {};
const path2d = (d) => (P2[d] ||= new Path2D(d));
const ORDER = Object.keys(LOBES);                         // the figure's drawing order: each covers the one before
let lobes = null;
function lobeAt(x, y) {
  if (!lobes) {
    const c = document.createElement("canvas");
    c.width = 512; c.height = Math.ceil(512 * TALL);
    const g = c.getContext("2d", { willReadFrequently: true });
    g.scale(512 * S, 512 * S);
    ORDER.forEach((k, i) => { g.fillStyle = `rgb(${(i + 1) * 40},0,0)`; g.fill(path2d(LOBES[k])); });
    lobes = { w: c.width, h: c.height, d: g.getImageData(0, 0, c.width, c.height).data };
  }
  const px = Math.floor(x * lobes.w), py = Math.floor(y * lobes.w);
  if (px < 0 || py < 0 || px >= lobes.w || py >= lobes.h) return null;
  const k = 4 * (py * lobes.w + px);
  if (lobes.d[k + 3] < 255) return null;                  // the outer edge, half covered
  return ORDER[Math.round(lobes.d[k] / 40) - 1] || null;
}
const inside = (x, y) => lobeAt(x, y) !== null;

// the still part, drawn once per size: the lobes in their order, dark with a hint of their area's colour (the stem's
// and the cerebellum's rims before the lobes over them), a light from the upper left, the gyri and the folia, the
// deep fissures, the outline
function backdrop(W, H, dpr) {
  const c = document.createElement("canvas");
  c.width = Math.round(W * dpr); c.height = Math.round(H * dpr);
  const g = c.getContext("2d");
  const k = dpr * W * S;
  g.scale(k, k);                                          // the figure's units from here on
  const u = VIEW[0] / W;                                  // one CSS pixel, in the figure's units
  g.lineCap = "round"; g.lineJoin = "round";
  for (const name of ORDER) {
    const shape = path2d(LOBES[name]);
    g.fillStyle = "#0d1430"; g.fill(shape);
    g.fillStyle = `rgba(${AREAS[name].rgb},0.08)`; g.fill(shape);
    if (name === "stem" || name === "cerebellum") {
      g.strokeStyle = "rgba(170,190,255,0.5)"; g.lineWidth = Math.max(2, 1.1 * u); g.stroke(shape);
    }
  }
  g.save();
  g.clip(path2d(OUTLINE));
  const light = g.createRadialGradient(330, 190, 0, 330, 190, 760);
  light.addColorStop(0, "rgba(150,170,240,0.16)"); light.addColorStop(1, "rgba(0,0,10,0.28)");
  g.fillStyle = light; g.fillRect(0, 0, VIEW[0], VIEW[1]);
  g.restore();
  g.strokeStyle = "rgba(190,205,255,0.36)"; g.lineWidth = Math.max(2, 1.0 * u);
  for (const d of GYRI) g.stroke(path2d(d));
  g.fillStyle = "rgba(205,218,255,0.6)";
  for (const d of FISSURES) g.fill(path2d(d));
  g.strokeStyle = "rgba(170,190,255,0.7)"; g.lineWidth = Math.max(4, 1.6 * u);
  g.stroke(path2d(OUTLINE));
  return c;
}

function build(n, rnd) {
  const nodes = [];
  const front = ["frontal", "language", "motor"];         // the frontal lobe: deciding, Broca's area, the motor strip
  while (nodes.length < n) {
    const x = rnd(), y = rnd() * TALL;
    const lobe = lobeAt(x, y);
    if (!lobe) continue;
    let area = lobe;
    if (lobe === "frontal") {
      let best = Infinity;
      for (const k of front) {
        const d = (x - AREAS[k].x) ** 2 + (y - AREAS[k].y) ** 2;
        if (d < best) { best = d; area = k; }
      }
    }
    nodes.push({ x, y, area, e: 0, tw: rnd() * 6.28 });
  }
  const edges = [], adj = nodes.map(() => []), seen = new Set();
  nodes.forEach((a, i) => {
    const near = nodes.map((b, j) => [j, (a.x - b.x) ** 2 + (a.y - b.y) ** 2]).filter(([j]) => j !== i)
      .sort((p, q) => p[1] - q[1]).slice(0, 3);
    for (const [j, d] of near) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (seen.has(key) || d > 0.012) continue;
      seen.add(key);
      edges.push([i, j]);
      adj[i].push(j); adj[j].push(i);
    }
  });
  const hubs = {};
  for (const [k, a] of Object.entries(AREAS)) {
    let best = Infinity;
    nodes.forEach((nd, i) => {
      const d = (nd.x - a.x) ** 2 + (nd.y - a.y) ** 2;
      if (nd.area === k && d < best && adj[i].length) { best = d; hubs[k] = i; }
    });
  }
  return { nodes, edges, adj, hubs };
}

function path(adj, from, to) {                           // the shortest way along the synapses (breadth first)
  if (from == null || to == null) return null;
  const prev = new Map([[from, -1]]), q = [from];
  while (q.length) {
    const i = q.shift();
    if (i === to) break;
    for (const j of adj[i]) if (!prev.has(j)) { prev.set(j, i); q.push(j); }
  }
  if (!prev.has(to)) return null;
  const out = [];
  for (let i = to; i !== -1; i = prev.get(i)) out.unshift(i);
  return out;
}

function seeded(s) {                                     // the same brain on every opening
  return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
}

export default {
  id: "brain",
  slot: "alerts",

  mount(root) {
    useCss("/static/css/brain.css");
    const btn = el("button", "notif-toggle brain-toggle", "🧠");
    btn.type = "button";
    btn.title = t("brain.title");
    root.append(btn);
    btn.addEventListener("click", () => (this.box ? this.close() : this.open()));
    try { if (localStorage.getItem(OPEN) === "1") this.open(); } catch { /* not remembered */ }
  },

  open() {
    const small = matchMedia("(max-width: 640px)").matches;
    const g = build(small ? 220 : 380, seeded(20261015));
    const box = el("section", "brain-pop");
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", t("brain.title"));
    const head = el("div", "brain-head");
    const info = el("button", "", "ℹ️");
    const demo = el("button", "", "▶");
    const full = el("button", "", "⛶");
    const shut = el("button", "", "✕");
    for (const [b, k] of [[info, "brain.info"], [demo, "brain.demo"], [full, "brain.full"], [shut, "brain.close"]]) {
      b.type = "button"; b.title = t(k);
    }
    head.append(el("strong", "", `🧠 ${t("brain.title")}`), el("span", "grow"), info, demo, full, shut);
    const canvas = el("canvas", "brain-canvas");
    const now = el("p", "brain-now muted", t("brain.idle"));
    now.setAttribute("aria-live", "polite");
    const legend = el("div", "brain-legend");
    const chips = {};
    for (const [k, a] of Object.entries(AREAS)) {
      const c = el("span", "brain-chip");
      const dot = el("i");
      dot.style.background = `rgb(${a.rgb})`;
      c.append(dot, el("span", "", `${a.icon} ${t(`brain.a.${k}`)}`));
      chips[k] = c;
      legend.append(c);
    }
    // ℹ️ what the picture means: each area, what she does there, why that area — and where the analogy stops
    const why = el("div", "brain-info hidden");
    why.append(el("p", "", t("brain.info.head")));
    const list = el("dl");
    for (const [k, a] of Object.entries(AREAS)) list.append(el("dt", "", `${a.icon} ${t(`brain.a.${k}`)}`), el("dd", "", t(`brain.why.${k}`)));
    why.append(list, el("p", "muted", t("brain.info.limits")));
    info.setAttribute("aria-expanded", "false");
    info.addEventListener("click", () => {
      const open = why.classList.toggle("hidden") === false;
      info.setAttribute("aria-expanded", String(open));
      canvas.classList.toggle("hidden", open);
    });
    box.append(head, canvas, why, now, legend);
    document.body.append(box);
    // moved by its title bar anywhere on the screen, kept inside it; a double click puts it back in the corner
    const place = (x, y) => {
      const r = box.getBoundingClientRect();
      x = Math.max(0, Math.min(innerWidth - r.width, x));
      y = Math.max(0, Math.min(innerHeight - r.height, y));
      Object.assign(box.style, { left: `${x}px`, top: `${y}px`, right: "auto", bottom: "auto" });
      return [x, y];
    };
    // the spot kept, as it was: checked against the screen once the panel has its size (its CSS may come later)
    try {
      const at = JSON.parse(localStorage.getItem(SPOT) || "null");
      if (at) Object.assign(box.style, { left: `${at[0]}px`, top: `${at[1]}px`, right: "auto", bottom: "auto" });
    } catch { /* the corner */ }
    head.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button") || document.fullscreenElement) return;
      const r = box.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
      head.setPointerCapture(e.pointerId);
      box.classList.add("moving");
      const move = (m) => place(m.clientX - dx, m.clientY - dy);
      const up = (u) => {
        head.removeEventListener("pointermove", move);
        box.classList.remove("moving");
        try { localStorage.setItem(SPOT, JSON.stringify(place(u.clientX - dx, u.clientY - dy))); } catch { /* this visit only */ }
      };
      head.addEventListener("pointermove", move);
      head.addEventListener("pointerup", up, { once: true });
      head.addEventListener("pointercancel", up, { once: true });
    });
    head.addEventListener("dblclick", (e) => {
      if (e.target.closest("button")) return;
      Object.assign(box.style, { left: "", top: "", right: "", bottom: "" });
      try { localStorage.removeItem(SPOT); } catch { /* nothing kept */ }
    });
    const keep = () => { if (box.style.left) place(parseFloat(box.style.left), parseFloat(box.style.top)); };
    addEventListener("resize", keep);
    const sized = new ResizeObserver(keep);
    sized.observe(box);
    this.box = box;
    try { localStorage.setItem(OPEN, "1"); } catch { /* not remembered */ }

    const ctx = canvas.getContext("2d");
    const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const pulses = [];
    let last = null, raf = 0, dpr = 1, W = 0, H = 0, lastSpark = 0, lastDelta = 0, bg = null;
    let lastEvent = 0, lastSustain = 0, working = false;
    const followed = new Set();                           // the runs open now
    const fit = () => {
      dpr = Math.min(2, devicePixelRatio || 1);
      W = canvas.clientWidth; H = Math.round(W * TALL);
      canvas.style.height = `${H}px`;
      canvas.width = W * dpr; canvas.height = H * dpr;
      bg = W ? backdrop(W, H, dpr) : null;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(canvas);

    const turn = turnable(canvas, g, lobeAt, TALL, () => W);      // 3D: held and turned (brain_3d.js)
    const proj = turn.proj;

    const fire = (area, label) => {
      if (!area || !AREAS[area]) return;
      const mine = g.nodes.map((n, i) => [n, i]).filter(([n]) => n.area === area);
      for (const [n] of mine) if (Math.random() < 0.35) n.e = Math.min(1.4, n.e + 0.8);
      for (let k = 0; k < (calm ? 1 : 4); k++) {          // from the hub out into the area
        const to = mine[Math.floor(Math.random() * mine.length)]?.[1];
        const p = path(g.adj, g.hubs[area], to);
        if (p && p.length > 1) pulses.push({ p, s: 0, rgb: AREAS[area].rgb });
      }
      if (last && last !== area) {                       // the signal from the step before
        const p = path(g.adj, g.hubs[last], g.hubs[area]);
        if (p) pulses.push({ p, s: 0, rgb: AREAS[area].rgb, big: true });
      }
      last = area;
      lastEvent = performance.now();
      working = false;
      for (const [k, c] of Object.entries(chips)) c.classList.toggle("on", k === area);
      now.textContent = `${AREAS[area].icon} ${label || t(`brain.a.${area}`)}`;
      clearTimeout(this.quiet);
      // at rest only when no run is open: a model on the cloud answers in one call, with no event for a while
      const rest = () => {
        if (followed.size) { this.quiet = setTimeout(rest, 2000); return; }
        now.textContent = t("brain.idle");
        for (const c of Object.values(chips)) c.classList.remove("on");
        last = null; working = false;
      };
      this.quiet = setTimeout(rest, 6000);
    };
    const onEvent = (name) => {
      if (!this.box) return;
      if (name === "synthesis.delta") {                  // the words as they come: a light every 300 ms
        if (performance.now() - lastDelta < 300) return;
        lastDelta = performance.now();
      }
      const area = areaOf(name);
      // the step in words: its whole name first (pivot.back is not pivot), then its family, else its area
      const said = [`brain.e.${name}`, `brain.e.${name.split(".")[0]}`].map((k) => [k, t(k)]).find(([k, v]) => v !== k);
      if (area) fire(area, said ? said[1] : null);
    };
    this.onEvent = onEvent;

    const draw = (ts) => {
      raf = requestAnimationFrame(draw);
      if (document.hidden) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      const X = (x) => x * W, Y = (y) => y * W;
      turn.frame(ctx);                                    // the view glides home; the brain's body drawn
      const front = turn.front();                         // the drawing fits only from the front
      if (bg && front > 0.02) {
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = front; ctx.drawImage(bg, 0, 0); ctx.globalAlpha = 1;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      if (!calm && ts - lastSpark > 280) {                // her own quiet activity
        lastSpark = ts;
        const n = g.nodes[Math.floor(Math.random() * g.nodes.length)];
        n.e = Math.max(n.e, 0.5);
      }
      if (followed.size && last && ts - lastEvent > 1500 && ts - lastSustain > 450) {   // a long step: its area works on
        lastSustain = ts;
        // a tool's answer back and silence: the model is reasoning on it (an agent writes its answer in one go)
        const busy = last === "cerebellum" ? "frontal" : last;
        const mine = g.nodes.map((n, i) => [n, i]).filter(([n]) => n.area === busy);
        for (let k = 0; k < 4 && mine.length; k++) mine[Math.floor(Math.random() * mine.length)][0].e = 0.85;
        const to = mine[Math.floor(Math.random() * mine.length)]?.[1];
        const p = !calm && Math.random() < 0.5 ? path(g.adj, g.hubs[busy], to) : null;
        if (p && p.length > 1) pulses.push({ p, s: 0, rgb: AREAS[busy].rgb });
        if (!working) {
          working = true;
          for (const [k, c] of Object.entries(chips)) c.classList.toggle("on", k === busy);
          now.textContent = `${AREAS[busy].icon} ${t(busy === last ? "brain.working" : "brain.reasoning")}`;
        }
      }
      for (const n of g.nodes) n.e *= 0.965;
      for (const [i, j] of g.edges) {
        const a = g.nodes[i], b = g.nodes[j], e = Math.min(1, (a.e + b.e) / 2), far = (proj[i][2] + proj[j][2]) / 2;
        ctx.strokeStyle = e > 0.05 ? `rgba(${AREAS[a.area].rgb},${(0.18 + e * 0.6) * far})` : `rgba(170,190,240,${0.2 * far})`;
        ctx.lineWidth = (0.6 + e * 1.4) * far;
        ctx.beginPath(); ctx.moveTo(X(proj[i][0]), Y(proj[i][1])); ctx.lineTo(X(proj[j][0]), Y(proj[j][1])); ctx.stroke();
      }
      g.nodes.forEach((n, i) => {
        const [px, py, near] = proj[i];
        const tw = (0.45 + 0.2 * Math.sin(ts / 900 + n.tw)) * near;
        const e = Math.min(1, n.e);
        const r = (1.3 + e * 2.6) * near;
        if (e > 0.05) {
          ctx.fillStyle = `rgba(${AREAS[n.area].rgb},${0.18 * e})`;
          ctx.beginPath(); ctx.arc(X(px), Y(py), r * 3.2, 0, 6.283); ctx.fill();
        }
        ctx.fillStyle = e > 0.05 ? `rgba(${AREAS[n.area].rgb},${0.5 + e * 0.5})` : `rgba(200,212,245,${Math.min(1, tw)})`;
        ctx.beginPath(); ctx.arc(X(px), Y(py), r, 0, 6.283); ctx.fill();
      });
      for (let k = pulses.length - 1; k >= 0; k--) {     // the signals, along their synapses
        const p = pulses[k];
        p.s += p.big ? 0.32 : 0.22;
        const at = Math.floor(p.s);
        if (at >= p.p.length - 1) {
          const n = g.nodes[p.p[p.p.length - 1]];
          n.e = Math.min(1.4, n.e + 0.9);
          pulses.splice(k, 1);
          continue;
        }
        const a = g.nodes[p.p[at]], A = proj[p.p[at]], Bp = proj[p.p[at + 1]], f = p.s - at;
        a.e = Math.max(a.e, p.big ? 0.7 : 0.45);
        const x = X(A[0] + (Bp[0] - A[0]) * f), y = Y(A[1] + (Bp[1] - A[1]) * f);
        ctx.fillStyle = `rgba(${p.rgb},0.25)`;
        ctx.beginPath(); ctx.arc(x, y, p.big ? 7 : 5, 0, 6.283); ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,0.95)";
        ctx.beginPath(); ctx.arc(x, y, p.big ? 2.4 : 1.8, 0, 6.283); ctx.fill();
      }
    };
    raf = requestAnimationFrame(draw);

    // what runs now: the activity feed (this person's own), each run followed to its end. The feed starts «from now»:
    // a run begun before the widget opened, or while the feed was away (the API restarted), is found in the open runs
    const stop = new AbortController();
    const follow = (id) => {
      if (!id || followed.has(id)) return;
      followed.add(id);
      onEvent("run.begin");
      followRun(id, (e) => onEvent(e.event)).catch(() => { /* the run is gone */ }).finally(() => followed.delete(id));
    };
    const catchUp = () => call("/v1/aurora/runs").then((rs) => rs.filter((r) => !r.done).forEach((r) => follow(r.id)))
      .catch(() => { /* not now: the feed will say */ });
    (async () => {
      for (let attempt = 0; !stop.signal.aborted;) {
        const since = performance.now();
        catchUp();
        try {
          await stream("/v1/aurora/activity/stream", (a) => {
            if (a.event === "run.begin" && a.payload?.run_id) follow(a.payload.run_id);
            else if (!a.event.startsWith("run.")) onEvent(a.event.includes(".") ? a.event : `${a.source}.${a.event}`);
          }, stop.signal);
        } catch { /* closed or away: again in a moment */ }
        attempt = performance.now() - since > 30000 ? 0 : attempt + 1;   // a feed that held: the next try at once
        if (!stop.signal.aborted) await new Promise((r) => setTimeout(r, Math.min(15000, 1000 * attempt)));
      }
    })();

    let playing = 0;
    demo.addEventListener("click", () => {
      clearTimeout(playing);
      let i = 0;
      const next = () => { if (!this.box || i >= DEMO.length) return; onEvent(DEMO[i++]); playing = setTimeout(next, 900); };
      next();
    });
    full.addEventListener("click", () => {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      else box.requestFullscreen?.().catch(() => {});
    });
    shut.addEventListener("click", () => this.close());
    this.teardown = () => {
      cancelAnimationFrame(raf); ro.disconnect(); stop.abort(); clearTimeout(playing); clearTimeout(this.quiet);
      removeEventListener("resize", keep); sized.disconnect();
    };
  },

  close() {
    this.teardown?.();
    this.box?.remove();
    this.box = null;
    try { localStorage.setItem(OPEN, "0"); } catch { /* not remembered */ }
  },
};

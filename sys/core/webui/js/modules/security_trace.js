// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🌍 The visual traceroute (owner, 2026-10-10: «dato un indirizzo IP ti faceva vedere sul mappamondo gli hop fino ad
// arrivare alla posizione… dagli incident un tasto geolocalizza… con animazione sul globo terrestre»).
// A globe drawn here on a canvas (orthographic projection, Natural Earth's countries from world-atlas, no library):
// each hop flies in as soon as it answers (Server-Sent Events from net_trace), the globe turns towards it; a place the
// round trip makes impossible (a network's registered seat, not its router: light in fibre is ~200 km/ms) is dashed.
import { bus } from "../bus.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";

let pending = null;                                            // an address sent here from an incident
bus.on("trace", ({ ip }) => { pending = ip; });

const RAD = Math.PI / 180;
let world = null;

async function loadWorld() {                                   // TopoJSON → rings of [lon, lat]
  if (world) return world;
  const topo = await (await fetch("/static/vendor/world/countries-110m.json")).json();
  const { scale: [sx, sy], translate: [tx, ty] } = topo.transform;
  const arcs = topo.arcs.map((arc) => {
    let x = 0, y = 0;
    return arc.map(([dx, dy]) => { x += dx; y += dy; return [x * sx + tx, y * sy + ty]; });
  });
  const ring = (ids) => ids.flatMap((i, k) => {
    const a = i < 0 ? arcs[~i].slice().reverse() : arcs[i];
    return k ? a.slice(1) : a;
  });
  const rings = [];
  for (const g of topo.objects.countries.geometries) {
    const polys = g.type === "Polygon" ? [g.arcs] : g.type === "MultiPolygon" ? g.arcs : [];
    for (const p of polys) for (const r of p) rings.push(ring(r));
  }
  world = rings;
  return world;
}

// orthographic projection around (lon0, lat0): [x, y, visible]
function project(lon, lat, lon0, lat0, r, cx, cy) {
  const l = (lon - lon0) * RAD, p = lat * RAD, p0 = lat0 * RAD;
  const cosc = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(l);
  return [cx + r * Math.cos(p) * Math.sin(l), cy - r * (Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l)), cosc > 0];
}

// points along the great circle from a to b ([lon, lat]), k steps
function arcPoints(a, b, k = 48) {
  const v = ([lon, lat]) => [Math.cos(lat * RAD) * Math.cos(lon * RAD), Math.cos(lat * RAD) * Math.sin(lon * RAD), Math.sin(lat * RAD)];
  const A = v(a), B = v(b);
  const d = Math.acos(Math.min(1, Math.max(-1, A[0] * B[0] + A[1] * B[1] + A[2] * B[2])));
  const out = [];
  for (let i = 0; i <= k; i++) {
    const f = i / k;
    const s = d < 1e-6 ? [1 - f, f] : [Math.sin((1 - f) * d) / Math.sin(d), Math.sin(f * d) / Math.sin(d)];
    const x = s[0] * A[0] + s[1] * B[0], y = s[0] * A[1] + s[1] * B[1], z = s[0] * A[2] + s[1] * B[2];
    out.push([Math.atan2(y, x) / RAD, Math.atan2(z, Math.hypot(x, y)) / RAD, Math.sin(f * Math.PI) * Math.min(0.18, d / 3)]);
  }
  return out;
}

export default {
  id: "sectrace",
  icon: "🌍",
  title: "nav.sec.trace",
  plugin: "security",

  mount(root) {
    useCss("/static/css/trace.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.sec.trace"></h2><p class="muted" data-i18n="trace.hint"></p>
      <form class="appr-actions trace-form"><input class="trace-ip" data-i18n-placeholder="trace.ph">
        <button class="approve" type="submit" data-i18n="trace.go"></button><span class="muted trace-out"></span></form>
      <div class="trace-body"><canvas class="trace-globe"></canvas><div class="trace-list"></div></div>
      <p class="muted trace-credit"></p>`;
    apply(root);
    this.q = (s) => root.querySelector(s);
    this.canvas = this.q(".trace-globe");
    this.view = { lon: 12, lat: 42, to: null, drag: null };
    this.hops = [];
    this.q(".trace-form").addEventListener("submit", (e) => { e.preventDefault(); this.start(this.q(".trace-ip").value); });
    this.canvas.addEventListener("pointerdown", (e) => { this.view.drag = [e.clientX, e.clientY, this.view.lon, this.view.lat]; this.view.to = null; });
    window.addEventListener("pointerup", () => { this.view.drag = null; });
    this.canvas.addEventListener("pointermove", (e) => {
      const d = this.view.drag;
      if (!d) return;
      this.view.lon = d[2] - (e.clientX - d[0]) * 0.4;
      this.view.lat = Math.max(-80, Math.min(80, d[3] + (e.clientY - d[1]) * 0.4));
    });
    loadWorld().then(() => this.loop());
  },

  enter() {
    if (pending) { this.q(".trace-ip").value = pending; const ip = pending; pending = null; this.start(ip); }
  },

  start(target) {
    target = String(target || "").trim();
    if (!target) return;
    this.es?.close();
    this.hops = [];
    this.target = null;
    this.born = performance.now();
    this.q(".trace-list").replaceChildren();
    this.q(".trace-out").textContent = t("trace.running");
    this.es = new EventSource(`/v1/aurora/security/trace?target=${encodeURIComponent(target)}`);
    this.es.addEventListener("start", (m) => { this.target = JSON.parse(m.data); this.row(null); });
    this.es.addEventListener("hop", (m) => {
      const h = JSON.parse(m.data);
      h.at = performance.now();
      this.hops.push(h);
      const g = h.geo || {};
      if (g.lat != null) this.view.to = [g.lon, g.lat];
      this.row(h);
    });
    this.es.addEventListener("rtt", (m) => {
      const r = JSON.parse(m.data);
      const h = this.hops.find((x) => x.n === r.n);
      if (h && (h.ms == null || r.ms < h.ms)) { h.ms = r.ms; this.row(h); }
    });
    this.es.addEventListener("done", (m) => {
      const d = JSON.parse(m.data);
      for (const x of d.hops) { const h = this.hops.find((y) => y.n === x.n); if (h) { Object.assign(h, { ms: x.ms, plausible: x.plausible }); this.row(h); } }
      this.q(".trace-out").textContent = t(d.reached ? "trace.reached" : "trace.not_reached", { n: d.hops.length, s: d.seconds });
      this.q(".trace-credit").textContent = `${d.credit} · Natural Earth (world-atlas)`;
      this.es.close();
    });
    this.es.addEventListener("error", (m) => {
      let msg = t("trace.failed");
      try { msg = JSON.parse(m.data).message; } catch { /* the stream closed */ }
      if (this.es.readyState !== EventSource.CLOSED || m.data) this.q(".trace-out").textContent = `⚠️ ${msg}`;
      this.es.close();
    });
  },

  row(h) {                                                      // the list beside the globe, one line a hop
    const list = this.q(".trace-list");
    if (!h) {
      const g = this.target.geo || {};
      list.replaceChildren(el("div", "trace-target", `🎯 ${this.target.ip} · ${[g.city, g.country].filter(Boolean).join(", ") || "—"}${g.org ? ` · ${g.org}` : ""}`));
      return;
    }
    const g = h.geo || {};
    const where = g.public === false ? t("trace.private") : [g.city, g.country].filter(Boolean).join(", ") || "—";
    const line = el("div", `trace-hop${h.plausible === false ? " far" : ""}`);
    line.dataset.n = h.n;
    line.append(el("span", "trace-n", String(h.n)), el("span", "trace-ip-cell", h.ip),
      el("span", "", where + (h.plausible === false ? ` · ${t("trace.seat")}` : "")),
      el("span", "muted", g.org || ""), el("span", "trace-ms", h.ms != null ? `${h.ms} ms` : "…"));
    const old = list.querySelector(`.trace-hop[data-n="${h.n}"]`);
    if (old) old.replaceWith(line); else list.append(line);
  },

  loop() {
    const c = this.canvas;
    const draw = () => {
      if (!c.isConnected || !c.clientWidth) {                    // not shown yet (mounted before it is placed), or
        setTimeout(() => requestAnimationFrame(draw), 400);     // hidden: look again in a moment, never stop (C263)
        return;
      }
      const w = c.clientWidth, hgt = c.clientHeight, dpr = window.devicePixelRatio || 1;
      if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(hgt * dpr); }
      const g = c.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, hgt);
      const v = this.view;
      if (v.to && !v.drag) {                                    // turn towards the newest hop
        let dl = ((v.to[0] - v.lon + 540) % 360) - 180;
        v.lon += dl * 0.06;
        v.lat += (Math.max(-60, Math.min(60, v.to[1])) - v.lat) * 0.06;
        if (Math.abs(dl) < 0.05) v.to = null;
      } else if (!v.drag && !this.hops.length) v.lon += 0.08;   // idle: the Earth turns
      const r = Math.min(w, hgt) / 2 - 12, cx = w / 2, cy = hgt / 2;
      const sea = g.createRadialGradient(cx - r / 3, cy - r / 3, r / 6, cx, cy, r);
      sea.addColorStop(0, "#1b3a63"); sea.addColorStop(1, "#071425");
      g.fillStyle = sea; g.beginPath(); g.arc(cx, cy, r, 0, 2 * Math.PI); g.fill();
      g.strokeStyle = "rgba(120,170,255,.10)"; g.lineWidth = 1;    // meridians and parallels every 15°
      for (let lon = -180; lon < 180; lon += 15) this.path(g, Array.from({ length: 37 }, (_, i) => [lon, -90 + i * 5]), r, cx, cy, false);
      for (let lat = -75; lat <= 75; lat += 15) this.path(g, Array.from({ length: 73 }, (_, i) => [-180 + i * 5, lat]), r, cx, cy, false);
      g.fillStyle = "#24476b"; g.strokeStyle = "rgba(160,200,255,.35)"; g.lineWidth = 0.6;
      for (const ring of world) this.path(g, ring, r, cx, cy, true);
      g.strokeStyle = "rgba(120,180,255,.5)"; g.lineWidth = 1.5; g.beginPath(); g.arc(cx, cy, r, 0, 2 * Math.PI); g.stroke();
      this.route(g, r, cx, cy);
      requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
  },

  path(g, pts, r, cx, cy, fill) {                               // a line or a land ring, cut where it goes behind
    const v = this.view;
    g.beginPath();
    let on = false, any = false;
    for (const [lon, lat] of pts) {
      const [x, y, vis] = project(lon, lat, v.lon, v.lat, r, cx, cy);
      if (vis) { if (on) g.lineTo(x, y); else g.moveTo(x, y); on = true; any = true; } else on = false;
    }
    if (!any) return;
    if (fill) { g.closePath(); g.fill(); }
    g.stroke();
  },

  route(g, r, cx, cy) {                                         // the hops placed, joined in the order they came
    const v = this.view, now = performance.now();
    const placed = this.hops.filter((h) => h.geo?.lat != null);
    const tgt = this.target?.geo;
    for (let i = 1; i < placed.length; i++) {
      const a = placed[i - 1], b = placed[i];
      const grow = Math.min(1, (now - b.at) / 900);             // each arc flies out in 0.9 s
      const pts = arcPoints([a.geo.lon, a.geo.lat], [b.geo.lon, b.geo.lat]);
      const k = Math.max(1, Math.round(pts.length * grow));
      g.setLineDash(b.plausible === false ? [5, 5] : []);
      g.strokeStyle = b.plausible === false ? "rgba(255,190,90,.6)" : "rgba(91,208,255,.9)";
      g.lineWidth = 2;
      g.beginPath();
      let on = false;
      for (const [lon, lat, h] of pts.slice(0, k)) {
        const [x, y, vis] = project(lon, lat, v.lon, v.lat, r * (1 + h), cx, cy);
        if (vis) { if (on) g.lineTo(x, y); else g.moveTo(x, y); on = true; } else on = false;
      }
      g.stroke();
      g.setLineDash([]);
    }
    placed.forEach((h, i) => {
      const [x, y, vis] = project(h.geo.lon, h.geo.lat, v.lon, v.lat, r, cx, cy);
      if (!vis) return;
      const last = i === placed.length - 1;
      const pulse = last ? 3 + 3 * Math.abs(Math.sin((now - h.at) / 300)) : 0;
      g.fillStyle = h.plausible === false ? "rgba(255,190,90,.9)" : (last ? "#ff5d73" : "#5bd0ff");
      g.beginPath(); g.arc(x, y, 3.5 + pulse, 0, 2 * Math.PI); g.fill();
      g.fillStyle = "#e8f0ff"; g.font = "11px sans-serif";
      g.fillText(`${h.n} ${h.geo.city || h.geo.country || ""}`, x + 7, y - 6);
    });
    if (tgt?.lat != null) {                                     // the address itself: a target ring
      const [x, y, vis] = project(tgt.lon, tgt.lat, v.lon, v.lat, r, cx, cy);
      if (vis) { g.strokeStyle = "#ff5d73"; g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 9, 0, 2 * Math.PI); g.stroke(); }
    }
  },
};

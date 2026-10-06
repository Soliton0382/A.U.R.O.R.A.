// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🗺️ The network drawn (owner, 2026-10-06): the firewall in the middle, its interfaces around it coloured by zone,
// each device on the ring of the interface whose network holds its address; circles are reserved DHCP addresses,
// squares hosts named on the firewall. Wheel or ± to zoom, drag to move, a device's name and address on hover.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const NS = "http://www.w3.org/2000/svg";
const ZONE = { LAN: "#5bd08a", WAN: "#f0a04b", DMZ: "#b48cff", VPN: "#4bb8f0", WiFi: "#f06b9a" };
const svg = (tag, attrs = {}, text = "") => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text) e.textContent = text;
  return e;
};
const colour = (zone) => ZONE[zone] || "#9aa3b2";

// rings around a centre: as many devices as fit at 34 px apart on each ring
function rings(n, first = 70, step = 42, gap = 34) {
  const out = [];
  for (let r = first; out.length < n; r += step) {
    const fit = Math.max(6, Math.floor((2 * Math.PI * r) / gap));
    for (let k = 0; k < fit && out.length < n; k++) {
      const left = Math.min(fit, n - out.length + k);
      const a = (2 * Math.PI * k) / left;
      out.push([r * Math.cos(a), r * Math.sin(a)]);
    }
  }
  return out;
}

function draw(g) {
  const groups = [...g.interfaces];
  if (g.other.length) groups.push({ name: t("sec.map_other"), zone: "", network: "", devices: g.other });
  const spots = groups.map((x) => rings(x.devices.length));
  const reach = spots.map((p) => (p.length ? Math.max(...p.map(([x, y]) => Math.hypot(x, y))) : 0) + 40);
  const R = Math.max(220, (Math.max(...reach, 60) * 1.15) / Math.sin(Math.PI / Math.max(groups.length, 2)));
  const root = svg("svg", { class: "net-map", viewBox: `${-R - 300} ${-R - 300} ${2 * R + 600} ${2 * R + 600}` });
  const world = svg("g");
  root.append(world);
  groups.forEach((grp, i) => {
    const a = (2 * Math.PI * i) / groups.length - Math.PI / 2, cx = R * Math.cos(a), cy = R * Math.sin(a), c = colour(grp.zone);
    world.append(svg("line", { x1: 0, y1: 0, x2: cx, y2: cy, stroke: c, "stroke-width": 3, opacity: 0.6 }));
    spots[i].forEach(([dx, dy], k) => {
      const d = grp.devices[k], x = cx + dx, y = cy + dy;
      world.append(svg("line", { x1: cx, y1: cy, x2: x, y2: y, stroke: c, "stroke-width": 0.6, opacity: 0.25 }));
      const node = d.kind === "host"
        ? svg("rect", { x: x - 6, y: y - 6, width: 12, height: 12, rx: 2, fill: c })
        : svg("circle", { cx: x, cy: y, r: 6.5, fill: c });
      const tip = svg("title", {}, `${d.name} (${d.ip})${d.groups?.length ? ` · ${d.groups.join(", ")}` : ""}`);
      const item = svg("g", { class: "net-dev" });
      item.append(node, tip, svg("text", { x, y: y + 17, "text-anchor": "middle", class: "net-label" }, d.name.slice(0, 18)));
      world.append(item);
    });
    const hub = svg("g", { class: "net-hub" });
    hub.append(svg("circle", { cx, cy, r: 26, fill: "#1b2130", stroke: c, "stroke-width": 3 }),
      svg("text", { x: cx, y: cy - 2, "text-anchor": "middle", class: "net-hub-name" }, grp.name),
      svg("text", { x: cx, y: cy + 12, "text-anchor": "middle", class: "net-hub-zone" }, grp.zone || ""),
      svg("title", {}, `${grp.name} ${grp.zone || ""} ${grp.network || ""} · ${grp.devices.length}`));
    world.append(hub);
  });
  const fw = svg("g", { class: "net-hub" });
  fw.append(svg("circle", { cx: 0, cy: 0, r: 38, fill: "#262d3d", stroke: "#e8ecf3", "stroke-width": 3 }),
    svg("text", { x: 0, y: 6, "text-anchor": "middle", class: "net-fw" }, "🧱"));
  world.append(fw);
  return root;
}

// zoom and pan by changing the viewBox: the wheel, the ± buttons, a drag (mouse or finger)
function interact(root) {
  let [x, y, w, h] = root.getAttribute("viewBox").split(" ").map(Number);
  const set = () => root.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
  const zoom = (f, cx = x + w / 2, cy = y + h / 2) => { x = cx - (cx - x) * f; y = cy - (cy - y) * f; w *= f; h *= f; set(); };
  root.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = root.getBoundingClientRect();
    zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, x + ((e.clientX - r.left) / r.width) * w, y + ((e.clientY - r.top) / r.height) * h);
  }, { passive: false });
  let drag = null;
  root.addEventListener("pointerdown", (e) => { drag = [e.clientX, e.clientY]; root.setPointerCapture(e.pointerId); });
  root.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const r = root.getBoundingClientRect();
    x -= ((e.clientX - drag[0]) / r.width) * w; y -= ((e.clientY - drag[1]) / r.height) * h;
    drag = [e.clientX, e.clientY]; set();
  });
  root.addEventListener("pointerup", () => { drag = null; });
  return zoom;
}

export async function openMap() {
  const dlg = el("dialog", "modal plug-modal net-modal");
  const close = el("button", "icon close", "✕");
  close.addEventListener("click", () => { dlg.close(); dlg.remove(); });
  const head = el("div", "plug-head");
  head.append(el("h3", "", t("sec.map")), close);
  dlg.append(head, el("p", "muted", "…"));
  document.body.append(dlg);
  dlg.showModal();
  let g;
  try { g = await call("/v1/aurora/security/netmap/graph"); } catch (e) { dlg.lastChild.textContent = t("ev.error", { m: e.message }); return; }
  if (!g.at) { dlg.lastChild.textContent = t("sec.map_none"); return; }
  const pic = draw(g);
  const zoom = interact(pic);
  const bar = el("div", "appr-actions");
  const plus = el("button", "", "＋"), minus = el("button", "", "－");
  plus.addEventListener("click", () => zoom(1 / 1.3));
  minus.addEventListener("click", () => zoom(1.3));
  const n = g.interfaces.reduce((s, i) => s + i.devices.length, 0) + g.other.length;
  bar.append(plus, minus, el("span", "muted", t("sec.map_legend", { n, when: new Date(g.at * 1000).toLocaleString() })));
  dlg.lastChild.replaceWith(bar);
  dlg.append(pic);
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Live CPU, RAM, GPU memory, the network's traffic and the cloud calls in the top bar (every 2 s while the page is
// visible). On a phone each is an icon and a number (owner, 2026-10-13: «sul mobile occupano un po' di spazio, magari
// potremmo usare icone e percentuali… manca qualcosa che indica le connessioni verso il cloud»); the full figures stay
// in each one's tooltip, and on a wide screen as before.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";

const gb = (mib) => (mib / 1024).toFixed(1);
const pct = (f) => `${Math.round(Math.max(0, Math.min(1, f || 0)) * 100)}%`;
const rate = (bps) => (bps == null ? "…" : bps >= 1e6 ? `${(bps / 1e6).toFixed(1)} MB/s` : `${Math.round(bps / 1e3)} kB/s`);

function gauge(label, icon, withLoad = false) {
  const g = el("div", "gauge");
  const bar = el("span", "bar");
  bar.append(el("span", "fill"));
  g.append(el("span", "icon", icon), el("span", "label", label), bar, el("span", "value"), el("span", "short"));
  if (withLoad) g.append(el("span", "load"));
  return g;
}

function set(g, frac, text, title, short) {
  const f = Math.max(0, Math.min(1, frac || 0));
  const fill = g.querySelector(".fill");
  fill.style.width = `${(f * 100).toFixed(0)}%`;
  fill.className = `fill${f > 0.9 ? " hot" : f > 0.75 ? " warm" : ""}`;
  g.querySelector(".value").textContent = text;
  g.querySelector(".short").textContent = short ?? pct(f);
  g.title = title || text;
}

export default {
  id: "metrics",
  slot: "topbar",

  mount(root) {
    useCss("/static/css/metrics.css");
    const box = el("div", "metrics");
    root.append(box);
    const cpu = gauge("CPU", "⚙️"), ram = gauge("RAM", "💾");
    const net = gauge("NET", "🌐"), cloud = gauge("CLOUD", "☁️");
    net.classList.add("net");
    cloud.classList.add("cloud");
    box.append(cpu, ram);
    const gpus = [];
    let timer = 0, placed = false;

    const tick = async () => {
      try {
        const m = await call("/v1/aurora/metrics");
        set(cpu, (m.cpu_pct ?? 0) / 100, m.cpu_pct === null ? "…" : `${Math.round(m.cpu_pct)}%`, `CPU ${m.cpu_pct ?? "…"}%`);
        set(ram, m.ram.used_mib / m.ram.total_mib, `${gb(m.ram.used_mib)}/${gb(m.ram.total_mib)} GB`,
          `RAM ${gb(m.ram.used_mib)}/${gb(m.ram.total_mib)} GB · swap ${gb(m.ram.swap_used_mib)} GB`);
        m.gpus.forEach((g, i) => {
          if (!gpus[i]) { gpus[i] = gauge(`GPU${g.index}`, `🎮${g.index}`, true); box.append(gpus[i]); }
          set(gpus[i], g.used_mib / g.total_mib, `${gb(g.used_mib)}/${gb(g.total_mib)} GB`,
            `${g.name} · VRAM ${gb(g.used_mib)}/${gb(g.total_mib)} GB · load ${g.util_pct}% · ${g.temp_c} °C`);
          const load = gpus[i].querySelector(".load");
          load.textContent = `${g.util_pct}%`;
          load.className = `load${g.util_pct >= 90 ? " hot" : g.util_pct >= 50 ? " warm" : ""}`;
        });
        if (!placed) { box.append(net, cloud); placed = true; }        // after the GPUs: the same place every time
        const n = m.net || {};
        const both = (n.rx_bps ?? 0) + (n.tx_bps ?? 0);
        set(net, (n.pct ?? 0) / 100, `↓${rate(n.rx_bps)} ↑${rate(n.tx_bps)}`,
          `Rete: ↓ ${rate(n.rx_bps)} · ↑ ${rate(n.tx_bps)}${n.link_mbps ? ` · ${n.pct ?? 0}% di ${n.link_mbps} Mbit/s` : ""}`,
          n.rx_bps == null ? "…" : rate(both));
        const c = m.cloud || { active: 0, calls: 0, sent: 0, received: 0, providers: [] };
        set(cloud, Math.min(1, c.calls / 30), c.active ? `${c.active} in corso · ${c.calls}/min` : `${c.calls}/min`,
          `Cloud: ${c.active} chiamate in corso, ${c.calls} nell'ultimo minuto` +
          (c.calls ? ` (${c.providers.join(", ")}) · inviati ${Math.round(c.sent / 1000)}k caratteri mascherati, ricevuti ${Math.round(c.received / 1000)}k` : ""),
          c.active ? `${c.active}·${c.calls}/m` : `${c.calls}/m`);
        cloud.classList.toggle("live", c.active > 0);
        net.classList.toggle("live", both > 1e6);
        box.classList.toggle("busy", !!m.busy);
      } catch { /* logged out or offline: try again later */ }
    };
    const start = () => { if (!timer && !document.hidden) { tick(); timer = setInterval(tick, 2000); } };
    const stop = () => { clearInterval(timer); timer = 0; };
    document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
    this.start = start;
  },

  enter() { this.start(); },
};

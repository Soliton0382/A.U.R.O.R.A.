// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Live CPU, RAM, GPU memory, the network's traffic and the cloud calls in the top bar (every 2 s while the page is
// visible). On a phone each is an icon and a number (owner, 2026-10-13: «sul mobile occupano un po' di spazio, magari
// potremmo usare icone e percentuali… manca qualcosa che indica le connessioni verso il cloud»); the full figures stay
// in each one's tooltip, and on a wide screen as before.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { t } from "../i18n.js";

const gb = (mib) => (mib / 1024).toFixed(1);
const pct = (f) => `${Math.round(Math.max(0, Math.min(1, f || 0)) * 100)}%`;
const rate = (bps) => (bps == null ? "…" : bps >= 1e6 ? `${(bps / 1e6).toFixed(1)} MB/s` : `${Math.round(bps / 1e3)} kB/s`);

// a processor's chip, drawn: no emoji is one (owner, 2026-10-20: «sostituisci l'icona ingranaggio con un chip»)
const CHIP = `<svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true" fill="none" stroke="currentColor"
  stroke-width="1.8" stroke-linecap="round"><rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5"
  height="5" rx=".8" fill="currentColor" stroke="none"/><path d="M9 2.5v3M12 2.5v3M15 2.5v3M9 18.5v3M12 18.5v3M15 18.5v3
  M2.5 9h3M2.5 12h3M2.5 15h3M18.5 9h3M18.5 12h3M18.5 15h3"/></svg>`;

function gauge(label, icon, withLoad = false) {
  const g = el("div", "gauge");
  const bar = el("span", "bar");
  bar.append(el("span", "fill"));
  const ic = el("span", "icon");
  if (icon === "chip") { ic.innerHTML = CHIP; ic.classList.add("chip"); } else ic.textContent = icon;
  g.append(ic, el("span", "label", label), bar, el("span", "value"), el("span", "short"));
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
    const cpu = gauge("CPU", "chip"), ram = gauge("RAM", "💾");
    const net = gauge("NET", "🌐"), cloud = gauge("CLOUD", "☁️");
    net.classList.add("net");
    cloud.classList.add("cloud");
    // the next 3 hours at home (owner, 2026-10-20): its icon and the temperature beside Aurora's mood, not in this bar
    // («lo metterei di fianco allo stato d'animo… così il resto non si spagina»), the words in the tooltip; read
    // every 15 minutes (the server keeps it as long), hidden when the weather has no place
    const wx = el("span", "wx-chip");
    wx.hidden = true;
    (document.getElementById("slot-health") || box).append(wx);
    box.append(cpu, ram);
    const sky = async () => {
      try {
        const n = (await call("/v1/aurora/weather/next")).next;
        wx.hidden = !n;
        if (!n) return;
        const temp = n.t_min === n.t_max ? `${n.t_max}°` : `${n.t_min}–${n.t_max}°`;
        wx.replaceChildren(el("span", "wx-icon", n.icon), el("span", "wx-temp", temp));
        wx.title = t("wx.next", { h: n.hours, words: n.words, temp, p: n.rain_pct, mm: n.rain_mm });
      } catch { /* offline: try again later */ }
    };
    sky();
    setInterval(() => { if (!document.hidden) sky(); }, 15 * 60_000);
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

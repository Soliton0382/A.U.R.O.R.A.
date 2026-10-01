// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Live CPU, RAM and GPU memory in the top bar (every 2 s while the page is visible).
import { call } from "../api.js";
import { el, useCss } from "../dom.js";

const gb = (mib) => (mib / 1024).toFixed(1);

function gauge(label, withLoad = false) {
  const g = el("div", "gauge");
  const bar = el("span", "bar");
  bar.append(el("span", "fill"));
  g.append(el("span", "label", label), bar, el("span", "value"));
  if (withLoad) g.append(el("span", "load"));
  return g;
}

function set(g, frac, text, title) {
  const f = Math.max(0, Math.min(1, frac || 0));
  const fill = g.querySelector(".fill");
  fill.style.width = `${(f * 100).toFixed(0)}%`;
  fill.className = `fill${f > 0.9 ? " hot" : f > 0.75 ? " warm" : ""}`;
  g.querySelector(".value").textContent = text;
  g.title = title || text;
}

export default {
  id: "metrics",
  slot: "topbar",

  mount(root) {
    useCss("/static/css/metrics.css");
    const box = el("div", "metrics");
    root.append(box);
    const cpu = gauge("CPU"), ram = gauge("RAM");
    box.append(cpu, ram);
    const gpus = [];
    let timer = 0;

    const tick = async () => {
      try {
        const m = await call("/v1/aurora/metrics");
        set(cpu, (m.cpu_pct ?? 0) / 100, m.cpu_pct === null ? "…" : `${Math.round(m.cpu_pct)}%`);
        set(ram, m.ram.used_mib / m.ram.total_mib, `${gb(m.ram.used_mib)}/${gb(m.ram.total_mib)} GB`,
          `RAM ${gb(m.ram.used_mib)}/${gb(m.ram.total_mib)} GB · swap ${gb(m.ram.swap_used_mib)} GB`);
        m.gpus.forEach((g, i) => {
          if (!gpus[i]) { gpus[i] = gauge(`GPU${g.index}`, true); box.append(gpus[i]); }
          set(gpus[i], g.used_mib / g.total_mib, `${gb(g.used_mib)}/${gb(g.total_mib)} GB`,
            `${g.name} · VRAM ${gb(g.used_mib)}/${gb(g.total_mib)} GB · load ${g.util_pct}% · ${g.temp_c} °C`);
          const load = gpus[i].querySelector(".load");
          load.textContent = `${g.util_pct}%`;
          load.className = `load${g.util_pct >= 90 ? " hot" : g.util_pct >= 50 ? " warm" : ""}`;
        });
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

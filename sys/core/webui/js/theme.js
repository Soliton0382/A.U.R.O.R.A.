// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Colour themes (owner, 2026-10-08: «i template di visualizzazione che cambiano le combinazioni colori»): the 🎨
// button at the foot of the menu, for every user; each person's on the server since 15 Oct («leghiamo le
// configurazioni agli utenti e non ai device»: /v1/aurora/me/prefs, taken at login by style.adopt), this browser a copy
// so the page opens in its colours at once. The colours are in css/themes.css, as tokens only.
import { call } from "./api.js";
import { el } from "./dom.js";
import { t } from "./i18n.js";

// id, the colours of its preview (background, panel, accent, text), the bar colour of the phone
export const THEMES = [
  { id: "aurora", dots: ["#020617", "#11141c", "#7aa2ff", "#e6e8ee"], bar: "#020617" },
  { id: "notte", dots: ["#000000", "#0a0a0e", "#b18cff", "#ece8f6"], bar: "#000000" },
  { id: "oceano", dots: ["#021a1f", "#08222a", "#3fd0c9", "#e2f4f4"], bar: "#021a1f" },
  { id: "foresta", dots: ["#04140b", "#0c1d13", "#6fd08c", "#e4f2e8"], bar: "#04140b" },
  { id: "tramonto", dots: ["#1a0b10", "#24111a", "#ff9a6a", "#f7e8e2"], bar: "#1a0b10" },
  { id: "chiaro", dots: ["#eef2f8", "#ffffff", "#2f5fd0", "#1a2233"], bar: "#eef2f8" },
  { id: "contrasto", dots: ["#000000", "#111111", "#ffd400", "#ffffff"], bar: "#000000" },
];
const KEY = "aurora.theme";

export function current() {
  try { return localStorage.getItem(KEY) || "aurora"; } catch { return "aurora"; }
}

// `save`: a person's choice, kept on the server too (not the boot's or the login's own apply)
export function applyTheme(id, save = false) {
  if (save) call("/v1/aurora/me/prefs", { method: "PUT", body: JSON.stringify({ theme: id }) }).catch(() => { /* kept here */ });
  const th = THEMES.find((x) => x.id === id) || THEMES[0];
  if (th.id === "aurora") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = th.id;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", th.bar);
  try { localStorage.setItem(KEY, th.id); } catch { /* private window: this visit only */ }
}

// the Appearance dialog: the menu's style (style.js) above, the colours below; each person's own choice
export function themePicker({ style, onStyle, onWelcome } = {}) {
  const dlg = el("dialog", "modal");
  const close = el("button", "icon close", "✕");
  close.addEventListener("click", () => { dlg.close(); dlg.remove(); });
  const head = el("div", "plug-head");
  head.append(el("h3", "", `🎨 ${t(onStyle ? "style.dialog" : "theme.title")}`), close);
  const row = el("div", "theme-row");
  const draw = () => row.replaceChildren(...THEMES.map((th) => {
    const b = el("button", `theme-swatch${current() === th.id ? " on" : ""}`);
    b.type = "button";
    const dots = el("span", "dots");
    for (const c of th.dots) { const d = el("span"); d.style.background = c; dots.append(d); }
    b.append(dots, el("span", "", t(`theme.${th.id}`)));
    b.addEventListener("click", () => { applyTheme(th.id, true); draw(); });
    return b;
  }));
  draw();
  const parts = [head];
  if (onStyle) {
    let picked = style;
    const styles = el("div", "style-row");
    const drawStyles = () => styles.replaceChildren(...["completo", "essenziale", "misto"].map((id) => {
      const b = el("button", `style-pick${picked === id ? " on" : ""}`);
      b.type = "button";
      b.setAttribute("aria-pressed", String(picked === id));
      b.append(el("strong", "", t(`style.${id}`)), el("small", "muted", t(`style.${id}.hint`)));
      b.addEventListener("click", () => { picked = id; onStyle(id); drawStyles(); });
      return b;
    }));
    drawStyles();
    parts.push(el("h4", "", t("style.title")), styles, el("h4", "", t("theme.colours")));
  }
  dlg.append(...parts, el("p", "muted", t("theme.hint")), row);
  if (onWelcome) {
    const again = el("button", "", `🧭 ${t("wl.again")}`);
    again.type = "button";
    again.addEventListener("click", () => { dlg.close(); dlg.remove(); onWelcome(); });
    dlg.append(again);
  }
  document.body.append(dlg);
  dlg.showModal();
}

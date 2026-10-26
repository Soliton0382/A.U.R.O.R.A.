// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📚 Projects → Papers: the user's works (the publications plugin, from Zenodo by ORCID) as cards, like the GitHub
// ones: views and downloads (unique, and every one), the change since yesterday and in a week, the versions, the
// licence, the keywords, and the views day by day once more than one day is kept. Reading only.
import { el } from "../dom.js";
import { t } from "../i18n.js";

const SVGNS = "http://www.w3.org/2000/svg";
const plus = (n) => (n > 0 ? `+${n}` : String(n ?? 0));
const KIND = { Software: "💾", Dataset: "🗃️", Presentation: "🖥️", Poster: "🪧", Image: "🖼️", Video: "🎞️" };

function stat(label, value, small) {
  const s = el("div", "mch-stat");
  s.append(el("small", "", label), el("strong", "", value), el("small", "", small || ""));
  return s;
}

// the totals over every work, with the change since yesterday
export function papersHead(items) {
  const sum = (f) => items.reduce((n, w) => n + (f(w) || 0), 0);
  const dv = sum((w) => (w.day || {}).views), dd = sum((w) => (w.day || {}).downloads);
  const box = el("div", "mch-stats prj-papers-head");
  box.append(stat(t("prj.papers_works"), String(items.length), ""),
    stat(`👁️ ${t("prj.paper_views")}`, sum((w) => w.views).toLocaleString(), items.some((w) => w.day) ? t("prj.paper_since_day", { n: plus(dv) }) : ""),
    stat(`⬇️ ${t("prj.paper_downloads")}`, sum((w) => w.downloads).toLocaleString(), items.some((w) => w.day) ? t("prj.paper_since_day", { n: plus(dd) }) : ""));
  return box;
}

// one work's views day by day: a thin line, a dot and its numbers under the pointer; nothing with one day only
function trend(history) {
  if (!history || history.length < 2) return el("small", "muted", t("prj.paper_trend_soon"));
  const W = 240, H = 44, P = 4;
  const vs = history.map((h) => h.views || 0);
  const lo = Math.min(...vs), hi = Math.max(...vs, lo + 1);
  const x = (i) => P + (i * (W - 2 * P)) / (history.length - 1);
  const y = (v) => H - P - ((v - lo) * (H - 2 * P)) / (hi - lo);
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "prj-paper-trend");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", t("prj.paper_trend", { a: vs[0], b: vs[vs.length - 1], n: history.length }));
  const line = document.createElementNS(SVGNS, "path");
  line.setAttribute("d", vs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(""));
  line.setAttribute("class", "sim-line");
  const dot = document.createElementNS(SVGNS, "circle");
  dot.setAttribute("r", "4");
  dot.setAttribute("class", "sim-dot");
  dot.style.display = "none";
  svg.append(line, dot);
  const tip = el("div", "sim-tip", "");
  svg.addEventListener("pointermove", (ev) => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(history.length - 1, Math.round(((ev.clientX - r.left) / r.width * W - P) / (W - 2 * P) * (history.length - 1))));
    dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(vs[i])); dot.style.display = "";
    tip.textContent = `${history[i].day} · 👁️ ${history[i].views} · ⬇️ ${history[i].downloads}`;
  });
  svg.addEventListener("pointerleave", () => { dot.style.display = "none"; tip.textContent = ""; });
  const box = el("div", "prj-paper-trendbox");
  box.append(svg, tip);
  return box;
}

export function paperCard(w) {
  const c = el("div", "mch-card prj-card prj-remote prj-paper");
  const year = String(w.published || "").slice(0, 4);
  c.append(el("div", "prj-cover prj-cover-gh prj-cover-paper", `${KIND[w.kind] || "📄"} ${w.kind || t("prj.paper")}${year ? ` · ${year}` : ""}`));
  const head = el("div", "mch-head");
  head.append(el("strong", "prj-paper-title", w.title));
  if ((w.versions || 1) > 1) head.append(el("span", "mch-tag", t("prj.paper_versions", { n: w.versions })));
  c.append(head);
  if (w.keywords?.length) c.append(el("div", "mch-line prj-what muted", w.keywords.join(" · ")));
  const stats = el("div", "mch-stats");
  stats.append(stat(`👁️ ${t("prj.paper_views")}`, String(w.views), t("prj.paper_all", { n: w.views_all ?? w.views })),
    stat(`⬇️ ${t("prj.paper_downloads")}`, String(w.downloads), t("prj.paper_all", { n: w.downloads_all ?? w.downloads })));
  const ch = (k) => (k ? `👁️ ${plus(k.views)} · ⬇️ ${plus(k.downloads)}` : "—");
  stats.append(stat(t("prj.paper_day"), ch(w.day), ""), stat(t("prj.paper_week"), ch(w.week), ""));
  c.append(stats, trend(w.history));
  const foot = el("div", "mch-price prj-gh-foot");
  const a = el("a", "", w.url.includes("doi.org/") ? `🔗 ${w.url.split("doi.org/")[1]}` : t("prj.paper_open"));
  a.href = w.url; a.target = "_blank"; a.rel = "noopener noreferrer";
  foot.append(a);
  if (w.published) foot.append(el("span", "muted", w.published));
  if (w.license) foot.append(el("span", "muted", w.license.toUpperCase()));
  c.append(foot);
  return c;
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ☀️ Any page as a tile of Oggi (owner, 2026-10-19: «la possibilità di aggiungere qualsiasi cosa l'utente desidera… in
// base a quello che può fare con il suo utente… come hai fatto con il menù cliccando sulla piantina»). The pages offered
// are the full menu's as this person sees it (a user's, a plugin's switched off: hidden the same way, their API refusing
// them anyway). A page with a tile of its own (the agenda for the calendar…) turns that on; a few say a line of their
// state; every other one is a shortcut.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

// a page whose own tile Oggi already has
export const BUILTIN = { calendar: "agenda", astro: "sky", home: "house", approvals: "waiting", usage: "stats",
  dreams: "dream", status: "health", reports: "research" };

// the pages this person may open, as the full menu shows them: [{id, icon, label}]
export function pages() {
  const full = document.querySelector("#nav .nav-full");
  if (!full) return [];
  return [...full.querySelectorAll("button[data-view]")]
    .filter((b) => !b.classList.contains("hidden") && !b.closest(".nav-group.hidden") && !["today", "advanced"].includes(b.dataset.view))
    .map((b) => ({ id: b.dataset.view, icon: b.querySelector(".ic")?.textContent || "", label: b.querySelector(".label")?.textContent || b.dataset.view }));
}

const ago = (s) => new Date(s * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const firstLine = (x) => String(x || "").split(/\n+/).map((l) => l.replace(/[#*_`>]/g, "").trim()).find(Boolean)?.slice(0, 160) || "";

// a page's state in a few lines, from the API the page itself reads
const SAY = {
  async routines() {
    const d = await call("/v1/aurora/routines");
    const on = d.routines.filter((r) => r.enabled);
    const bad = on.filter((r) => r.last_run && r.last_ok === false);
    const last = [...on].sort((a, b) => (b.last_run || 0) - (a.last_run || 0))[0];
    const out = [el("p", "", t("today.pg.routines", { n: on.length, bad: bad.length }))];
    if (last?.last_run) out.push(el("small", "muted", `${last.last_ok === false ? "⚠️" : "✅"} ${last.title} · ${ago(last.last_run)}`));
    return out;
  },
  async projects() {
    const d = await call("/v1/aurora/projects");
    const busy = d.projects.filter((p) => p.changes > 0);
    return [el("p", "", t("today.pg.projects", { n: d.projects.length, busy: busy.length }))];
  },
  async ideas() {
    const d = await call("/v1/aurora/ideas");
    return [el("p", "", t("today.pg.ideas", { n: d.ideas.length }))];
  },
  async diary() {
    const r = (await call("/v1/aurora/reflections"))[0];
    return r ? [el("p", "", firstLine(r.text)), el("small", "muted", String(r.created_at).slice(0, 10))] : [];
  },
  async dj() {
    const d = await call("/v1/aurora/dj");
    const last = [...d.mixes].sort((a, b) => b.at - a.at)[0];
    return [el("p", "", t("today.pg.dj", { tracks: d.tracks.length, mixes: d.mixes.length })), ...(last ? [el("small", "muted", `🎧 ${last.name}`)] : [])];
  },
  async social() {
    const d = await call("/v1/aurora/social");
    const out = [el("p", "", t("today.pg.social", { n: d.platforms.filter((p) => p.available).length }))];
    if (d.last_report) out.push(el("small", "muted", firstLine(d.last_report.text)));
    return out;
  },
  async updates() {
    const d = await call("/v1/aurora/update");
    return [el("p", "", d.error ? `⚠️ ${d.error}` : t("today.pg.updates", { when: d.checked ? ago(d.checked) : "—" }))];
  },
};

// the tile of one page: its state when it has a way to say it, else a shortcut; null when the person may not open it
export async function pageTile(id, ctx) {
  const p = pages().find((x) => x.id === id);
  if (!p) return null;
  const s = el("section", "td-tile td-page");
  s.append(el("h3", "", `${p.icon} ${p.label}`));
  if (SAY[id]) {
    const lines = await SAY[id]().catch(() => []);
    s.append(...lines);
  }
  const open = el("button", "link", t("today.pg.open", { page: p.label }));
  open.type = "button";
  open.addEventListener("click", () => ctx.show(id));
  s.append(open);
  return s;
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📊 How Aurora is used (owner, 2026-10-17: «una statistica generale per tenere traccia di tutto il tipo di utilizzo…
// niente dati personali»): questions, agent runs, model and tool calls per day and per user — counts and durations
// only. The admin sees everyone and Aurora's own work; a user only their own (the API decides).
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
const PERIODS = [1, 7, 30, 90];
const loc = () => lang.replace("_", "-");
const n = (x) => Math.round(x || 0).toLocaleString(loc());
const dec = (x, d = 1) => (x || 0).toLocaleString(loc(), { minimumFractionDigits: d, maximumFractionDigits: d });
const big = (x) => (x >= 1e6 ? `${dec(x / 1e6)} M` : x >= 1e4 ? `${Math.round(x / 1e3)} k` : n(x));
const hours = (s) => (s >= 3600 ? `${dec(s / 3600)} h` : `${Math.round((s || 0) / 60)} min`);
const share = (a, b) => (b ? `${Math.round((100 * a) / b)}%` : "–");
const who = (u) => (u === "" ? t("usage.aurora") : u);

function tile(icon, label, value, sub) {
  const b = el("div", "usage-tile");
  b.append(el("div", "usage-label", `${icon} ${label}`), el("div", "usage-value", value), el("div", "usage-sub muted", sub || ""));
  return b;
}

// one measure per day, one series: bars from the baseline, a tooltip per bar (the day and the number)
function bars(title, days, key, fmt = n) {
  const W = 320, H = 120, L = 4, R = 4, T = 8, B = 18;
  const top = Math.max(0, ...days.map((d) => d[key] || 0)), max = top || 1;
  const step = (W - L - R) / days.length, w = Math.max(2, step - 2);
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "usage-chart", role: "img", "aria-label": title });
  g.append(svg("line", { x1: L, x2: W - R, y1: H - B, y2: H - B, class: "usage-base" }));
  days.forEach((d, i) => {
    const v = d[key] || 0, h = ((H - T - B) * v) / max, x = L + i * step + (step - w) / 2;
    const hit = svg("rect", { x: L + i * step, y: T, width: step, height: H - T - B, class: "usage-hit" });
    const r = svg("rect", { x, y: H - B - h, width: w, height: h, rx: Math.min(2, w / 2), class: "usage-bar" });
    const tip = svg("title");
    tip.textContent = `${d.day.slice(6, 8)}/${d.day.slice(4, 6)} · ${fmt(v)}`;
    hit.append(tip);
    g.append(r, hit);
  });
  for (const i of [0, days.length - 1]) {
    if (days.length < 2 && i) continue;
    const tx = svg("text", { x: L + i * step + step / 2, y: H - 4, class: "usage-axis", "text-anchor": i ? "end" : "start" });
    tx.textContent = `${days[i].day.slice(6, 8)}/${days[i].day.slice(4, 6)}`;
    g.append(tx);
  }
  const box = el("div", "usage-chartbox");
  box.append(el("div", "usage-label", `${title} · max ${fmt(top)}`), g);
  return box;
}

function table(cols, rows) {
  const tb = el("table", "table usage-table");
  const head = el("tr");
  cols.forEach(([k, num]) => head.append(el("th", num ? "num" : "", t(k))));
  tb.append(head);
  for (const r of rows) {
    const tr = el("tr");
    r.forEach((c, i) => tr.append(el("td", cols[i][1] ? "num" : "", c)));
    tb.append(tr);
  }
  return rows.length ? tb : el("p", "muted", t("usage.none"));
}

export default {
  id: "usage",
  icon: "📈",
  title: "nav.usage",

  mount(root) {
    useCss("/static/css/usage.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="usage.title"></h2><p class="muted" data-i18n="usage.lead"></p>
      <div class="usage-bar-top"><div class="usage-periods"></div><select class="usage-who"></select></div>
      <div class="usage-body"></div>`;
    apply(root);
    this.days = 7;
    this.user = null;
    this.periods = root.querySelector(".usage-periods");
    this.who = root.querySelector(".usage-who");
    this.body = root.querySelector(".usage-body");
    for (const p of PERIODS) {
      const b = el("button", "", t(p === 1 ? "usage.today" : "usage.days", { n: p }));
      b.dataset.days = p;
      b.addEventListener("click", () => { this.days = p; this.enter(); });
      this.periods.append(b);
    }
    this.who.addEventListener("change", () => { this.user = this.who.value === "*" ? null : this.who.value; this.enter(); });
  },

  async enter() {
    for (const b of this.periods.children) b.classList.toggle("on", Number(b.dataset.days) === this.days);
    const q = `/v1/aurora/usage?days=${this.days}${this.user !== null ? `&user=${encodeURIComponent(this.user)}` : ""}`;
    const r = await call(q);
    this.who.hidden = !r.everyone;
    if (r.everyone) {
      this.who.replaceChildren(el("option", "", t("usage.everyone")), ...r.names.map((u) => el("option", "", who(u))));
      this.who.firstChild.value = "*";
      r.names.forEach((u, i) => { this.who.children[i + 1].value = u; });
      this.who.value = this.user === null ? "*" : this.user;
    }
    const s = r.totals;
    const tiles = el("div", "usage-tiles");
    tiles.append(
      tile("💬", t("usage.questions"), n(s.questions), s.questions ? t("usage.avg", { s: dec(s.question_s / s.questions) }) : ""),
      tile("🤖", t("usage.agent"), n(s.agent_runs), t("usage.steps", { n: n(s.agent_steps) })),
      tile("☁️", t("usage.cloud"), n(s.cloud_calls), t("usage.tokens", { n: big(s.cloud_tokens) })),
      tile("🖥️", t("usage.local"), n(s.local_calls), t("usage.gpu", { h: hours(s.local_s) })),
      tile("🧰", t("usage.tools"), n(s.tool_calls), t("usage.failed", { p: share(s.tool_failed, s.tool_calls) })),
      tile("↩️", t("usage.fallbacks"), n(s.fallbacks), t("usage.approvals", { n: n(s.approvals) })),
    );
    const parts = [tiles];
    if (r.days.length > 1) {
      const charts = el("div", "usage-charts");
      charts.append(bars(t("usage.questions"), r.days, "questions"), bars(t("usage.cloud"), r.days, "cloud_calls"),
        bars(t("usage.cloud_tokens"), r.days, "cloud_tokens", big), bars(t("usage.tools"), r.days, "tool_calls"));
      parts.push(charts);
    }
    if (r.everyone && this.user === null) {
      parts.push(el("h3", "setting-cat", t("usage.by_user")), table(
        [["usage.user"], ["usage.questions", 1], ["usage.agent", 1], ["usage.cloud", 1], ["usage.cloud_tokens", 1], ["usage.local", 1], ["usage.tools", 1]],
        r.users.map((u) => [who(u.user), n(u.questions), n(u.agent_runs), n(u.cloud_calls), big(u.cloud_tokens), n(u.local_calls), n(u.tool_calls)])));
    }
    parts.push(el("h3", "setting-cat", t("usage.models_cloud")), table(
      [["usage.model"], ["usage.calls", 1], ["usage.cloud_tokens", 1], ["usage.per_call", 1]],
      r.cloud.map((m) => [m.name, n(m.calls), big(m.tokens), big(m.calls ? m.tokens / m.calls : 0)])));
    parts.push(el("h3", "setting-cat", t("usage.models_local")), table(
      [["usage.role"], ["usage.calls", 1], ["usage.tokens_out", 1], ["usage.time", 1]],
      r.local.map((m) => [m.name, n(m.calls), big(m.tokens), hours(m.s)])));
    parts.push(el("h3", "setting-cat", t("usage.tools_title")), table(
      [["usage.tool"], ["usage.calls", 1], ["usage.failed_col", 1], ["usage.avg_s", 1]],
      r.tools.slice(0, 40).map((m) => [m.name, n(m.calls), share(m.failed, m.calls), dec(m.calls ? m.s / m.calls : 0)])));
    if (r.fallback.length) parts.push(el("h3", "setting-cat", t("usage.fallbacks")), table(
      [["usage.provider"], ["usage.calls", 1]], r.fallback.map((m) => [m.name, n(m.calls)])));
    parts.push(el("p", "muted", t("usage.privacy")));
    this.body.replaceChildren(...parts);
  },
};

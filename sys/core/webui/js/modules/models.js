// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Models: which model does each step of Aurora (local, Claude, Gemini, Grok...), what each step sends out, masking,
// and what the cloud cost and saved (calls, tokens, cost, masked items, SSCC), measured from the traces.
import { call } from "../api.js";
import { el, info } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { renderModes } from "./models_mode.js";

export default {
  id: "models",
  icon: "🧠",
  title: "nav.models",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="md.title"></h2><p class="muted" data-i18n="md.hint"></p>
      <div class="md-mode"></div>
      <div class="md-state"></div>
      <h3 class="setting-cat" data-i18n="md.roles"></h3><div class="md-roles"></div>
      <div><button class="md-save" data-i18n="md.save"></button> <span class="muted md-out"></span></div>
      <h3 class="setting-cat" data-i18n="md.media"></h3><p class="muted" data-i18n="md.media_hint"></p><div class="md-media"></div>
      <h3 class="setting-cat" data-i18n="md.limits"></h3><p class="muted" data-i18n="md.limits_hint"></p><div class="md-limits"></div>
      <h3 class="setting-cat" data-i18n="md.stats"></h3>
      <div class="ev"><select class="md-days"><option value="1">24 h</option><option value="7" selected>7 gg</option><option value="30">30 gg</option></select></div>
      <div class="md-stats"></div>`;
    apply(root);
    this.state = root.querySelector(".md-state");
    this.modeBox = root.querySelector(".md-mode");
    this.roles = root.querySelector(".md-roles");
    this.stats = root.querySelector(".md-stats");
    this.out = root.querySelector(".md-out");
    root.querySelector(".md-days").addEventListener("change", (e) => this.loadStats(e.target.value));
    root.querySelector(".md-save").addEventListener("click", async () => {
      const changes = {};
      for (const row of this.roles.querySelectorAll(".md-role")) {
        changes[row.dataset.role] = { provider: row.querySelector("select:not(.md-pick)").value, model: row.querySelector("input").value.trim() };
      }
      try { await call("/v1/aurora/models/roles", { method: "PUT", body: JSON.stringify(changes) }); this.out.textContent = t("md.saved"); }
      catch (e) { this.out.textContent = t("ev.error", { m: e.message }); }
    });
  },

  async enter() {
    const m = await call("/v1/aurora/models");
    const box = this.state;
    box.replaceChildren();
    const line = (cls, text) => box.append(el("p", cls, text));
    line(m.exempt ? "muted" : "error", t(m.exempt ? "md.exempt_on" : "md.exempt_off"));
    line(m.mask ? "muted" : "error", t(m.mask ? "md.mask_on" : "md.mask_off"));
    line("muted", t("md.pictures"));
    this.providers = m.providers;
    renderModes(this.modeBox, m.providers, () => this.enter());      // 🧭 the whole: local, mixed, cloud, all cloud
    this.roles.replaceChildren(...m.roles.map((r) => this.row(r)));
    this.loadMedia();
    this.loadLimits();
    this.loadStats(7);
  },

  // 🆓 each provider's free tier (owner, 2026-10-06): a tick to stay in it, its numbers, today's use; past them the
  // local model does the step until the minute or the day turns (mdl_budget)
  async loadLimits() {
    const box = document.querySelector(".md-limits");
    let m;
    try { m = await call("/v1/aurora/models/limits"); } catch (e) { box.replaceChildren(el("p", "muted", t("ev.error", { m: e.message }))); return; }
    const table = el("table", "sec-rules-table md-limits-table");
    const head = el("tr");
    for (const h of ["", "provider", "per_minute", "per_day", "tokens_per_day", "today"]) head.append(el("th", "", h ? t(`md.lim.${h}`) : "🆓"));
    table.append(head);
    const label = Object.fromEntries((this.providers || []).map((p) => [p.id, p.label]));
    for (const [p, lim] of Object.entries(m.limits)) {
      if (!m.configured[p]) continue;                   // only the providers with a key
      const tr = el("tr");
      const free = el("input"); free.type = "checkbox"; free.checked = lim.free; free.dataset.p = p; free.dataset.k = "free";
      const c0 = el("td"); c0.append(free);
      tr.append(c0, el("td", "", label[p] || p));
      for (const k of ["per_minute", "per_day", "tokens_per_day"]) {
        const i = el("input"); i.type = "number"; i.min = 0; i.value = lim[k]; i.dataset.p = p; i.dataset.k = k; i.title = t("md.lim.zero");
        const td = el("td"); td.append(i); tr.append(td);
      }
      const d = m.today[p];
      tr.append(el("td", d.stopped ? "warn" : "muted", `${d.calls} · ${d.tokens}${d.stopped ? ` · ⏸️ ${d.stopped}` : ""}`));
      table.append(tr);
    }
    const out = el("span", "muted");
    const save = el("button", "", t("md.save"));
    save.addEventListener("click", async () => {
      const changes = {};
      box.querySelectorAll("[data-p]").forEach((i) => { (changes[i.dataset.p] ??= {})[i.dataset.k] = i.type === "checkbox" ? i.checked : Number(i.value); });
      try { await call("/v1/aurora/models/limits", { method: "PUT", body: JSON.stringify(changes) }); out.textContent = t("md.saved"); this.loadLimits(); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
    const bar = el("div");
    bar.append(save, out);
    box.replaceChildren(table.rows.length > 1 ? table : el("p", "muted", t("md.lim.none")), bar);
    // 🆓 beside each step given to a provider kept in its free tier
    const free = new Set(Object.entries(m.limits).filter(([, l]) => l.free).map(([p]) => p));
    document.querySelectorAll(".md-role").forEach((row) => {
      row.querySelector(".md-free")?.remove();
      const p = row.querySelector("select:not(.md-pick)")?.value;
      if (free.has(p)) { const b = el("span", "md-free", "🆓"); b.title = t("md.lim.badge"); row.append(b); }
    });
  },

  // 🎨 pictures, edits, videos (owner, 2026-10-06): the local models or a provider that really does that task
  async loadMedia() {
    const box = this.root?.querySelector(".md-media") || document.querySelector(".md-media");
    let m;
    try { m = await call("/v1/aurora/models/media"); } catch (e) { box.replaceChildren(el("p", "muted", t("ev.error", { m: e.message }))); return; }
    const out = el("span", "muted");
    const rows = Object.entries(m.choices).map(([task, opts]) => {
      const row = el("div", "ev");
      const sel = el("select");
      sel.dataset.task = task;
      for (const o of opts) {
        const op = el("option", "", o.provider === "local" ? t(`md.media_local.${task}`) : `${o.label} · ${o.model}${o.ready ? "" : ` — ${t("md.no_key")}`}`);
        op.value = o.provider;
        op.disabled = !o.ready && o.provider !== m.assigned[task].provider;
        op.selected = o.provider === m.assigned[task].provider;
        sel.append(op);
      }
      row.append(el("strong", "", t(`md.media.${task}`)), sel);
      if (task !== "image" && !m.exempt) row.append(el("span", "muted", t("md.media_photo")));
      return row;
    });
    const save = el("button", "", t("md.save"));
    save.addEventListener("click", async () => {
      const changes = Object.fromEntries([...box.querySelectorAll("select")].map((s) => [s.dataset.task, { provider: s.value }]));
      try { await call("/v1/aurora/models/media", { method: "PUT", body: JSON.stringify(changes) }); out.textContent = t("md.saved"); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
    const bar = el("div");
    bar.append(save, out);
    box.replaceChildren(...rows, bar);
  },

  row(r) {
    const row = el("div", "ev md-role");
    row.dataset.role = r.id;
    const sel = el("select");
    for (const p of this.providers) {
      const o = el("option", "", p.configured ? p.label : `${p.label} — ${t("md.no_key")}`);
      o.value = p.id;
      o.disabled = !p.configured && p.id !== r.provider;
      o.selected = p.id === r.provider;
      sel.append(o);
    }
    // the provider's models in a real menu (a datalist hid them on phones and filtered them by what was typed);
    // "other" opens the box for a name not in the list. The box stays what is saved.
    const pick = el("select", "md-pick");
    const model = el("input");
    model.value = r.model || "";
    model.placeholder = t("md.model_ph");
    const warn = el("span", "md-warn", "📷");
    warn.title = t("md.pictures");
    const option = (value, text) => { const o = el("option", "", text); o.value = value; return o; };
    const fill = async () => {
      pick.replaceChildren();
      if (sel.value === "local") { model.value = ""; model.hidden = true; pick.hidden = true; return; }
      pick.hidden = false;
      let models = [];
      try { ({ models } = await call(`/v1/aurora/models/${sel.value}/list`)); }
      catch (e) { model.placeholder = t("ev.error", { m: e.message }); }
      pick.append(option("", t("md.model_default")), ...models.map((n) => option(n, n)), option("\u0000", t("md.model_other")));
      const known = !model.value || models.includes(model.value);
      pick.value = known ? model.value : "\u0000";
      model.hidden = known;
    };
    pick.addEventListener("change", () => {
      const other = pick.value === "\u0000";
      model.hidden = !other;
      model.value = other ? "" : pick.value;
      if (other) model.focus();
    });
    sel.addEventListener("change", () => { model.value = ""; fill(); warn.hidden = !(r.id === "vision" && sel.value !== "local"); });
    model.hidden = r.provider === "local";
    pick.hidden = r.provider === "local";
    if (r.provider !== "local") fill();
    warn.hidden = !(r.id === "vision" && r.provider !== "local");
    const name = el("div", "md-name");
    name.append(el("strong", "", lang.startsWith("it") ? r.it : r.en), info(t("md.sees", { what: r.sees })));
    row.append(name, sel, pick, model, warn);
    return row;
  },

  async loadStats(days) {
    const s = await call(`/v1/aurora/models/stats?days=${days}`);
    const box = this.stats;
    box.replaceChildren();
    const calls = Object.entries(s.calls);
    if (!calls.length) box.append(el("p", "muted", t("md.no_calls")));
    for (const [k, v] of calls) {
      const r = el("div", "ev");
      r.append(el("strong", "", k), el("span", "", t("md.calls", { n: v.calls })),
        el("span", "muted", t("md.tokens", { i: v.in.toLocaleString(), o: v.out.toLocaleString(), c: v.cached.toLocaleString() })),
        el("span", "", `💶 ${v.cost_usd.toFixed(2)} $`), el("span", "muted", `${Math.round(v.seconds)} s`));
      box.append(r);
    }
    const masked = Object.entries(s.masked).map(([k, n]) => `${k} ${n}`).join(", ");
    box.append(el("p", "", t("md.masked", { what: masked || t("md.nothing") })));
    box.append(el("p", s.pictures_sent ? "error" : "muted", t("md.pictures_sent", { n: s.pictures_sent })));
    const fb = Object.entries(s.fallbacks).map(([k, n]) => `${k} ${n}`).join(", ");
    if (fb) box.append(el("p", "error", t("md.fallbacks", { what: fb })));
    const spent = s.today?.tokens || {};
    for (const [prov, n] of Object.entries(spent)) {      // today's tokens against the daily ceiling
      const paid = s.paid?.includes(prov) && s.daily_cap > 0;
      const stopped = (s.today.stopped || []).includes(prov);
      box.append(el("p", stopped ? "error" : "muted", paid
        ? t(stopped ? "md.budget_stop" : "md.budget", { p: prov, n: n.toLocaleString(), cap: s.daily_cap.toLocaleString() })
        : t("md.budget_free", { p: prov, n: n.toLocaleString() })));
    }
    const sc = s.sscc;
    box.append(el("p", "", sc.calls ? t("md.sscc_live", { n: sc.calls, pct: sc.saved_pct, i: sc.chars_in, o: sc.chars_out }) : t("md.sscc_none")));
    if (s.sscc_reference) {
      const r = s.sscc_reference;
      box.append(el("p", "muted", t("md.sscc_ref", { full: r.tokens_full.toLocaleString(), sscc: r.tokens_sscc.toLocaleString(),
        pct: Math.round(100 * (1 - r.tokens_sscc / r.tokens_full)), sf: r.score?.full, ss: r.score?.sscc })));
    }
  },
};

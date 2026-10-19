// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → 🌌 Tonight (ROADMAP N30): the night (astronomical dark, the Moon, the forecast) and the whole catalogue
// ranked by the hours each object can be taken with the person's equipment (ast_skyplan); a row opens that object's
// night hour by hour. The catalogue is fetched by the server on the first ask (a few seconds, once).
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { datePicker, fmtDate } from "../dates.js";

const KINDS = ["", "narrowband", "broadband", "hdr", "galaxy"];
const COLS = ["n", "pic", "name", "type", "size", "hours", "max", "moon", "fit", "set"];
const thumbUrl = (name) => `/v1/aurora/astro/sky/thumb?object=${encodeURIComponent(name)}`;
const pct = (x) => `${Math.round(x * 100)}%`;

function controls(box, run) {
  const row = el("div", "sky-controls");
  const date = datePicker("", () => again());
  const kind = el("select", "sky-kind");
  KINDS.forEach((k) => { const o = el("option", "", t(`sky.kind.${k || "all"}`)); o.value = k; kind.append(o); });
  const alt = el("input");
  alt.type = "number"; alt.min = "0"; alt.max = "80"; alt.value = "30"; alt.title = t("sky.min_alt");
  const go = el("button", "btn", `🔄 ${t("sky.again")}`);
  go.type = "button";
  const again = () => run({ date: date.value, kind: kind.value, min_alt: alt.value });
  let wait;
  go.addEventListener("click", again);
  kind.addEventListener("change", again);
  alt.addEventListener("input", () => { clearTimeout(wait); wait = setTimeout(again, 600); });
  row.append(el("label", "", t("sky.date")), date.el, el("label", "", t("sky.kind")), kind,
    el("label", "", t("sky.min_alt")), alt, go);
  box.append(row, el("p", "muted sky-how", `👆 ${t("sky.how")}`));
}

function nightCard(d) {
  const n = d.night;
  const card = el("div", "sky-night");
  const lines = [`📍 ${d.site.lat}, ${d.site.lon} (${d.site.from}) · ${fmtDate(d.date)}`];
  if (!n.dusk) lines.push(t("sky.never_dark"));
  else {
    lines.push(`🌑 ${t("sky.dark", { from: n.dusk, to: n.dawn, h: n.dark_h })}`);
    lines.push(`🌙 ${t("sky.moon", { lit: pct(n.moon_lit), h: n.moon_up_dark_h })}`);
    if (n.cloud_mean != null) lines.push(`☁️ ${t("sky.clouds", { c: n.cloud_mean, h: n.clear_dark_h })}`);
    if (n.seeing.length) lines.push(`👁️ ${n.seeing.map((s) => `${s.at} ${s.seeing} · T${s.transparency}`).join(" · ")}`);
    if (n.forecast_errors.length) lines.push(`⚠️ ${n.forecast_errors.join(", ")}`);
  }
  if (d.field) lines.push(`🖼️ ${t("sky.field", { w: d.field.w_deg, h: d.field.h_deg, s: d.field.scale })}`);
  lines.forEach((x) => card.append(el("div", "", x)));
  if (d.clouds_ignored) card.append(el("div", "warn", `⚠️ ${t("sky.clouds_ignored")}`));
  if (d.families) {
    const said = Object.entries(d.families).filter(([, v]) => v.usable || v.if_clear)
      .map(([f, v]) => `${t(`sky.fam.${f}`)} ${v.usable}${v.if_clear ? ` (+${v.if_clear} ☁️)` : ""}`);
    card.append(el("div", "", `🗂️ ${t("sky.families")}: ${said.join(" · ")}`));
  }
  return card;
}

// the sequence's base values, the measured ones first, each changeable before it goes to N.I.N.A. (owner, 19 Oct: «la
// possibilità di modificare parametri base, come il numero di scatti»): written again with them
function seqParams(p, write) {
  const form = el("form", "sky-seq-params");
  if (!p) return form;
  const fields = [["count", 1, 2000, 1], ["exposure_s", 0.001, 3600, "any"], ["gain", 0, 10000, 1], ["offset", 0, 10000, 1]];
  const inputs = {};
  for (const [key, min, max, step] of fields) {
    const lab = el("label", "", t(`sky.seq_${key}`));
    const inp = el("input");
    Object.assign(inp, { type: "number", min, max, step, value: p[key], required: true });
    inputs[key] = inp;
    lab.append(inp);
    form.append(lab);
  }
  const again = el("button", "btn", `✍️ ${t("sky.seq_rewrite")}`);
  again.type = "submit";
  form.append(again);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    write(Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, Number(v.value)])));
  });
  return form;
}

// the written sequence: downloaded, or loaded into N.I.N.A. through its Advanced API (owner, 19 Oct: «non c'è modo di
// scaricarla ed inviarla a nina»)
// …or for another program (owner, 19 Oct: «rendere compatibile… con altri software di pianificazione»): Ekos, CCDciel,
// a target list (N.I.N.A., SGP, APT); the Ekos folder kept in this browser
const EKOS_DIR = "aurora.astro.ekos_dir";
function seqActions(file) {
  const fmt = el("select", "sky-seq-fmt");
  fmt.setAttribute("aria-label", t("sky.seq_format"));
  for (const f of ["nina", "ekos", "ccdciel", "csv"]) { const o = el("option", "", t(`sky.fmt.${f}`)); o.value = f; fmt.append(o); }
  const dir = el("input", "sky-seq-dir");
  dir.placeholder = t("sky.seq_ekos_dir");
  dir.setAttribute("aria-label", t("sky.seq_ekos_dir"));
  try { dir.value = localStorage.getItem(EKOS_DIR) || ""; } catch { /* this visit only */ }
  const down = el("a", "btn", `⬇️ ${t("sky.seq_download")}`);
  const hint = el("small", "muted");
  const link = () => {
    const q = new URLSearchParams({ name: file, format: fmt.value });
    if (fmt.value === "ekos" && dir.value.trim()) q.set("folder", dir.value.trim());
    down.href = `/v1/aurora/astro/sky/sequence/file?${q}`;
    down.download = "";
    dir.hidden = fmt.value !== "ekos";
    hint.textContent = t(`sky.fmt_note.${fmt.value}`);
  };
  fmt.addEventListener("change", link);
  dir.addEventListener("input", () => { try { localStorage.setItem(EKOS_DIR, dir.value.trim()); } catch { /* this visit only */ } link(); });
  link();
  const send = el("button", "btn", `📤 ${t("sky.seq_send")}`);
  const out = el("span", "muted");
  send.addEventListener("click", async () => {
    send.disabled = true;
    out.textContent = "⏳";
    try {
      const r = await call("/v1/aurora/astro/sky/sequence/send", { method: "POST", body: JSON.stringify({ file }) });
      out.textContent = r.error ? `⚠️ ${r.error}` : `✅ ${r.said}`;
    } catch (e) { out.textContent = e.message; }
    send.disabled = false;
  });
  return [fmt, dir, down, send, out, hint];
}

function hourly(d) {
  // the object's altitude through the night: one bar an hour, dark hours solid, the usable ones marked
  const wrap = el("div", "sky-hours");
  for (const h of d.hourly || []) {
    const bar = el("div", `sky-hour${h.usable ? " ok" : ""}${h.dark ? "" : " twilight"}`);
    bar.title = `${h.at} · ${h.alt}°` + (h.cloud != null ? ` · ☁️ ${h.cloud}%` : "") + ` · 🌙 ${h.moon_alt}°`;
    const fill = el("i");
    fill.style.height = `${Math.max(0, h.alt) / 90 * 100}%`;
    bar.append(fill, el("small", "", h.at.slice(0, 2)));
    wrap.append(bar);
  }
  return wrap;
}

function table(d, open) {
  const tb = el("table", "an-table sky-table");
  const head = el("tr");
  for (const k of COLS) head.append(el("th", "", t(`sky.col.${k}`)));
  tb.append(head);
  d.targets.forEach((r, i) => {
    const tr = el("tr", `sky-row${r.if_clear ? " muted" : ""}`);
    const names = [...r.common, ...r.aliases].join(", ");
    const cells = [String(i + 1), "", `${r.name}${names ? ` · ${names}` : ""}`, `${r.type} · ${t(`sky.kind.${r.kind}`)}`,
      r.size_arcmin[0] ? `${r.size_arcmin[0]}′` : "—", `${r.if_clear ? "☁️ " : ""}${r.hours} h${r.from ? ` · ${r.from}–${r.to}` : ""}${r.if_clear ? ` · ${t("sky.if_clear")}` : ""}`,
      `${r.max_alt}° · ${r.max_at}`, `${r.moon_sep}°`, r.fit.words, r.set || "—"];
    cells.forEach((c, k) => { const td = el("td", "", c); td.dataset.label = t(`sky.col.${COLS[k]}`); tr.append(td); });
    const picCell = tr.children[1];
    picCell.className = "sky-pic";
    const mini = () => { const im = el("img", "sky-mini"); im.loading = "lazy"; im.alt = ""; im.src = thumbUrl(r.name); picCell.replaceChildren(im); };
    if (r.thumb) mini();                                     // opened before: its picture is kept
    else picCell.textContent = "📷";
    tr.addEventListener("click", () => { if (!r.thumb) { r.thumb = true; setTimeout(mini, 2500); } });
    tr.title = t("sky.open");
    tr.addEventListener("click", () => open(r.name, tr));
    tb.append(tr);
  });
  const wrap = el("div", "an-wrap");
  wrap.append(tb);
  return wrap;
}

export async function skyTab(box) {
  if (box.dataset.ready) return;
  box.dataset.ready = "1";
  box.replaceChildren(el("p", "muted", t("sky.hint")));
  const out = el("div", "sky-out");
  const one = el("div", "sky-one");
  let last = {};
  // the object's night opens right under its row (a phone's list is long: at the bottom it was never seen)
  const open = async (name, row) => {
    const at = el("tr", "sky-detail");
    const cell = el("td");
    cell.colSpan = COLS.length;
    cell.append(one);
    at.append(cell);
    row.parentNode.querySelectorAll(".sky-detail").forEach((x) => x.remove());
    row.after(at);
    one.replaceChildren(el("p", "muted", `⏳ ${name}`));
    try {
      const q = new URLSearchParams({ ...last, object: name, limit: 1 });
      const d = await call(`/v1/aurora/astro/sky?${q}`);
      if (d.error) { one.replaceChildren(el("p", "warn", d.error)); return; }
      const r = d.targets[0];
      const pic = el("img", "sky-thumb");
      pic.alt = r.name;
      pic.loading = "lazy";
      pic.src = thumbUrl(name);
      pic.addEventListener("error", () => pic.replaceWith(el("p", "muted", t("sky.no_thumb"))));
      const plan = el("button", "primary", `🗓️ ${t("sky.plan")}`);
      const said = el("pre", "col-text");
      const write = async (own = {}) => {
        plan.disabled = true;
        said.textContent = `⏳ ${t("sky.planning")}`;
        try {
          const s = await call("/v1/aurora/astro/sky/sequence", { method: "POST", body: JSON.stringify({ object: name, date: last.date || "", kind: last.kind && last.kind !== "galaxy" ? last.kind : "", ...own }) });
          said.textContent = s.error ? `⚠️ ${s.error}` : s.text;
          if (s.file) acts.replaceChildren(seqParams(s.params, write), ...seqActions(s.file));
        } catch (e) { said.textContent = e.message; }
        plan.disabled = false;
      };
      plan.addEventListener("click", () => write());
      const acts = el("div", "sky-seq-acts");
      const side = el("div", "sky-one-side");
      side.append(el("h4", "", `🎯 ${r.name} · ${r.if_clear ? "☁️ " : ""}${r.hours} h · ${r.fit.words}`), hourly(d), plan, acts, said);
      const box2 = el("div", "sky-one-box");
      box2.append(pic, side);
      one.replaceChildren(box2, el("p", "muted", t("sky.thumb_note")));
      at.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) { one.replaceChildren(el("p", "warn", e.message)); }
  };
  const run = async (p = {}) => {
    last = Object.fromEntries(Object.entries(p).filter(([, v]) => v !== "" && v != null));
    out.replaceChildren(el("p", "muted", `⏳ ${t("sky.wait")}`));
    one.replaceChildren();
    let d;
    try { d = await call(`/v1/aurora/astro/sky?${new URLSearchParams(last)}`); } catch (e) { out.replaceChildren(el("p", "warn", e.message)); return; }
    if (d.error && !d.night) { out.replaceChildren(el("p", "warn", d.error)); return; }
    out.replaceChildren(nightCard(d));
    if (d.targets?.length) out.append(table(d, open), el("p", "muted", t("sky.count", { n: d.candidates, of: d.catalogue })));
    else if (d.night.dusk) out.append(el("p", "muted", t("sky.none")));
  };
  controls(box, (p) => run(p));
  box.append(out, one);
  run();
}

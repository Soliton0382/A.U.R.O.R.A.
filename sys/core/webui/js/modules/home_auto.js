// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🪄 Automations on the 🏠 pages (hom_auto): any device — lights, plugs, a camera's switches, buttons — at a time, at
// sunrise or sunset with an offset, on chosen days, or by hand like a scene (owner, 2026-10-20: «una sezione apposita
// di scene/automatismi che prenda in considerazione di gestire tutti i device»). A guided editor: name, when, what.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { t } from "../i18n.js";

const DAYS = [0, 1, 2, 3, 4, 5, 6];                       // Monday first, as hom_auto (Python's weekday)

const svc = (s) => { const k = `hauto.svc.${s}`, v = t(k); return v === k ? s : v; };

function when(w, today) {
  const days = w.days?.length && w.days.length < 7 ? ` · ${w.days.map((d) => t(`hauto.day.${d}`)).join(" ")}` : "";
  if (w.type === "manual") return t("hauto.when.manual");
  if (w.type === "time") return t("hauto.when.time_at", { at: w.at }) + days;
  const off = w.offset_min ? ` ${w.offset_min > 0 ? "+" : "−"}${Math.abs(w.offset_min)} min` : "";
  return `${t(`hauto.when.${w.type}`)}${off}${today ? ` (${t("hauto.today", { at: today })})` : ""}${days}`;
}

export async function automationsBlock(devices, allowed, reload) {
  let r, scenes = {};
  try { r = await call("/v1/aurora/home/automations"); } catch { return null; }
  try { scenes = (await call("/v1/aurora/home/scenes")).scenes; } catch { /* no light scene to offer */ }
  // what an action may touch: every entity the page can command, with its device's name
  const targets = [];
  for (const d of devices) for (const e of d.entities) if (allowed[e.domain]) targets.push({ ...e, device: d.name });
  const block = el("section", "home-group");
  const add = el("button", "", t("hauto.new"));
  const head = el("div", "home-head");
  head.append(el("h3", "setting-cat home-kind", `${t("hauto.title")} · ${r.automations.length}`), add);
  const box = el("div", "scene-editor");
  box.hidden = true;
  const card = el("section", "home-card");
  if (!r.automations.length) card.append(el("p", "muted", t("hauto.none")));
  const sun = r.sun?.sunrise ? el("p", "muted", t("hauto.sun", r.sun)) : null;
  for (const a of r.automations) card.append(row(a, reload, () => open(a)));
  const open = (a) => {
    box.replaceChildren(editor(a, targets, scenes, allowed, () => { box.hidden = true; }, reload));
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  add.addEventListener("click", () => open(null));
  block.append(...[head, el("p", "muted", t("hauto.hint")), sun, box, card].filter(Boolean));
  return block;
}

function row(a, reload, edit) {
  const line = el("div", "home-entity auto-row");
  const text = el("div", "auto-text");
  text.append(el("span", "home-name", `${a.enabled ? "🟢" : "⏸️"} ${a.name}`),
    el("span", "home-state", `${when(a.when, a.today)} · ${t("hauto.n_actions", { n: a.actions.length })}`));
  if (a.last) text.append(el("span", "muted", `${a.last_ok ? "✅" : "⚠️"} ${clock(new Date(a.last * 1000).toISOString())} · ${a.last_text || ""}`));
  const act = async (what, b) => {
    b.disabled = true;
    try { await call(`/v1/aurora/home/automations/${a.id}/${what}`, { method: "POST" }); }
    catch (e) { b.textContent = t("ev.error", { m: e.message }); }
    setTimeout(reload, 600);
  };
  const go = el("button", "", "▶");
  go.title = t("hauto.run");
  go.addEventListener("click", () => act("run", go));
  const sw = el("button", "", a.enabled ? "⏸️" : "🟢");
  sw.title = t(a.enabled ? "hauto.off" : "hauto.on");
  sw.addEventListener("click", () => act(a.enabled ? "off" : "on", sw));
  const ed = el("button", "", "✏️");
  ed.title = t("scene.edit");
  ed.addEventListener("click", edit);
  const del = el("button", "danger", "🗑️");
  del.title = t("up.delete");
  del.addEventListener("click", () => { if (confirm(t("hauto.delete_q", { name: a.name }))) act("delete", del); });
  const btns = el("div", "auto-btns");
  btns.append(go, sw, ed, del);
  line.append(text, btns);
  return line;
}

function editor(a, targets, scenes, allowed, close, reload) {
  const f = el("div", "home-card scene-form");
  const name = el("input");
  name.value = a?.name || "";
  name.placeholder = t("hauto.name_hint");
  // when
  const type = el("select");
  for (const k of ["manual", "time", "sunset", "sunrise"]) type.append(new Option(t(`hauto.when.${k}`), k));
  type.value = a?.when?.type || "time";
  const at = el("input");
  at.type = "time";
  at.value = a?.when?.at || "19:00";
  const off = el("input");
  off.type = "number";
  off.min = -240;
  off.max = 240;
  off.step = 5;
  off.value = a?.when?.offset_min || 0;
  const days = el("div", "auto-days");
  const picked = new Set(a?.when?.days || DAYS);
  for (const d of DAYS) {
    const b = el("button", picked.has(d) ? "on" : "", t(`hauto.day.${d}`));
    b.type = "button";
    b.addEventListener("click", () => { picked.has(d) ? picked.delete(d) : picked.add(d); b.classList.toggle("on", picked.has(d)); });
    days.append(b);
  }
  const atL = el("label", "", t("hauto.at")), offL = el("label", "", t("hauto.offset"));
  atL.append(at);
  offL.append(off);
  const showWhen = () => {
    atL.hidden = type.value !== "time";
    offL.hidden = !["sunset", "sunrise"].includes(type.value);
    days.hidden = type.value === "manual";
  };
  type.addEventListener("change", showWhen);
  showWhen();
  // what: the actions, each a target and what to do with it
  const list = el("div", "auto-actions");
  const addAction = (x = {}) => {
    const line = el("div", "auto-action");
    const what = el("select"), how = el("select");
    what.append(new Option(t("hauto.pick"), ""));
    for (const s of Object.keys(scenes || {})) what.append(new Option(`🎨 ${t("hauto.scene")}: ${scenes[s].name}`, `scene:${s}`));
    for (const e of targets) what.append(new Option(`${e.device} — ${e.name || e.entity_id}`, e.entity_id));
    what.value = x.scene ? `scene:${x.scene}` : x.entity_id || "";
    const pct = el("input");
    pct.type = "number";
    pct.min = 1;
    pct.max = 100;
    pct.placeholder = "%";
    pct.title = t("scene.brightness");
    pct.value = x.data?.brightness_pct ?? "";
    const kelvin = el("input");                           // a white's warmth: 2700 warm … 6500 cold
    kelvin.type = "number";
    kelvin.min = 2000;
    kelvin.max = 6500;
    kelvin.step = 50;
    kelvin.placeholder = "K";
    kelvin.title = t("hauto.kelvin");
    kelvin.value = x.data?.color_temp_kelvin ?? "";
    const lightOn = () => what.value.startsWith("light.") && how.value === "turn_on";
    const fill = () => {
      how.replaceChildren();
      const v = what.value, domain = v.split(".")[0];
      if (v.startsWith("scene:")) how.append(new Option(t("hauto.start_scene"), "start"), new Option(t("hauto.stop_scene"), "stop"));
      else for (const s of allowed[domain] || []) how.append(new Option(svc(s), s));
      // a light: any scene on it alone, beside switching it (owner, 2026-10-20: «di fianco al device, si possa
      // applicare la possibile scena»)
      if (domain === "light") for (const [k, sc] of Object.entries(scenes || {})) how.append(new Option(`🎨 ${sc.name}`, `scene:${k}`));
      const was = x.scene ? (x.stop ? "stop" : "start") : x.service === "scene" ? `scene:${x.scene_name}` : x.service;
      if (was && [...how.options].some((o) => o.value === was)) how.value = was;
      pct.hidden = kelvin.hidden = !lightOn();
    };
    what.addEventListener("change", fill);
    how.addEventListener("change", () => { pct.hidden = kelvin.hidden = !lightOn(); });
    fill();
    const rm = el("button", "", "✕");
    rm.type = "button";
    rm.addEventListener("click", () => line.remove());
    line.append(what, how, pct, kelvin, rm);
    line.read = () => {
      if (!what.value) return null;
      if (what.value.startsWith("scene:")) return { scene: what.value.slice(6), ...(how.value === "stop" ? { stop: true } : {}) };
      if (how.value.startsWith("scene:")) return { entity_id: what.value, service: "scene", scene_name: how.value.slice(6) };
      const out = { entity_id: what.value, service: how.value };
      if (lightOn()) {
        const data = {};
        if (pct.value) data.brightness_pct = Number(pct.value);
        if (kelvin.value) data.color_temp_kelvin = Number(kelvin.value);
        if (Object.keys(data).length) out.data = data;
      }
      return out;
    };
    list.append(line);
  };
  (a?.actions?.length ? a.actions : [{}]).forEach(addAction);
  const more = el("button", "", t("hauto.add_action"));
  more.type = "button";
  more.addEventListener("click", () => addAction());
  const out = el("span", "muted");
  const save = el("button", "", t("scene.save")), cancel = el("button", "", t("scene.cancel"));
  cancel.addEventListener("click", close);
  save.addEventListener("click", async () => {
    const actions = [...list.children].map((l) => l.read()).filter(Boolean);
    const body = { id: a?.id, name: name.value.trim(), enabled: a ? a.enabled : true, actions,
      when: { type: type.value, at: at.value, offset_min: Number(off.value) || 0, days: [...picked].sort() } };
    save.disabled = true;
    try { await call("/v1/aurora/home/automations", { method: "POST", body: JSON.stringify(body) }); close(); reload(); }
    catch (e) { out.textContent = t("ev.error", { m: e.message }); save.disabled = false; }
  });
  const step = (k, ...xs) => { const s = el("div", "scene-step"); s.append(el("h4", "", t(k)), ...xs); return s; };
  const bar = el("div", "appr-actions");
  bar.append(save, cancel, out);
  f.append(step("scene.step_name", name), step("hauto.step_when", type, atL, offL, days),
    step("hauto.step_what", list, more), el("p", "muted", t("hauto.chat_hint")), bar);
  return f;
}

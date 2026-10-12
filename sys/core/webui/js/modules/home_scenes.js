// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎨 Scenes on the 🏠 page (hom_scenes): any user's own, on the devices they choose (owner, 2026-10-12: «uno può crearsi
// le scene che vuole con le configurazioni che vuole selezionando i dispositivi che vuole, in modo guidato e semplice»).
// A guided editor in four steps — name, devices, colours, effect and time — and ▶ / ⏹ / ✏️ / 🗑️ for each scene.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

// the colour names hom_scenes knows, with a swatch to show
const SWATCH = { rosso: "#e53935", verde: "#43a047", blu: "#1e88e5", oro: "#d4a017", giallo: "#fdd835",
  arancione: "#fb8c00", viola: "#8e24aa", rosa: "#f48fb1", ciano: "#00acc1", magenta: "#d81b60",
  bianco: "#f5f5f5", "bianco caldo": "#ffe0b2" };
const SWITCHES = new Set(["switch", "fan", "input_boolean"]);

const swatchOf = (c) => (Array.isArray(c) ? `hsl(${c[0]} ${c[1]}% 50%)` : SWATCH[c] || c);

export async function scenesBlock(devices, reload) {
  let r;
  try { r = await call("/v1/aurora/home/scenes"); } catch { return null; }
  const lights = [], plugs = [];
  for (const d of devices) {
    for (const e of d.entities) {
      if (e.domain === "light") lights.push({ ...e, device: d.name });
      else if (SWITCHES.has(e.domain)) plugs.push({ ...e, device: d.name });
    }
  }
  if (!lights.length && !plugs.length) return null;              // nothing a scene could use
  const block = el("section", "home-group");
  const names = Object.keys(r.scenes);
  const add = el("button", "", t("scene.new"));
  const head = el("div", "home-head");
  head.append(el("h3", "setting-cat home-kind", `${t("home.scenes")} · ${names.length}`), add);
  const card = el("section", "home-card");
  const box = el("div", "scene-editor");
  box.hidden = true;
  if (!names.length) card.append(el("p", "muted", t("scene.none")));
  for (const k of names) card.append(row(k, r.scenes[k], r.running.includes(k), reload, () => open(r.scenes[k])));
  add.addEventListener("click", () => open(null));
  block.append(head, box, card);
  return block;

  function open(scene) {
    box.replaceChildren(editor(scene, lights, plugs, () => { box.hidden = true; }, reload));
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function row(k, s, on, reload, edit) {
  const line = el("div", "home-entity");
  const dots = el("span", "scene-dots");
  for (const c of s.colours) { const d = el("span", "scene-dot"); d.style.background = swatchOf(c); dots.append(d); }
  line.append(el("span", "home-name", `${on ? "▶ " : ""}${s.name}`), dots,
    el("span", "home-state", t("home.scene_info", { n: s.lights.length + (s.switches || []).length, c: s.colours.length, s: s.every_s })));
  const act = async (what, b) => {
    b.disabled = true;
    try { await call(`/v1/aurora/home/scenes/${encodeURIComponent(k)}/${what}`, { method: "POST" }); }
    catch (e) { b.textContent = t("ev.error", { m: e.message }); }
    setTimeout(reload, 800);
  };
  const go = el("button", on ? "approve" : "", on ? t("home.scene_stop") : t("home.scene_start"));
  go.addEventListener("click", () => act(on ? "off" : "start", go));
  const ed = el("button", "", "✏️");
  ed.title = t("scene.edit");
  ed.addEventListener("click", edit);
  const del = el("button", "", "🗑️");
  del.addEventListener("click", () => { if (confirm(t("scene.delete_q", { name: s.name }))) act("delete", del); });
  line.append(go, ed, del);
  return line;
}

function editor(scene, lights, plugs, close, reload) {
  const s = scene || { name: "", lights: [], switches: [], colours: ["rosso", "verde"], every_s: 5, mode: "chase", brightness: 80, minutes: 0 };
  const form = el("div", "home-card scene-form");
  const step = (n, key) => { const h = el("h4", "", `${n}. ${t(key)}`); form.append(h); return h; };

  step(1, "scene.step_name");
  const name = el("input");
  name.placeholder = t("scene.name_hint");
  name.value = s.name;
  form.append(name);

  step(2, "scene.step_devices");
  const picked = new Set([...s.lights, ...(s.switches || [])]);
  const pick = (list, title) => {
    if (!list.length) return;
    form.append(el("p", "muted", title));
    const grid = el("div", "scene-pick");
    for (const e of list) {
      const l = el("label", "scene-opt");
      const c = el("input");
      c.type = "checkbox";
      c.checked = picked.has(e.entity_id);
      c.addEventListener("change", () => { c.checked ? picked.add(e.entity_id) : picked.delete(e.entity_id); colourStep.hidden = !anyLight(); });
      const off = ["unavailable", "unknown"].includes(e.state) ? ` (${t("scene.offline")})` : "";
      l.append(c, el("span", "", `${e.name || e.entity_id}${off}`));
      grid.append(l);
    }
    form.append(grid);
  };
  pick(lights, t("scene.lights"));
  pick(plugs, t("scene.plugs"));
  const anyLight = () => lights.some((e) => picked.has(e.entity_id));

  const colourStep = el("div");
  colourStep.append(el("h4", "", `3. ${t("scene.step_colours")}`));
  const chosen = [...s.colours];
  const order = el("div", "scene-dots scene-order");
  const draw = () => {
    order.replaceChildren(...chosen.map((c, i) => {
      const d = el("button", "scene-dot scene-big");
      d.style.background = swatchOf(c);
      d.title = `${Array.isArray(c) ? c.join(",") : c} — ${t("scene.remove")}`;
      d.addEventListener("click", () => { chosen.splice(i, 1); draw(); });
      return d;
    }));
    if (!chosen.length) order.append(el("span", "muted", t("scene.no_colour")));
  };
  const chips = el("div", "scene-dots");
  for (const [n, hex] of Object.entries(SWATCH)) {
    const b = el("button", "scene-chip", n);
    b.style.borderColor = hex;
    b.addEventListener("click", () => { chosen.push(n); draw(); });
    chips.append(b);
  }
  const custom = el("input");
  custom.type = "color";
  custom.value = "#00ff88";
  const addCustom = el("button", "", t("scene.add_colour"));
  addCustom.addEventListener("click", () => { chosen.push(custom.value); draw(); });
  chips.append(custom, addCustom);
  colourStep.append(el("p", "muted", t("scene.colours_hint")), chips, order);
  form.append(colourStep);
  colourStep.hidden = !anyLight();
  draw();

  step(4, "scene.step_effect");
  const mode = el("select");
  for (const m of ["chase", "together"]) mode.append(Object.assign(el("option", "", t(`scene.mode_${m}`)), { value: m }));
  mode.value = s.mode;
  const num = (v, min, max, key) => {
    const i = el("input", "home-number");
    i.type = "number"; i.min = min; i.max = max; i.value = v;
    const l = el("label", "scene-num");
    l.append(el("span", "", t(key)), i);
    return [l, i];
  };
  const [everyL, every] = num(s.every_s, 3, 3600, "scene.every");
  const [brightL, bright] = num(s.brightness, 1, 100, "scene.brightness");
  const [minL, mins] = num(s.minutes, 0, 1440, "scene.minutes");
  form.append(mode, everyL, brightL, minL);

  const msg = el("span", "muted");
  const save = async (andStart) => {
    const body = {
      name: name.value.trim(), was: scene ? scene.name : "",
      lights: lights.filter((e) => picked.has(e.entity_id)).map((e) => e.entity_id),
      switches: plugs.filter((e) => picked.has(e.entity_id)).map((e) => e.entity_id),
      colours: chosen, mode: mode.value, every_s: Number(every.value), brightness: Number(bright.value), minutes: Number(mins.value),
    };
    try {
      const out = await call("/v1/aurora/home/scenes", { method: "POST", body: JSON.stringify(body) });
      if (andStart) await call(`/v1/aurora/home/scenes/${encodeURIComponent(out.name)}/start`, { method: "POST" });
      close();
      reload();
    } catch (e) { msg.textContent = t("ev.error", { m: e.message }); }
  };
  const bar = el("div", "appr-actions");
  const ok = el("button", "approve", t("scene.save"));
  ok.addEventListener("click", () => save(false));
  const tryIt = el("button", "", t("scene.save_start"));
  tryIt.addEventListener("click", () => save(true));
  const cancel = el("button", "", t("scene.cancel"));
  cancel.addEventListener("click", close);
  bar.append(ok, tryIt, cancel, msg);
  form.append(bar, el("p", "muted", t("scene.chat_hint")));
  return form;
}

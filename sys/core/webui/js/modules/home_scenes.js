// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎨 Scenes on the 🏠 page (hom_scenes): what lights do — a white of a warmth and brightness, or colours that move by
// blocks, all together, or gradually through every shade (owner, 2026-10-20: «le scene stabiliscono cosa fanno le luci,
// la selezione delle scene+luce la si fa negli automatismi»). A scene holds no lights: the automations choose them;
// here it is tried on a light picked beside its ▶. A guided editor — name, kind, colours or white, effect and time.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

// the colour names hom_scenes knows, with a swatch to show
const SWATCH = { rosso: "#e53935", arancione: "#fb8c00", giallo: "#fdd835", oro: "#d4a017", verde: "#43a047",
  ciano: "#00acc1", blu: "#1e88e5", viola: "#8e24aa", magenta: "#d81b60", rosa: "#f48fb1",
  bianco: "#f5f5f5", "bianco caldo": "#ffe0b2" };

// a white by its warmth: 2000 K (candle) … 6500 K (daylight), drawn as its colour
const kelvinHex = (k) => {
  const f = Math.max(0, Math.min(1, (k - 2000) / 4500));
  const mix = (a, b) => Math.round(a + (b - a) * f);
  return `rgb(${mix(255, 220)},${mix(176, 232)},${mix(90, 255)})`;
};
const swatchOf = (c) => (Array.isArray(c) ? `hsl(${c[0]} ${c[1]}% 50%)`
  : typeof c === "string" && /^k\d+$/.test(c) ? kelvinHex(Number(c.slice(1))) : SWATCH[c] || c);
const isWhite = (s) => s.colours.length === 1 && typeof s.colours[0] === "string" && /^k\d+$/.test(s.colours[0]);

export async function scenesBlock(devices, reload) {
  let r;
  try { r = await call("/v1/aurora/home/scenes"); } catch { return null; }
  const lights = [];
  for (const d of devices) for (const e of d.entities) if (e.domain === "light") lights.push({ ...e, device: d.name });
  if (!lights.length) return null;                               // nothing a scene could light
  const block = el("section", "home-group");
  const names = Object.keys(r.scenes);
  const add = el("button", "", t("scene.new"));
  const head = el("div", "home-head");
  head.append(el("h3", "setting-cat home-kind", `${t("home.scenes")} · ${names.length}`), add);
  const card = el("section", "home-card");
  const box = el("div", "scene-editor");
  box.hidden = true;
  if (!names.length) card.append(el("p", "muted", t("scene.none")));
  for (const k of names) card.append(row(k, r.scenes[k], r.running.includes(k), lights, reload, () => open(r.scenes[k])));
  add.addEventListener("click", () => open(null));
  block.append(head, el("p", "muted", t("scene.hint")), box, card);
  return block;

  function open(scene) {
    box.replaceChildren(editor(scene, lights, () => { box.hidden = true; }, reload));
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// a light to try a scene on
function lightPick(lights) {
  const s = el("select", "scene-try");
  for (const e of lights) {
    const off = ["unavailable", "unknown"].includes(e.state) ? ` (${t("scene.offline")})` : "";
    s.append(new Option(`${e.name || e.entity_id}${off}`, e.entity_id));
  }
  return s;
}

function row(k, s, on, lights, reload, edit) {
  const line = el("div", "home-entity scene-row");
  const dots = el("span", "scene-dots");
  for (const c of s.colours) { const d = el("span", "scene-dot"); d.style.background = swatchOf(c); dots.append(d); }
  const what = isWhite(s) ? t("scene.info_white", { k: s.colours[0].slice(1), b: s.brightness })
    : t("scene.info_colours", { c: s.colours.length, m: t(`scene.short_${s.mode}`), s: s.every_s, b: s.brightness });
  line.append(el("span", "home-name", `${on ? "▶ " : ""}${s.name}`), dots, el("span", "home-state", what));
  const act = async (what2, b, body) => {
    b.disabled = true;
    try { await call(`/v1/aurora/home/scenes/${encodeURIComponent(k)}/${what2}`, { method: "POST", body: JSON.stringify(body || {}) }); }
    catch (e) { b.textContent = t("ev.error", { m: e.message }); }
    setTimeout(reload, 800);
  };
  const where = lightPick(lights);
  where.title = t("scene.try_on");
  const go = el("button", "", t("home.scene_try"));
  go.addEventListener("click", () => act("start", go, { lights: [where.value] }));
  // ⏹ the light picked beside it: any scene on it stopped, the light off (a white scene is over at once: it has
  // nothing «running» to stop)
  const off = el("button", on ? "approve" : "", "⏹");
  off.title = t("home.scene_stop");
  off.addEventListener("click", () => act("off", off, { lights: [where.value] }));
  const ed = el("button", "", "✏️");
  ed.title = t("scene.edit");
  ed.addEventListener("click", edit);
  const del = el("button", "", "🗑️");
  del.addEventListener("click", () => { if (confirm(t("scene.delete_q", { name: s.name }))) act("delete", del); });
  const tools = el("span", "scene-tools");
  tools.append(where, go, off, ed, del);
  line.append(tools);
  return line;
}

function editor(scene, lights, close, reload) {
  const s = scene || { name: "", colours: ["rosso", "verde"], every_s: 1, mode: "fade", brightness: 80, minutes: 0 };
  const form = el("div", "home-card scene-form");
  const step = (n, key) => { const h = el("h4", "", `${n}. ${t(key)}`); form.append(h); return h; };

  step(1, "scene.step_name");
  const name = el("input");
  name.placeholder = t("scene.name_hint");
  name.value = s.name;
  form.append(name);

  // 2. a white (its warmth) or colours
  step(2, "scene.step_kind");
  const kind = el("select");
  for (const k of ["white", "colours"]) kind.append(new Option(t(`scene.kind_${k}`), k));
  kind.value = scene && isWhite(scene) ? "white" : "colours";
  form.append(kind);

  const whiteStep = el("div");
  const kelvin = el("input");
  kelvin.type = "range"; kelvin.min = 2000; kelvin.max = 6500; kelvin.step = 25;
  kelvin.value = scene && isWhite(scene) ? scene.colours[0].slice(1) : 3000;
  const kOut = el("span", "scene-k");
  const kShow = () => { kOut.textContent = `${kelvin.value} K`; kOut.style.background = kelvinHex(Number(kelvin.value)); };
  kelvin.addEventListener("input", kShow);
  kShow();
  whiteStep.append(el("p", "muted", t("scene.white_hint")), kelvin, kOut);
  form.append(whiteStep);

  const colourStep = el("div");
  const chosen = scene && !isWhite(scene) ? [...scene.colours] : [...s.colours];
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
  const mode = el("select");
  for (const m of ["fade", "chase", "together"]) mode.append(new Option(t(`scene.mode_${m}`), m));
  mode.value = s.mode || "fade";
  colourStep.append(el("p", "muted", t("scene.colours_hint")), chips, order, el("h4", "", t("scene.step_effect")), mode);
  form.append(colourStep);
  draw();

  // 3. brightness and time
  step(3, "scene.step_time");
  const num = (v, min, max, key) => {
    const i = el("input", "home-number");
    i.type = "number"; i.min = min; i.max = max; i.value = v;
    const l = el("label", "scene-num");
    l.append(el("span", "", t(key)), i);
    return [l, i];
  };
  const [brightL, bright] = num(s.brightness, 1, 100, "scene.brightness");
  const [everyL, every] = num(s.every_s, 1, 3600, "scene.every");             // the server: ≥ 1 s graduale, ≥ 3 s the others
  const [minL, mins] = num(s.minutes, 0, 1440, "scene.minutes");
  form.append(brightL, everyL, minL);
  const showKind = () => {
    const white = kind.value === "white";
    whiteStep.hidden = white ? false : true;
    colourStep.hidden = white;
    everyL.hidden = white;                         // a white is set once
  };
  kind.addEventListener("change", showKind);
  showKind();

  // 4. tried on a light (optional): the automations choose the lights for good
  step(4, "scene.step_try");
  const where = lightPick(lights);
  form.append(where);

  const msg = el("span", "muted");
  const save = async (andTry) => {
    const white = kind.value === "white";
    const body = {
      name: name.value.trim(), was: scene ? scene.name : "", lights: [], switches: [],
      colours: white ? [`${kelvin.value}K`] : chosen, mode: white ? "together" : mode.value,
      every_s: Number(every.value), brightness: Number(bright.value), minutes: Number(mins.value),
    };
    try {
      const out = await call("/v1/aurora/home/scenes", { method: "POST", body: JSON.stringify(body) });
      if (andTry) await call(`/v1/aurora/home/scenes/${encodeURIComponent(out.name)}/start`, { method: "POST", body: JSON.stringify({ lights: [where.value] }) });
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

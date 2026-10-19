// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📡 The telescope PC's camera in the live collimation (owner, 2026-10-19: «un server da installare nel mini PC… che
// invii in streaming»; «fai in modo che aurora possa procedere come se usasse l'interfaccia ocal… zoom, gain etc»): the
// PC linked once (a key, the zip with the script that installs what it needs, the command), its cameras listed, the
// one chosen shown; and what the collimator's own program sets — resolution, gain, exposure (auto or by hand),
// brightness, contrast, focus (auto or by hand), zoom… — asked from here, each with what the camera says it took.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const FPS = [5, 10, 15, 20];
const SEND = [1280, 1920, 0];                  // the stream's width; 0: as the camera takes it

export function pcPanel(card, { show, stop }) {
  const cams = el("select");
  const go = el("button", "approve", `📡 ${t("col.pc_use")}`);
  const halt = el("button", "btn", `⏹ ${t("col.live_stop")}`);
  const link = el("button", "btn", `🔑 ${t("col.pc_link")}`);
  const said = el("small", "muted");
  const how = el("div", "col-pc-how");
  const row = el("div", "col-row");
  // the package always in sight (owner, 20 Oct: «non vedo dove scaricare il ps1»): it holds no key, the key comes
  // with «Collega il PC»
  const bundle = () => {
    const a = el("a", "btn", `⬇️ ${t("col.pc_script")}`);
    a.href = "/v1/aurora/astro/camera/bundle";
    a.download = "aurora_camera.zip";
    return a;
  };
  row.append(el("strong", "", `📡 ${t("col.pc")}`), cams, go, halt, bundle(), link, said);
  const controls = el("details", "col-pc-controls");
  controls.hidden = true;
  const put = (body) => call("/v1/aurora/astro/camera", { method: "PUT", body: JSON.stringify(body) });
  let built = false;
  const read = {};

  function build(s) {
    built = true;
    const box = el("div", "col-row");
    const opt = (sel, items, label, value) => {
      sel.replaceChildren(...items.map((v) => { const o = el("option", "", label(v)); o.value = JSON.stringify(v); return o; }));
      if (value !== undefined) sel.value = JSON.stringify(value);
      return sel;
    };
    const size = opt(el("select"), s.sizes, (v) => `${v[0]}×${v[1]}`, s.settings.size || [1920, 1080]);
    const fps = opt(el("select"), FPS, (v) => `${v} fps`, s.settings.fps || 10);
    const send = opt(el("select"), SEND, (v) => (v ? `${v} px` : t("col.pc_full")), s.settings.send_width ?? 1280);
    for (const [sel, key] of [[size, "size"], [fps, "fps"], [send, "send_width"]]) {
      sel.addEventListener("change", () => put({ settings: { [key]: JSON.parse(sel.value) } }));
    }
    const lab = (text, ...x) => { const l = el("label", "", text); l.append(...x); return l; };
    box.append(lab(t("col.pc_size"), size), lab(t("col.pc_fps"), fps), lab(t("col.pc_send"), send));
    for (const k of s.switches) {
      const cb = el("input");
      cb.type = "checkbox";
      cb.checked = !!s.settings[k];
      cb.addEventListener("change", () => put({ settings: { [k]: cb.checked } }));
      box.append(lab(t(`col.pc_${k}`), cb));
    }
    const nums = el("div", "col-row");
    for (const k of s.controls) {
      const i = el("input", "col-num");
      Object.assign(i, { type: "number", step: "any", value: s.settings[k] ?? "" });
      i.placeholder = "—";
      let timer = 0;
      i.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => put({ settings: { [k]: i.value === "" ? null : Number(i.value) } }), 400);
      });
      read[k] = el("small", "muted");
      nums.append(lab(t(`col.pc_${k}`), i, read[k]));
    }
    const dialog = el("button", "btn", `🪟 ${t("col.pc_dialog")}`);
    dialog.addEventListener("click", () => put({ settings: { dialog: true } }));
    controls.replaceChildren(el("summary", "", `🎛️ ${t("col.pc_controls")}`), el("p", "muted", t("col.pc_controls_hint")), box, nums, dialog);
  }

  async function state() {
    try {
      const s = await call("/v1/aurora/astro/camera");
      const keep = cams.value || s.wanted;
      cams.replaceChildren(...s.devices.map((d) => { const o = el("option", "", d); o.value = d; return o; }));
      if (keep) cams.value = keep;
      said.textContent = !s.key ? t("col.pc_none") : s.pc_seen_s === null || s.pc_seen_s > 15 ? t("col.pc_off")
        : s.camera?.error ? `⚠️ ${s.camera.error}` : s.live ? t("col.pc_live", { fps: s.fps }) : t("col.pc_on");
      controls.hidden = !s.key;
      if (s.key && !built) build(s);
      const v = s.camera?.values || {};
      for (const k of Object.keys(read)) read[k].textContent = v[k] !== undefined ? t("col.pc_took", { v: v[k] }) : "";
      return s;
    } catch { said.textContent = ""; return null; }
  }

  go.addEventListener("click", async () => {
    if (!cams.value) return;
    await put({ wanted: cams.value });
    show();
    state();
  });
  halt.addEventListener("click", async () => {
    stop();
    await put({ wanted: "" });
    state();
  });
  link.addEventListener("click", async () => {
    if (!confirm(t("col.pc_link_q"))) return;
    const k = await call("/v1/aurora/astro/camera/key", { method: "POST" });
    const dl = bundle();
    const steps = el("ol", "col-steps");
    for (const n of [1, 2, 3, 4, 5]) steps.append(el("li", "", t(`col.pc_step${n}`)));
    // the command in sight, with its copy (owner, 20 Oct: «il comando powershell nella pagina non c'è»: it was a
    // small grey box under the steps); shown once, as the key
    const cmd = el("pre", "col-text col-pc-cmd", k.command);
    const copy = el("button", "approve", `📋 ${t("col.pc_copy")}`);
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(k.command); copy.textContent = `✅ ${t("col.pc_copied")}`; }
      catch { getSelection().selectAllChildren(cmd); }
    });
    how.replaceChildren(el("strong", "", `🖥️ ${t("col.pc_cmd")}`), cmd, copy, el("p", "muted", t("col.pc_cmd_once")),
      el("p", "muted", t("col.pc_how")), dl, steps);
    how.scrollIntoView({ behavior: "smooth", block: "start" });
    state();
  });
  const timer = setInterval(() => { if (!document.body.contains(card)) clearInterval(timer); else state(); }, 4000);
  state();
  return { row, how, controls };
}

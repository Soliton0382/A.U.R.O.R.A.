// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎯 Collimation live (owner, 2026-10-19: «un'interfaccia grafica sul mini PC… uso la camera ocal ma con la nostra
// interfaccia, sposto l'insieme di cerchi per farli combaciare con il draw tube… poi si modificano solo i raggi… il tipo
// di rapporto focale… la possibilità di variare manualmente il valore di offset»). Any collimating camera the browser
// sees (a USB camera: the OCAL's own program closed, it holds the camera) or a picture; a train of circles drawn over
// it: the drawtube (dragged with the whole train onto the tube's edge), the centre spot and the collimator's reflection
// on its centre (the focuser's axis: steps 1 and 3), the secondary's outline displaced along the tube by the offset
// (step 2). The radii set by hand to the reflections' sizes; the displacement then follows from them — the shadow's
// size against the secondary's gives the camera's distance (ast_ocal.expected, the same formula), the focal ratio and
// the secondary's size the rest — or is typed by hand. The train kept in this browser: after a secondary taken out,
// the circles are where they were. Or the telescope PC's camera relayed through Aurora (owner, 19 Oct: «un server da
// installare nel mini PC… che invii in streaming»): its script sends the camera chosen here, seen from any device.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { pcPanel } from "./astro_collim_pc.js";

const KEY = "aurora.collim.live";
const RATIOS = [2.8, 3, 3.5, 3.8, 4, 4.5, 5, 5.5, 6, 7, 8];
// a typical secondary for each focal ratio, × the aperture: only until the person types their own
const TYPICAL = { 2.8: 0.45, 3: 0.42, 3.5: 0.38, 3.8: 0.36, 4: 0.35, 4.5: 0.31, 5: 0.27, 5.5: 0.25, 6: 0.23, 7: 0.2, 8: 0.18 };
const CIRCLES = ["drawtube", "secondary", "shadow", "ocal", "spot"];
const COLOR = { drawtube: "#4060ff", secondary: "#ff40ff", shadow: "#00dcff", ocal: "#ff8c00", spot: "#ff2020" };
// each circle's radius its own, × the picture's width (owner, 19 Oct: «i raggi li facciamo che si possono modificare in
// modo indipendente»): the drawtube changed, the others stay
const FIRST = { cx: 0.5, cy: 0.5, rad: { drawtube: 0.42, secondary: 0.26, shadow: 0.084, ocal: 0.046, spot: 0.013 },
  code: { on: false, x: 2000, y: 1500, w: 4000, h: 3000 },
  angle: 0, side: 1, manual: null, ratio: 4, aperture: 200, secondary_mm: 70, axis: { dx: 0, dy: 0 }, zoom: 1, night: false };

// the same geometry as ast_ocal: the offset secondary's outline seen from `view` mm, centred from the focal point
export function shift(view, focus, half) {
  const c = (focus - Math.sqrt(focus * focus + 4 * half * half)) / 2;
  const up = (c + half) / (view - c - half), down = (c - half) / (view - c + half);
  return (up + down) / (up - down);
}

// the shadow's displacement, × its radius, toward the primary's end: the secondary offset (each way) seen in the concave
// primary, magnified as its size is — offset / half the secondary, whatever the camera's distance (first drawn
// concentric: the owner, 19 Oct: «sono tutti concentrici non hanno l'offset corretto»)
export function shadowShift(m, ap, f) {
  if (!(m > 0 && m < ap && ap < f)) return 0;
  const focus = (m * f) / ap;
  return -(focus - Math.sqrt(focus * focus + m * m)) / 2 / (m / 2);
}

// {shift, view, offset_mm, shadow} from the shadow-to-secondary ratio k: the shadow the concave primary's image, × f/(f − S)
export function offsetFor(k, m, ap, f) {
  if (!(k > 0.03 && k < 0.8 && m > 0 && m < ap && ap < f)) return null;
  const focus = (m * f) / ap, s = f - focus, mag = f / focus;
  if (mag <= k) return null;
  const view = (k * (s + s * mag)) / (mag - k);
  if (view <= m) return null;
  const offset = -(focus - Math.sqrt(focus * focus + m * m)) / 2;
  return { shift: shift(view, focus, m / 2), view, offset_mm: offset, shadow: shadowShift(m, ap, f) };
}

function load() {
  let st;
  try { st = { ...FIRST, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch { st = { ...FIRST }; }
  if (st.R && !st.rad?.v) {                    // the circles kept before: their radii were × the drawtube's
    st.rad = { drawtube: st.R, ...Object.fromEntries(CIRCLES.slice(1).map((k) => [k, (st[k] ?? FIRST.rad[k] / 0.42) * st.R])) };
  }
  st.rad = { ...FIRST.rad, ...st.rad, v: 2 };
  st.code = { ...FIRST.code, ...st.code };
  return st;
}

function keep(st) {
  try { localStorage.setItem(KEY, JSON.stringify(st)); } catch { /* this visit only */ }
}

function num(value, step, min, max) {
  const i = el("input", "col-num");
  Object.assign(i, { type: "number", step, min, max, value });
  return i;
}

export function liveCard(scope) {
  const st = load();
  if (scope?.secondary_mm && !localStorage.getItem(KEY)) {        // the person's own tube, the first time
    st.secondary_mm = scope.secondary_mm;
    st.aperture = scope.aperture_mm || st.aperture;
    st.ratio = scope.focal_mm && scope.aperture_mm ? Math.round((scope.focal_mm / scope.aperture_mm) * 10) / 10 : st.ratio;
  }
  let pick = "drawtube";
  const c = el("section", "astro-card wide col-live");
  c.append(el("h4", "", `🎯 ${t("col.live")}`), el("p", "muted", t("col.live_hint")));

  // the source: a camera the browser sees, or a picture
  const cams = el("select");
  const start = el("button", "approve", `📷 ${t("col.live_start")}`);
  const stop = el("button", "btn", `⏹ ${t("col.live_stop")}`);
  const file = el("input");
  Object.assign(file, { type: "file", accept: "image/*", hidden: true });
  const fromPic = el("button", "btn", `🖼️ ${t("col.live_picture")}`);
  fromPic.addEventListener("click", () => file.click());
  const src = el("div", "col-row");
  src.append(cams, start, stop, fromPic, file);

  // the telescope PC's camera, relayed through Aurora (astro_collim_pc.js): shown here when chosen there
  const pc = pcPanel(c, {
    show: () => {
      stream?.getTracks().forEach((x) => x.stop());
      remote.onload = () => { remote.onload = null; draw(); };
      remote.src = `/v1/aurora/astro/camera/stream?t=${Date.now()}`;
      remote.hidden = false;
      video.hidden = true;
      still.hidden = true;
    },
    stop: () => remote.removeAttribute("src"),
  });

  const stage = el("div", "col-stage");
  const video = el("video");
  Object.assign(video, { autoplay: true, muted: true, playsInline: true });
  const still = el("img");
  still.hidden = true;
  const remote = el("img");
  remote.hidden = true;
  const canvas = el("canvas", "col-overlay");
  const inner = el("div", "col-inner");                  // what the digital zoom enlarges: the picture and the circles
  inner.append(video, still, remote, canvas);
  stage.append(inner);
  const said = el("p", "col-say");
  let stream = null;

  const media = () => (!remote.hidden ? remote : still.hidden ? video : still);
  const size = () => {
    const m = media();
    return [m.videoWidth || m.naturalWidth || 1280, m.videoHeight || m.naturalHeight || 720];
  };

  // the scope: focal ratio, aperture, secondary; the offset automatic or typed
  const ratio = el("select");
  for (const r of RATIOS) { const o = el("option", "", `f/${r}`); o.value = r; ratio.append(o); }
  ratio.value = String(st.ratio);
  const ap = num(st.aperture, 1, 50, 2000);
  const sec = num(st.secondary_mm, 1, 10, 600);
  const auto = el("input");
  auto.type = "checkbox";
  auto.checked = st.manual === null;
  const manual = num(st.manual ?? 0, 0.5, -40, 40);
  manual.disabled = auto.checked;
  const saveScope = el("button", "btn", `💾 ${t("col.live_save_scope")}`);
  const tube = el("div", "col-row");
  const lab = (k, ...x) => { const l = el("label", "", t(k)); l.append(...x); return l; };
  tube.append(lab("col.live_ratio", ratio), lab("col.live_aperture", ap), lab("col.live_secondary", sec),
    lab("col.live_auto", auto), lab("col.live_manual", manual), saveScope);
  ratio.addEventListener("change", () => {
    st.ratio = Number(ratio.value);
    if (!scope?.secondary_mm) { st.secondary_mm = Math.round(st.aperture * TYPICAL[st.ratio]); sec.value = st.secondary_mm; }
    draw();
  });
  ap.addEventListener("input", () => { st.aperture = Number(ap.value); draw(); });
  sec.addEventListener("input", () => { st.secondary_mm = Number(sec.value); draw(); });
  auto.addEventListener("change", () => { manual.disabled = auto.checked; st.manual = auto.checked ? null : Number(manual.value); draw(); });
  manual.addEventListener("input", () => { if (!auto.checked) { st.manual = Number(manual.value); draw(); } });
  saveScope.addEventListener("click", async () => {
    try {
      await call("/v1/aurora/astro/collimation/scope", { method: "PUT", body: JSON.stringify({ secondary_mm: st.secondary_mm, aperture_mm: st.aperture, focal_mm: Math.round(st.aperture * st.ratio) }) });
      saveScope.textContent = `✅ ${t("col.live_saved")}`;
    } catch (e) { saveScope.textContent = `⚠️ ${e.message}`; }
  });

  // the circles: which one the radius slider, the wheel and ± change; the tube's axis in the picture
  const which = el("div", "col-row col-which");
  const radius = el("input");
  Object.assign(radius, { type: "range", min: 0.005, max: 1.2, step: 0.001 });
  for (const k of CIRCLES) {
    const b = el("button", "cat-chip", t(`col.c.${k}`));
    b.style.borderColor = COLOR[k];
    b.dataset.c = k;
    b.addEventListener("click", () => { pick = k; mark(); });
    which.append(b);
  }
  radius.max = 0.8;
  radius.min = 0.002;
  const px = el("input", "col-num");                       // the radius in the picture's pixels, typed or stepped
  Object.assign(px, { type: "number", step: 1, min: 1 });
  const step = (d) => { const [w] = size(); st.rad[pick] = Math.max(1, st.rad[pick] * w + d) / w; mark(); draw(); };
  const less = el("button", "btn", "−"), more = el("button", "btn", "+");
  less.addEventListener("click", () => step(-1));
  more.addEventListener("click", () => step(1));
  const mark = () => {
    which.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.c === pick));
    radius.value = st.rad[pick];
    px.value = Math.round(st.rad[pick] * size()[0]);
  };
  radius.addEventListener("input", () => { st.rad[pick] = Number(radius.value); px.value = Math.round(st.rad[pick] * size()[0]); draw(); });
  px.addEventListener("change", () => { if (Number(px.value) > 0) { st.rad[pick] = Number(px.value) / size()[0]; mark(); draw(); } });
  const angle = el("input");
  Object.assign(angle, { type: "range", min: 0, max: 359, step: 1, value: st.angle });
  angle.addEventListener("input", () => { st.angle = Number(angle.value); draw(); });
  const flip = el("button", "btn", "⇄");
  flip.title = t("col.live_flip");
  flip.addEventListener("click", () => { st.side = -st.side; draw(); });
  const reset = el("button", "btn", t("col.live_reset"));
  reset.addEventListener("click", () => { Object.assign(st, { ...FIRST, rad: { ...FIRST.rad, v: 2 }, code: st.code, ratio: st.ratio, aperture: st.aperture, secondary_mm: st.secondary_mm, manual: st.manual }); mark(); draw(); });
  const sizes = el("div", "col-row");
  sizes.append(lab("col.live_radius", radius), lab("col.live_px", px), less, more, lab("col.live_axis", angle), flip, reset);

  // the view: digital zoom around the circles, night mode; the camera's true centre by turning it (as the collimator's
  // own program does): the centre spot marked, the collimator turned 180° in the focuser, marked again — the middle is
  // where the focuser's axis is at the reflections' depth, whatever the camera's own tilt or play
  const zoom = el("input");
  Object.assign(zoom, { type: "range", min: 1, max: 4, step: 0.05, value: st.zoom });
  zoom.addEventListener("input", () => { st.zoom = Number(zoom.value); draw(); });
  const night = el("input");
  night.type = "checkbox";
  night.checked = st.night;
  night.addEventListener("change", () => { st.night = night.checked; draw(); });
  const turn = el("button", "btn", `🔄 ${t("col.live_turn")}`);
  const unturn = el("button", "btn", t("col.live_unturn"));
  let marking = 0, first = null;
  turn.addEventListener("click", () => { marking = 1; first = null; said.textContent = t("col.live_turn1"); });
  unturn.addEventListener("click", () => { st.axis = { dx: 0, dy: 0 }; draw(); });
  const view = el("div", "col-row");
  view.append(lab("col.live_zoom", zoom), lab("col.live_night", night), turn, unturn);

  // the collimator's centre code (its own program's «Center Code», a pair of pixels the maker gives for each serial):
  // the reflections' circles on that pixel; the code's resolution given, so any picture's size takes it
  const codeOn = el("input");
  codeOn.type = "checkbox";
  codeOn.checked = st.code.on;
  const cn = (k, stepv) => {
    const i = num(st.code[k], stepv, 0, 20000);
    i.addEventListener("input", () => { st.code[k] = Number(i.value); draw(); });
    return i;
  };
  codeOn.addEventListener("change", () => { st.code.on = codeOn.checked; draw(); });
  const code = el("div", "col-row");
  code.append(lab("col.live_code_on", codeOn), lab("col.live_code_x", cn("x", 1)), lab("col.live_code_y", cn("y", 1)),
    lab("col.live_code_w", cn("w", 1)), lab("col.live_code_h", cn("h", 1)));

  const analyse = el("button", "primary", `🔎 ${t("col.live_analyse")}`);
  const verdict = el("ul", "an-findings");
  c.append(src, pc.row, pc.how, pc.controls, tube, which, sizes, view, code, stage, said, analyse, verdict,
    el("p", "muted", t("col.live_legend")));

  function circle(ctx, x, y, r, color, dashed) {
    ctx.setLineDash(dashed ? [10, 8] : []);
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, Math.max(1, r), 0, 2 * Math.PI);
    ctx.stroke();
  }

  function draw() {
    keep(st);
    const [w, h] = size();
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.lineWidth = Math.max(2, w / 500);
    const cx = st.cx * w, cy = st.cy * h, R = st.rad.drawtube * w;
    let ax = cx + (st.axis?.dx || 0) * w, ay = cy + (st.axis?.dy || 0) * h;     // the axis at the reflections' depth
    const odd = st.code.on && Math.abs(w / h - st.code.w / st.code.h) > 0.01;    // the code for another shape
    if (st.code.on && st.code.w > 0 && st.code.h > 0) { ax = (st.code.x / st.code.w) * w; ay = (st.code.y / st.code.h) * h; }
    inner.style.transformOrigin = `${st.cx * 100}% ${st.cy * 100}%`;
    inner.style.transform = st.zoom > 1 ? `scale(${st.zoom})` : "";
    c.classList.toggle("col-night", !!st.night);
    const a = (st.angle * Math.PI) / 180, dx = Math.cos(a) * st.side, dy = Math.sin(a) * st.side;
    const geo = offsetFor(st.rad.shadow / st.rad.secondary, st.secondary_mm, st.aperture, st.aperture * st.ratio);
    const sh = st.manual !== null ? st.manual / 100 : geo ? geo.shift : 0;
    const shs = shadowShift(st.secondary_mm, st.aperture, st.aperture * st.ratio);   // the shadow: toward the primary
    const rs = st.rad.secondary * w, rsh = st.rad.shadow * w;
    circle(ctx, cx, cy, R, COLOR.drawtube, false);
    circle(ctx, ax + dx * sh * rs, ay + dy * sh * rs, rs, COLOR.secondary, false);
    circle(ctx, ax - dx * shs * rsh, ay - dy * shs * rsh, rsh, COLOR.shadow, true);
    circle(ctx, ax, ay, st.rad.ocal * w, COLOR.ocal, false);
    circle(ctx, ax, ay, st.rad.spot * w, COLOR.spot, false);
    ctx.setLineDash([]);
    ctx.strokeStyle = "#3cff3c";                          // the focuser's axis: where the spot and the reflection go
    ctx.beginPath();
    ctx.moveTo(ax - R * 0.08, ay); ctx.lineTo(ax + R * 0.08, ay);
    ctx.moveTo(ax, ay - R * 0.08); ctx.lineTo(ax, ay + R * 0.08);
    ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,.35)";            // the tube's axis, the open end at the arrow
    ctx.beginPath();
    ctx.moveTo(cx - dx * R, cy - dy * R); ctx.lineTo(cx + dx * R, cy + dy * R);
    ctx.stroke();
    if (marking) return;                                  // the turn's instructions stay on screen
    said.textContent = (odd ? `⚠️ ${t("col.live_code_odd", { cw: st.code.w, ch: st.code.h, w, h })} ` : "") + (st.manual !== null
      ? t("col.live_said_manual", { s: (sh * 100).toFixed(1), h: (shs * 100).toFixed(1) })
      : geo ? t("col.live_said", { s: (sh * 100).toFixed(1), v: Math.round(geo.view), o: geo.offset_mm.toFixed(1), h: (shs * 100).toFixed(1) })
        : t("col.live_said_none"));
  }

  // the whole train dragged; the wheel changes the chosen circle
  let drag = null;
  const at = (ev) => {
    const r = canvas.getBoundingClientRect();
    return [(ev.clientX - r.left) / r.width, (ev.clientY - r.top) / r.height];
  };
  canvas.addEventListener("pointerdown", (ev) => {
    const [x, y] = at(ev);
    if (marking === 1) { first = [x, y]; marking = 2; said.textContent = t("col.live_turn2"); return; }
    if (marking === 2) {
      st.axis = { dx: (first[0] + x) / 2 - st.cx, dy: (first[1] + y) / 2 - st.cy };
      marking = 0;
      draw();
      const [w, h] = size();
      said.textContent = t("col.live_turned", { p: ((Math.hypot(st.axis.dx * w, st.axis.dy * h) / (st.rad.drawtube * w)) * 100).toFixed(1),
        x: Math.round((st.cx + st.axis.dx) * w), y: Math.round((st.cy + st.axis.dy) * h), w, h });
      return;
    }
    drag = { x, y, cx: st.cx, cy: st.cy };
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    const [x, y] = at(ev);
    st.cx = drag.cx + x - drag.x;
    st.cy = drag.cy + y - drag.y;
    draw();
  });
  canvas.addEventListener("pointerup", () => { drag = null; });
  canvas.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const f = ev.deltaY < 0 ? 1.01 : 1 / 1.01;
    st.rad[pick] *= f;
    mark();
    draw();
  }, { passive: false });

  async function cameras() {
    const list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
    cams.replaceChildren(...list.map((d, i) => { const o = el("option", "", d.label || `${t("col.live_camera")} ${i + 1}`); o.value = d.deviceId; return o; }));
    if (st.device && list.some((d) => d.deviceId === st.device)) cams.value = st.device;
  }
  start.addEventListener("click", async () => {
    if (!navigator.mediaDevices?.getUserMedia) { said.textContent = t("col.live_https"); return; }
    try {
      stream?.getTracks().forEach((x) => x.stop());
      stream = await navigator.mediaDevices.getUserMedia({ video: cams.value ? { deviceId: { exact: cams.value }, width: { ideal: 1920 } } : { width: { ideal: 1920 } } });
      video.srcObject = stream;
      still.hidden = true;
      remote.hidden = true;
      remote.removeAttribute("src");
      video.hidden = false;
      await cameras();
      st.device = stream.getVideoTracks()[0]?.getSettings().deviceId || st.device;
      video.onloadedmetadata = draw;
    } catch (e) { said.textContent = `${t("col.live_no_camera")} (${e.name})`; }
  });
  stop.addEventListener("click", () => { stream?.getTracks().forEach((x) => x.stop()); stream = null; });
  file.addEventListener("change", () => {
    const f = file.files[0];
    if (!f) return;
    still.onload = draw;
    still.src = URL.createObjectURL(f);
    still.hidden = false;
    remote.hidden = true;
    remote.removeAttribute("src");
    video.hidden = true;
    file.value = "";
  });
  cams.addEventListener("change", () => { st.device = cams.value; if (stream) start.click(); });

  // a second opinion: the frame read by the server (ast_ocal), with the tube saved
  analyse.addEventListener("click", async () => {
    const [w, h] = size();
    const grab = document.createElement("canvas");
    grab.width = w;
    grab.height = h;
    grab.getContext("2d").drawImage(media(), 0, 0, w, h);
    verdict.replaceChildren(el("li", "muted", t("col.reading")));
    const blob = await new Promise((r) => grab.toBlob(r, "image/jpeg", 0.92));
    try {
      const r = await call("/v1/aurora/astro/collimation/photo", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: blob });
      verdict.replaceChildren(...(r.error ? [el("li", "warn", r.error)] : r.verdict.map((v) => el("li", "", `${v.ok === true ? "✅" : v.ok === false ? "⚠️" : "ℹ️"} ${v.text}`))));
    } catch (e) { verdict.replaceChildren(el("li", "warn", e.message)); }
  });

  if (navigator.mediaDevices?.enumerateDevices) cameras().catch(() => {});
  mark();
  draw();
  return c;
}

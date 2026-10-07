// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The chat's media and Aurora's own bubbles (moved from chat.js, 7 October 2026: one module per part): a phone photo
// made light before it leaves, this device's microphone recorded, a dream and a good morning among the turns.
import { call } from "../api.js";
import { clock, el, toBase64 } from "../dom.js";
import { t } from "../i18n.js";
import { shareButton } from "../share.js";
import { view } from "../viewer.js";
import * as voice from "../voice.js";

// a phone photo, made light before it leaves: at most 2048 px, upright, JPEG (also from HEIC when the browser reads it)
export async function shrink(file) {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, 2048 / Math.max(bmp.width, bmp.height));
    const cv = document.createElement("canvas");
    cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
    cv.getContext("2d").drawImage(bmp, 0, 0, cv.width, cv.height);
    const blob = await new Promise((ok) => cv.toBlob(ok, "image/jpeg", 0.85));
    return blob ? new File([blob], `foto-${Date.now()}.jpg`, { type: "image/jpeg" }) : file;
  } catch { return file; }
}

// the recorder of this device's microphone, bound to the chat's button and composer (heard: the transcription)
export function makeRecorder({ mic, input, heard, canRecord }) {
  // this device's microphone: tap to start, tap to stop (at most MAX s); WebM/Opus on Android, MP4/AAC on iOS
  const MAX = 30;
  let rec = null;
  const recordHere = async () => {
    if (rec) { rec.stop(); return; }
    if (!canRecord) { input.placeholder = t("chat.src.unsupported"); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
    catch (e) { input.placeholder = t(e.name === "NotAllowedError" ? "chat.src.denied" : "ev.error", { m: e.message }); return; }
    const type = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac"].find((m) => MediaRecorder.isTypeSupported?.(m));
    const chunks = [];
    rec = new MediaRecorder(stream, type ? { mimeType: type } : {});
    rec.ondataavailable = (ev) => { if (ev.data.size) chunks.push(ev.data); };
    // C114: a recording of 0.1 s reached the server twice (the microphone closed at once): said, never sent
    let closed = false;
    stream.getAudioTracks().forEach((tr) => tr.addEventListener("ended", () => { closed = true; }));
    const t0 = performance.now();
    let secs = 0;
    mic.classList.add("recording");
    mic.textContent = "⏹️ 0";
    const tick = setInterval(() => { mic.textContent = `⏹️ ${++secs}`; if (secs >= MAX) rec?.stop(); }, 1000);
    rec.onstop = async () => {
      clearInterval(tick);
      stream.getTracks().forEach((tr) => tr.stop());          // the phone's microphone is released at once
      const mime = rec.mimeType || type || "audio/webm";
      rec = null;
      const took = (performance.now() - t0) / 1000;
      if (closed || took < 0.8) {
        input.placeholder = closed ? t("chat.mic.closed") : t("chat.mic.short", { s: took.toFixed(1) });
        mic.textContent = "🎙️";
        mic.classList.remove("recording");
        return;
      }
      mic.textContent = "…";
      mic.disabled = true;
      try {
        const data = await toBase64(new Blob(chunks, { type: mime }));
        heard(await call("/v1/aurora/senses/transcribe", { method: "POST", body: JSON.stringify({ data, mime }) }));
      } catch (e) { input.placeholder = t("ev.error", { m: e.message }); }
      mic.textContent = "🎙️";
      mic.classList.remove("recording");
      mic.disabled = false;
    };
    rec.start(500);                                // pieces every half second, not only at the stop
  };
  return recordHere;
}

// A dream of the last nights, among the turns: Aurora's own painting and the story.
export function dreamOf(messages, d) {
  const m = el("div", "msg aurora dream past");
  m.append(el("div", "dream-title", t("chat.dream")));
  if (d.image) {
    const img = el("img", "dream-img");
    img.src = d.image;
    img.alt = t("chat.dream_alt");
    img.loading = "lazy";
    if (d.image_prompt) img.title = d.image_prompt;
    img.addEventListener("click", () => view(d.image, img.alt || "sogno.png", "image/png"));
    m.append(img);
  }
  for (const para of d.text.split(/\n\s*\n/)) if (para.trim()) m.append(el("p", "", para.trim()));
  m.append(shareButton(d.text, d.image));
  m.append(el("div", "meta", clock(d.created_at)));
  messages.append(m);
}

// The good morning (kno_morning): what she did and learned overnight, with "listen" (a tap: browsers speak only after one)
// a second thought (kno_review): a past answer answered again, better, with its sources — the same bubble
export function morningOf(messages, d, sayAloud) {
  const m = el("div", `msg aurora dream ${d.role === "review" ? "review" : "morning"} past`);
  m.append(el("div", "dream-title", t(d.role === "review" ? "chat.review" : "chat.morning")));
  for (const para of d.text.split(/\n\s*\n/)) if (para.trim()) m.append(el("p", "", para.trim()));
  const listen = el("button", "", `🔊 ${t("chat.listen")}`);
  listen.type = "button";
  listen.addEventListener("click", async () => {
    if (voice.speaking()) { voice.stop(); return; }
    const msg = await sayAloud(d.text.replace(/^[^\p{L}]+/gmu, ""));
    if (msg) listen.after(el("div", "meta", msg));          // said under the button pressed, not only in the composer
  });
  m.append(listen, el("div", "meta", clock(d.created_at)));
  messages.append(m);
}

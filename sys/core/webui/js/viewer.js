// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// A file opened inside the page: a picture, a PDF, a video. The installed app (PWA) must never open a new window:
// the system browser it would use has no device cookie, and the file would answer "invalid key" (C39, C100).
import { el } from "./dom.js";
import { t } from "./i18n.js";

const kind = (mime, name) => {
  const m = mime || "", n = (name || "").toLowerCase();
  if (m.startsWith("image/") || /\.(png|jpe?g|webp|gif|avif)$/.test(n)) return "image";
  if (m === "application/pdf" || n.endsWith(".pdf")) return "pdf";
  if (m.startsWith("video/") || /\.(mp4|webm|mov)$/.test(n)) return "video";
  return "";
};

export function canView(mime, name) { return kind(mime, name) !== ""; }

export function view(url, name, mime) {
  const k = kind(mime, name);
  const box = el("div", `viewer viewer-${k}`);
  const bar = el("div", "viewer-bar");
  const save = el("a", "viewer-btn", `⬇️ ${t("viewer.save")}`);
  save.href = url;
  save.setAttribute("download", name || "");
  const close = el("button", "viewer-btn", "✕");
  close.type = "button";
  close.title = t("viewer.close");
  bar.append(el("span", "viewer-name", name || ""), save, close);
  let body;
  if (k === "image") { body = el("img"); body.src = url; body.alt = name || ""; }
  else if (k === "video") { body = el("video"); body.src = url; body.controls = true; body.autoplay = true; body.playsInline = true; }
  else { body = el("iframe"); body.src = url; body.title = name || ""; }
  body.classList.add("viewer-body");
  box.append(bar, body);
  const shut = () => { box.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (ev) => { if (ev.key === "Escape") shut(); };
  close.addEventListener("click", shut);
  box.addEventListener("click", (ev) => { if (ev.target === box) shut(); });     // a click outside the file closes
  document.addEventListener("keydown", onKey);
  document.body.append(box);
}

// A link to a file: opens the viewer when the file can be shown, else stays a download (never a new window).
export function viewLink(a, url, name, mime) {
  a.href = url;
  a.removeAttribute("target");
  if (!canView(mime, name)) { a.setAttribute("download", name || ""); return a; }
  a.addEventListener("click", (ev) => { ev.preventDefault(); view(url, name, mime); });
  return a;
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// DOM helpers shared by every module. Server data always goes in as text, never as HTML.
export const $ = (id) => document.getElementById(id);

export function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

export const scrollEnd = (box) => { box.scrollTop = box.scrollHeight; };

export const toBase64 = (file) => new Promise((ok, fail) => {
  const r = new FileReader();
  r.onload = () => ok(r.result.slice(r.result.indexOf(",") + 1));
  r.onerror = () => fail(r.error);
  r.readAsDataURL(file);
});

// Always the full date and time: "30/09/2026 10:31".
export function clock(iso) {
  const d = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
  return `${d.toLocaleDateString([], { day: "2-digit", month: "2-digit", year: "numeric" })} `
    + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// A module's own stylesheet, added once.
export function useCss(href) {
  if (document.querySelector(`link[data-module-css="${href}"]`)) return;
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = href;
  l.dataset.moduleCss = href;
  document.head.append(l);
}

// ⓘ a short explanation of a control (owner, 2026-10-06): on hover with a mouse, on a tap on the phone
export function info(text) {
  const i = el("button", "info-i", "i");
  i.type = "button";
  i.title = text;
  i.setAttribute("aria-label", text);
  i.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const open = i.nextElementSibling?.classList.contains("info-pop");
    document.querySelectorAll(".info-pop").forEach((p) => p.remove());
    if (!open) i.after(el("span", "info-pop", text));
  });
  return i;
}

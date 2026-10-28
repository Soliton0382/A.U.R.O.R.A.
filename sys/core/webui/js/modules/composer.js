// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ✍️ The composer every chat shares (owner, 29 Oct: «uniformiamo le chat in modo che siano come l'app»): a
// <form class="ask"> with its textarea and buttons inside one box (css/composer.css). Enter sends, Shift+Enter a new
// line; files pasted into the text or dropped on the page go to onFiles; the box's height is told to its host as
// --ask-h, so the menus over it (chat_menu.js) open above it however tall it grows.
import { useCss } from "../dom.js";

export function composer({ form, input, onFiles = null, dropOn = null }) {
  useCss("/static/css/composer.css");
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); form.requestSubmit(); }
  });
  if (onFiles) {
    input.addEventListener("paste", (ev) => {
      const files = Array.from(ev.clipboardData?.files || []);
      if (files.length) { ev.preventDefault(); onFiles(files); }
    });
    if (dropOn) {
      dropOn.addEventListener("dragover", (ev) => { ev.preventDefault(); dropOn.classList.add("drop"); });
      dropOn.addEventListener("dragleave", () => dropOn.classList.remove("drop"));
      dropOn.addEventListener("drop", (ev) => { ev.preventDefault(); dropOn.classList.remove("drop"); onFiles(Array.from(ev.dataTransfer.files)); });
    }
  }
  const host = form.parentElement;
  if (host && typeof ResizeObserver === "function") {
    new ResizeObserver(() => host.style.setProperty("--ask-h", `${form.offsetHeight}px`)).observe(form);
  }
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ✍️ The composer every chat shares (owner, 29 Oct: «uniformiamo le chat in modo che siano come l'app»): a
// <form class="ask"> with its textarea and buttons inside one box (css/composer.css). Enter sends, Shift+Enter a new
// line; files pasted into the text or dropped on the page go to onFiles; the box's height is told to its host as
// --ask-h, so the menus over it (chat_menu.js) open above it however tall it grows.
import { useCss } from "../dom.js";
import { call } from "../api.js";

// «/» at the start of a message lists the tools that can be asked for by name (owner, 26 Nov: N158); the automatic
// routing stays the default. Arrows choose, Tab or Enter put the command in, Esc closes.
let commands = null;
async function loadCommands() {
  if (commands) return commands;
  try { commands = (await call(`/v1/aurora/chat/commands?lang=${(navigator.language || "it").slice(0, 2)}`)).commands || []; }
  catch { commands = []; }
  return commands;
}

function slashMenu(form, input) {
  const box = document.createElement("div");
  box.className = "slash-menu";
  box.setAttribute("role", "listbox");
  box.hidden = true;
  form.appendChild(box);
  let shown = [], at = 0;
  const draw = () => {
    box.replaceChildren(...shown.map((c, i) => {
      const row = document.createElement("div");
      row.className = "slash-row" + (i === at ? " on" : "");
      row.setAttribute("role", "option");
      const b = document.createElement("b"); b.textContent = c.cmd;
      const t = document.createElement("span"); t.textContent = " " + c.text;
      const e = document.createElement("small"); e.textContent = c.example;
      row.append(b, t, e);
      row.addEventListener("mousedown", (ev) => { ev.preventDefault(); pick(i); });
      return row;
    }));
    box.hidden = !shown.length;
    box.children[at]?.scrollIntoView({ block: "nearest" });
  };
  const pick = (i) => {
    const c = shown[i]; if (!c) return;
    input.value = c.cmd + " ";
    shown = []; draw(); input.focus();
    input.dispatchEvent(new Event("input", { bubbles: true }));
  };
  input.addEventListener("input", async () => {
    const v = input.value;
    if (!/^\/\S*$/.test(v)) { if (shown.length) { shown = []; draw(); } return; }
    const all = await loadCommands();
    shown = all.filter((c) => c.cmd.startsWith(v.toLowerCase())); at = 0; draw();
  });
  input.addEventListener("keydown", (ev) => {
    if (box.hidden) return;
    if (ev.key === "ArrowDown") { ev.preventDefault(); at = (at + 1) % shown.length; draw(); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); at = (at - 1 + shown.length) % shown.length; draw(); }
    else if (ev.key === "Tab" || ev.key === "Enter") { ev.preventDefault(); ev.stopImmediatePropagation(); pick(at); }
    else if (ev.key === "Escape") { shown = []; draw(); }
  }, true);
}

export function composer({ form, input, onFiles = null, dropOn = null }) {
  useCss("/static/css/composer.css");
  slashMenu(form, input);
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

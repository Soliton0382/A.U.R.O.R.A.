// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🖥️ A terminal in a project's cage (roadmap 75, owner 2026-10-10: the owner's projects are command-line programs, so
// their live preview is running them): no network, only the project's folder; a program that asks for input works.
// Output as Server-Sent Events, keys as POSTs (prj_term); the terminal echoes what is typed, so nothing is echoed here.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const open = new Map();                       // project → terminal id: back to the same terminal on the page again

function clean(text) {                        // a dumb terminal still sends a few escapes: shown as plain text
  return text.replace(/bash: (cannot set terminal process group|no job control)[^\n]*\n/g, "")   // no tty of its own: by design
    .replace(/\x1b\][^\x07]*\x07/g, "").replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "").replace(/\r\n/g, "\n")
    .replace(/\r/g, "");
}

export function terminalView(name) {
  const box = el("div", "prj-term");
  const screen = el("pre", "prj-term-screen");
  const form = el("form", "prj-term-line");
  const input = el("input");
  input.setAttribute("autocomplete", "off");
  input.setAttribute("spellcheck", "false");
  input.placeholder = t("prj.term_ph");
  const send = el("button", "", t("prj.term_send"));
  send.type = "submit";
  const ctrlc = el("button", "", "Ctrl-C");
  ctrlc.type = "button";
  const close = el("button", "", t("prj.term_close"));
  close.type = "button";
  form.append(input, send, ctrlc, close);
  box.append(el("p", "muted", t("prj.term_note")), screen, form);
  let id = open.get(name), es = null, seen = 0;

  const write = (text) => {
    for (const ch of clean(text)) {
      if (ch === "\b") screen.textContent = screen.textContent.slice(0, -1);
      else screen.textContent += ch;
    }
    if (screen.textContent.length > 200000) screen.textContent = screen.textContent.slice(-150000);
    screen.scrollTop = screen.scrollHeight;
  };
  const key = (data) => call(`/v1/aurora/projects/${name}/terminal/${id}/input`, { method: "POST",
    body: JSON.stringify({ data }) }).catch((e) => write(`\n[${e.message}]\n`));
  const listen = () => {
    es?.close();
    es = new EventSource(`/v1/aurora/projects/${name}/terminal/${id}/stream?after=${seen}`);
    es.onmessage = (m) => {
      const d = JSON.parse(m.data);
      if (d.ended) { write(`\n[${t("prj.term_ended")}]\n`); es.close(); open.delete(name); return; }
      seen = d.n;
      write(d.text);
    };
  };
  const start = async () => {
    try {
      if (!id) { id = (await call(`/v1/aurora/projects/${name}/terminal`, { method: "POST", body: "{}" })).id; open.set(name, id); }
      listen();
      input.focus();
    } catch (e) { write(`[${e.message}]\n`); }
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); if (id) key(input.value + "\n"); input.value = ""; });
  ctrlc.addEventListener("click", () => id && key("\x03"));
  close.addEventListener("click", async () => {
    es?.close();
    if (id) await call(`/v1/aurora/projects/${name}/terminal/${id}`, { method: "DELETE" }).catch(() => {});
    open.delete(name);
    id = null;
    write(`\n[${t("prj.term_ended")}]\n`);
  });
  box.stop = () => es?.close();               // leaving the page: the stream stops, the terminal waits (idle limit)
  start();
  return box;
}

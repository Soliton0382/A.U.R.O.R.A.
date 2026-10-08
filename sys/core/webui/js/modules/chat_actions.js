// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Under every message (owner, 2026-10-08): 📋 copy its text, and ↩️ reply to one of Aurora's, as in a messaging app —
// the message goes over the box, quoted, and is sent with the reply: Aurora reads it as the last thing said, with its
// sources, however old (kno_followup.quoted), instead of looking for it in the recent turns.
import { el } from "../dom.js";
import { t } from "../i18n.js";

const QUOTE_SHOWN = 160;          // characters of the quote shown over the box and in the bubble
const QUOTE_SENT = 3000;          // characters sent when the message is not one of Aurora's runs (kno_followup.QUOTE_CUT)

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { /* http or refused: the old way */ }
  const area = el("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.cssText = "position:fixed;opacity:0;top:0;left:0";
  document.body.append(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  area.remove();
  return ok;
}

export const excerpt = (text) => {
  const s = String(text || "").replace(/\s+/g, " ").trim();
  return s.length > QUOTE_SHOWN ? `${s.slice(0, QUOTE_SHOWN)}…` : s;
};

// the row of a message: `reply` only for Aurora's messages
export function actions(root, text, reply = null) {
  if (!text || root.querySelector(":scope > .msg-actions")) return;
  const bar = el("div", "msg-actions");
  const c = el("button", "", "📋");
  c.type = "button";
  c.title = t("chat.copy");
  c.setAttribute("aria-label", c.title);
  c.addEventListener("click", async () => {
    const ok = await copy(text);
    c.textContent = ok ? "✓" : "✗";
    c.title = t(ok ? "chat.copied" : "chat.copy.failed");
    setTimeout(() => { c.textContent = "📋"; c.title = t("chat.copy"); }, 1500);
  });
  bar.append(c);
  if (reply) {
    const r = el("button", "", "↩️");
    r.type = "button";
    r.title = t("chat.reply");
    r.setAttribute("aria-label", r.title);
    r.addEventListener("click", reply);
    bar.append(r);
  }
  root.append(bar);
}

// the quote over the box: set by ↩️, taken by the next message, dropped by ✕
export function quoteBox(box, input) {
  let current = null;
  const draw = () => {
    box.replaceChildren();
    box.classList.toggle("hidden", !current);
    if (!current) return;
    const x = el("button", "x", "✕");
    x.type = "button";
    x.title = t("chat.reply.cancel");
    x.addEventListener("click", () => { current = null; draw(); });
    box.append(el("div", "quote-who", `↩️ ${t("chat.reply.to")}`), el("div", "quote-text", excerpt(current.text)), x);
  };
  draw();
  return {
    set(item) { current = item; draw(); input.focus(); },
    // what goes with the message: the run, which the server reads as she kept it; the text when it is not a run
    take() {
      const q = current;
      current = null;
      draw();
      return q && { run_id: q.run_id || undefined, text: q.text.slice(0, QUOTE_SENT) };
    },
  };
}

// the quote at the top of the owner's bubble
export function quoted(reply) {
  const q = el("div", "quote");
  q.append(el("div", "quote-who", `↩️ ${t("chat.reply.to")}`), el("div", "quote-text", excerpt(reply.text)));
  return q;
}

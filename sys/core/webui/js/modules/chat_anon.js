// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🕶️ The anonymous chat, a page of its own (owner, 2026-10-20: «farei proprio una tab nel menù della chat anonima…
// stessa aurora, niente voce, solo testo, niente file da lei, può eventualmente gestire upload di file»): the same
// Aurora, text only; questions go with "anonymous": true (nothing remembered short or long, no trace, she makes no
// file), files may be attached; the conversation sealed on the server only to be shown again (sys_anon), emptied 24
// hours after its first message or by «Svuota ora».
import { call } from "../api.js";
import { clock, el, scrollEnd, toBase64, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { actions } from "./chat_actions.js";
import { auroraBubble, follow, renderPast } from "./trace.js";

const anonLoad = () => call("/v1/aurora/chat/anon");
const anonClear = () => call("/v1/aurora/chat/anon", { method: "DELETE" });
const anonSave = (turns) => call("/v1/aurora/chat/anon", { method: "POST", body: JSON.stringify({ turns }) })
  .catch(() => null);                                     // not kept: the answer was given all the same

// the line on top: what this chat is, when it empties, and «empty it now»
function banner(expires, onClear) {
  const box = el("div", "anon-banner");
  const when = expires ? new Date(expires * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : null;
  box.append(el("span", "", `🕶️ ${t("chat.anon.banner")}${when ? ` ${t("chat.anon.until", { when })}` : ""}`));
  const clear = el("button", "", `🧹 ${t("chat.anon.clear")}`);
  clear.type = "button";
  clear.addEventListener("click", async () => {
    if (!confirm(t("chat.anon.clear_q"))) return;
    clear.disabled = true;
    try { await anonClear(); } finally { onClear(); }
  });
  box.append(clear);
  return box;
}

export default {
  id: "anonchat",
  icon: "🕶️",
  title: "nav.anonchat",

  mount(root, ctx) {
    useCss("/static/css/chat.css");
    root.classList.add("chat");
    root.innerHTML = `
      <div class="conversation anon">
        <div class="anon-top"></div>
        <div class="messages"></div>
        <div class="chips pending"></div>
        <form class="ask">
          <button type="button" class="icon attach" data-i18n-title="chat.attach">📎</button>
          <input type="file" multiple hidden accept="image/*,video/*,.txt,.md,.markdown,.html,.htm,.pdf">
          <textarea rows="2" data-i18n-placeholder="chat.anon.placeholder"></textarea>
          <button type="submit" class="send" data-i18n="chat.send"></button>
        </form>
      </div>`;
    apply(root);
    this.top = root.querySelector(".anon-top");
    this.messages = root.querySelector(".messages");
    const form = root.querySelector("form"), input = root.querySelector("textarea");
    const fileInput = root.querySelector("input[type=file]"), chips = root.querySelector(".chips.pending");
    const send = root.querySelector(".send");
    let pending = [];
    const drawChips = () => chips.replaceChildren(...pending.map((f, i) => {
      const c = el("span", "chip", `📄 ${f.name} ✕`);
      c.addEventListener("click", () => { pending.splice(i, 1); drawChips(); });
      return c;
    }));
    root.querySelector(".attach").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => { pending.push(...fileInput.files); fileInput.value = ""; drawChips(); });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const question = input.value.trim(), files = pending;
      if (!question && !files.length) return;
      send.disabled = true;
      input.value = "";
      pending = [];
      drawChips();
      this.userBubble(question, files.map((f) => f.name));
      const b = auroraBubble(this.messages);
      scrollEnd(this.messages);
      try {
        const attachments = await Promise.all(files.map(async (f) => ({ name: f.name, mime: f.type, data: await toBase64(f) })));
        const { run_id } = await call("/v1/aurora/ask", { method: "POST",
          body: JSON.stringify({ question, attachments, anonymous: true }) });
        const final = await follow(run_id, b, this.messages);
        if (final?.text) {
          actions(b.root, final.text);                   // 📋 only: no voice here
          const at = new Date().toISOString();
          await anonSave([{ role: "user", text: question, created_at: at }, { role: "aurora", text: final.text, created_at: at }]);
          this.drawTop();
        }
      } catch (e) {
        b.body.replaceChildren(el("p", "error", t("ev.error", { m: e.message })));
        if (e.status === 401) ctx.relogin();
      } finally { send.disabled = false; input.focus(); }
    });
  },

  userBubble(text, names = [], when) {
    const m = el("div", "msg user");
    if (text) m.append(el("p", "", text));
    if (names.length) m.append(el("div", "chips", names.map((n) => `📄 ${n}`).join("  ")));
    m.append(el("div", "meta", clock(when || new Date().toISOString())));
    this.messages.append(m);
  },

  async drawTop() {
    let d = { expires: null };
    try { d = await anonLoad(); } catch { /* none yet */ }
    this.top.replaceChildren(banner(d.expires, () => this.enter()));
    return d;
  },

  async enter() {
    const d = await this.drawTop();
    this.messages.replaceChildren();
    for (const turn of d.turns || []) {
      if (turn.role === "user") { this.userBubble(turn.text, [], turn.created_at); continue; }
      const b = auroraBubble(this.messages);
      renderPast(b, turn);
      actions(b.root, turn.text);
      b.root.classList.add("past");
    }
    if (!(d.turns || []).length) this.messages.append(el("p", "muted anon-empty", t("chat.anon.hint")));
    scrollEnd(this.messages);
  },
};

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The conversation: history on load, composer with attachments, live answers.
import { call, stream } from "../api.js";
import { bus } from "../bus.js";
import { clock, el, scrollEnd, toBase64, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { auroraBubble, follow, renderPast } from "./trace.js";
import { viewLink } from "../viewer.js";
import * as voice from "../voice.js";
import { dietBubbles, dietCards } from "../diet.js";
import { dreamOf, makeRecorder, morningOf, shrink } from "./chat_media.js";
import { thinkMode } from "./chat_think.js";
import { attachMenu, settingsMenu, showGear, source } from "./chat_menu.js";
import { actions, quoteBox, quoted } from "./chat_actions.js";

const HISTORY_TURNS = 8;          // 4 exchanges: the same memory Aurora keeps in context

// A file of a message: one just chosen (a File) or one kept by Aurora ({name, mime, url}, from the history).
function chip(file) {
  const type = file.type || file.mime || "";
  const kept = !(file instanceof Blob);
  const c = el(kept ? "a" : "span", "chip");
  if (kept) viewLink(c, file.url, file.name, type);         // inside the page: the PWA has no cookie in a new window
  if (type.startsWith("image/") && (!kept || file.inline)) {
    const img = el("img");
    img.src = kept ? file.url : URL.createObjectURL(file);
    img.loading = "lazy";
    c.append(img);
  } else c.append(el("span", "", type.startsWith("video/") ? "🎬" : type.startsWith("audio/") ? "🎧" : "📄"));
  c.append(el("span", "", file.name));
  return c;
}

export default {
  id: "chat",
  icon: "💬",
  title: "nav.chat",

  mount(root, ctx) {
    useCss("/static/css/chat.css");
    root.classList.add("chat");
    root.innerHTML = `
      <div class="conversation">
        <div class="messages"></div>
        <div class="chips pending"></div>
        <div class="quote-box hidden"></div>
        <form class="ask">
          <button type="button" class="icon attach" data-i18n-title="chat.attach">📎</button>
          <button type="button" class="icon mic" data-i18n-title="chat.mic">🎙️</button>
          <button type="button" class="icon gear">⚙️</button>
          <button type="button" class="icon hush hidden" data-i18n-title="chat.hush">⏹️</button>
          <input type="file" multiple hidden accept="image/*,video/*,.txt,.md,.markdown,.html,.htm,.pdf">
          <input type="file" class="shoot" hidden accept="image/*" capture="environment">
          <textarea rows="2" data-i18n-placeholder="chat.placeholder"></textarea>
          <button type="submit" class="send" data-i18n="chat.send"></button>
        </form>
      </div>`;
    apply(root);
    const conv = root.querySelector(".conversation");
    const messages = root.querySelector(".messages");
    const form = root.querySelector("form");
    const input = root.querySelector("textarea");
    const fileInput = root.querySelector("input[type=file]:not(.shoot)");
    const send = root.querySelector(".send");
    const chipsBox = root.querySelector(".chips.pending");
    const thinking = thinkMode;                                    // how much to think (chat_think.js, in ⚙️)
    const gear = root.querySelector(".gear");
    showGear(gear);
    gear.addEventListener("click", () => {
      if (conv.querySelector(".compose-menu")) { conv.querySelector(".compose-menu").remove(); return; }
      settingsMenu(conv, gear);
    });
    const quote = quoteBox(root.querySelector(".quote-box"), input);       // ↩️ the message replied to
    const replyTo = (text, runId) => () => quote.set({ text, run_id: runId });
    let pending = [];
    const mine = new Set();          // runs started from this page: the activity feed must not show them twice
    let asking = 0;                  // requests in flight whose run id is not known yet

    const renderChips = () => chipsBox.replaceChildren(...pending.map((f, i) => {
      const c = chip(f);
      const x = el("button", "x", "×");
      x.type = "button";
      x.addEventListener("click", () => { pending.splice(i, 1); renderChips(); });
      c.append(x);
      return c;
    }));
    const addFiles = (list) => { pending.push(...Array.from(list)); renderChips(); };

    // Camera and microphone: of this device (the phone's, through the browser) or of Aurora's machine (plugin
    // "senses"), chosen in ⚙️ (chat_menu.js). A touch screen starts on this device, a PC on the machine.
    // The owner's click is the consent; the browser asks its own permission the first time.
    const mic = root.querySelector(".mic");
    const shoot = root.querySelector(".shoot");
    const canRecord = !!(window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder);

    shoot.addEventListener("change", async () => {
      const f = shoot.files?.[0];
      shoot.value = "";
      if (f) addFiles([await shrink(f)]);
    });
    const takePhoto = async () => {
      if (source() === "device") { shoot.click(); return; }
      try {
        const r = await call("/v1/aurora/senses/photo", { method: "POST", body: "{}" });
        const bytes = Uint8Array.from(atob(r.data), (c) => c.charCodeAt(0));
        addFiles([new File([bytes], r.name, { type: r.mime })]);
      } catch (e) { input.placeholder = t("ev.error", { m: e.message }); }
    };
    root.querySelector(".attach").addEventListener("click", () => {
      if (conv.querySelector(".compose-menu")) { conv.querySelector(".compose-menu").remove(); return; }
      attachMenu(conv, { file: () => fileInput.click(), shoot: takePhoto });
    });

    // Answers aloud (voice.js; when the owner spoke, always or off, chosen in ⚙️): ⏹️ shows while she speaks
    let spoken = false;                              // the message in the box was dictated
    const hush = root.querySelector(".hush");
    let hushTimer = null;
    const watchVoice = () => {
      clearInterval(hushTimer);
      hush.classList.remove("hidden");
      let quiet = 0;                                 // a few checks before hiding: the voice may still be on its way
      hushTimer = setInterval(() => {
        quiet = voice.speaking() ? 0 : quiet + 1;
        if (quiet >= 6) { clearInterval(hushTimer); hush.classList.add("hidden"); }
      }, 500);
    };
    hush.addEventListener("click", () => { voice.stop(); clearInterval(hushTimer); hush.classList.add("hidden"); });
    const sayAloud = async (text) => {
      watchVoice();
      const r = await voice.speak(text, lang.replace("_", "-"));
      if (r === "unplayable") {                     // not a permission: the browser's own reason, by its name
        const msg = t("chat.voice.unplayable", { e: voice.unplayable });
        input.placeholder = msg;
        return msg;
      }
      if (r === "blocked" || r === "server" || r === "offline") {   // the true reason (C177), not «only online voices»
        const msg = t(r === "server" ? "chat.voice.server_error" : `chat.voice.${r}`);
        input.placeholder = msg;
        return msg;
      }
      if (r === "novoice") {                       // said where it shows, and why: only online voices, or none
        const msg = t(`chat.voice.novoice.${await voice.why(lang.replace("_", "-"))}`);
        input.placeholder = msg;
        return msg;
      }
      return "";
    };

    const heard = (r) => {
      if (r.clear) spoken = true;
      if (r.clear) input.value = (input.value ? input.value + " " : "") + r.text;
      else input.placeholder = t("chat.mic.none");
      if (r.clear) { form.requestSubmit(); return; }   // hands-free: what was dictated goes, the answer comes aloud
      input.focus();
    };
    const recordHere = makeRecorder({ mic, input, heard, canRecord });     // chat_media.js
    mic.addEventListener("click", async () => {
      if (source() === "device") { recordHere(); return; }
      const seconds = 8;
      mic.disabled = true;
      mic.classList.add("recording");
      let left = seconds;
      const tick = setInterval(() => { mic.textContent = `🔴 ${--left > 0 ? left : "…"}`; }, 1000);
      mic.textContent = `🔴 ${left}`;
      try {
        heard(await call("/v1/aurora/senses/listen", { method: "POST", body: JSON.stringify({ seconds }) }));
      } catch (e) { input.placeholder = t("ev.error", { m: e.message }); }
      clearInterval(tick);
      mic.textContent = "🎙️";
      mic.classList.remove("recording");
      mic.disabled = false;
    });
    fileInput.addEventListener("change", () => { addFiles(fileInput.files); fileInput.value = ""; });
    input.addEventListener("paste", (ev) => {
      const files = Array.from(ev.clipboardData?.files || []);
      if (files.length) { ev.preventDefault(); addFiles(files); }
    });
    conv.addEventListener("dragover", (ev) => { ev.preventDefault(); conv.classList.add("drop"); });
    conv.addEventListener("dragleave", () => conv.classList.remove("drop"));
    conv.addEventListener("drop", (ev) => { ev.preventDefault(); conv.classList.remove("drop"); addFiles(ev.dataTransfer.files); });
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
    });

    const userBubble = (text, files = [], when, reply = null) => {
      const m = el("div", "msg user");
      if (reply?.text) m.append(quoted(reply));
      if (files.length) { const row = el("div", "chips"); row.append(...files.map(chip)); m.append(row); }
      if (text) m.append(el("div", "", text));
      m.append(el("div", "meta", clock(when || new Date().toISOString())));
      actions(m, text);
      messages.append(m);
    };

    const dreamBubble = (d) => { dreamOf(messages, d); actions(messages.lastElementChild, d.text, replyTo(d.text)); };    // chat_media.js
    const morningBubble = (d) => { morningOf(messages, d, sayAloud); actions(messages.lastElementChild, d.text, replyTo(d.text)); };   // chat_media.js

    // Questions to go deeper, under a knowledge answer: complete on their own, each with the answer's sources
    // in focus (kno_followup), so a click searches the right way; the owner sees the whole question sent.
    let nextFocus = null;
    const offerDeeper = (b, items) => {
      const row = el("div", "deeper");
      row.append(el("div", "meta", t("chat.deeper")));
      for (const it of items) {
        const go = el("button", "deeper-q", `🔎 ${it.question}`);
        go.type = "button";
        go.addEventListener("click", () => {
          if (send.disabled) return;
          row.remove();
          nextFocus = it.focus || [];
          input.value = it.question;
          form.requestSubmit();
        });
        row.append(go);
      }
      b.body.append(row);
    };

    const offerAcquire = (b, question) => {
      // Searching outside is an external action: it starts only from the owner's click.
      const go = el("button", "", `🛰️ ${t("chat.acquire")}`);
      go.addEventListener("click", async () => {
        go.remove();
        send.disabled = true;
        b.steps.append(el("hr"));
        try {
          asking++;
          const { run_id } = await call("/v1/aurora/acquire", { method: "POST", body: JSON.stringify({ question }) }).finally(() => asking--);
          mine.add(run_id);
          await follow(run_id, b, messages);
        } catch (e) {
          b.body.append(el("p", "error", t("ev.error", { m: e.message })));
        } finally { send.disabled = false; }
      });
      b.body.append(go);
    };

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const question = input.value.trim();
      const files = pending;
      const focus = nextFocus;
      nextFocus = null;
      const aloud = voice.mode() === "always" || (voice.mode() === "voice" && spoken);
      spoken = false;
      if (aloud) voice.unlock();                     // during the owner's tap: some phones speak only after one
      else voice.stop();
      if (!question && !files.length) return;
      send.disabled = true;
      input.value = "";
      pending = [];
      renderChips();
      const reply = quote.take();
      userBubble(question, files, undefined, reply);
      const b = auroraBubble(messages);
      scrollEnd(messages);
      try {
        const attachments = await Promise.all(files.map(async (f) => ({ name: f.name, mime: f.type, data: await toBase64(f) })));
        asking++;
        // "/agente <goal>" (or "/agent"): an agent works on the goal with its tools
        const goal = question.match(/^\/agen(?:te|t)\s+(.+)/s)?.[1];
        const { run_id } = await (goal
          ? call("/v1/aurora/agent", { method: "POST", body: JSON.stringify({ goal }) })
          : call("/v1/aurora/ask", { method: "POST", body: JSON.stringify({ question, attachments, suggest: true, ...(focus ? { focus } : {}), ...(reply ? { reply_to: reply } : {}), ...(thinking() ? { think: thinking() } : {}) }) })
        ).finally(() => asking--);
        mine.add(run_id);
        const final = await follow(run_id, b, messages);
        if (final?.text) actions(b.root, final.text, replyTo(final.text, run_id));
        if (aloud && final?.text) sayAloud(final.text);
        if (final?.diet) await dietCards(b, final.diet);
        if (final?.abstained && final.mode !== "self") offerAcquire(b, question);
        else if (final?.suggestions?.length) { const stick = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 120; offerDeeper(b, final.suggestions); if (stick) scrollEnd(messages); }
      } catch (e) {
        b.body.replaceChildren(el("p", "error", t("ev.error", { m: e.message })));
        b.head.classList.remove("running");
        if (e.status === 401) ctx.relogin();
      } finally {
        send.disabled = false;
        input.focus();
      }
    });

    // Another page asks Aurora something (e.g. "review this project"): it goes out as if typed here.
    bus.on("ask", async ({ text }) => { await ctx.show("chat"); input.value = text; form.requestSubmit(); });

    // The latest turns from Aurora's memory: a refresh does not start from an empty page.
    const shown = new Set();                           // the turns on screen (their sid): a catch-up adds only the others
    const renderTurn = (turn) => {
      shown.add(turn.sid);
      if (turn.role === "user") { userBubble(turn.text, turn.attachments || [], turn.created_at, turn.reply_to); return; }
      if (turn.role === "dream") { dreamBubble(turn); return; }
      if (turn.role === "morning" || turn.role === "review") { morningBubble(turn); return; }
      const b = auroraBubble(messages);
      renderPast(b, turn);
      actions(b.root, turn.text, replyTo(turn.text, turn.run_id));
      if (turn.suggestions?.length) offerDeeper(b, turn.suggestions);
      b.root.classList.add("past");
      if (turn.run_id) mine.add(turn.run_id);
    };
    // back on the page (the app was asleep, the stream lost): what happened meanwhile on other devices (owner, 2026-10-06)
    this.catchUp = async () => {
      let turns;
      try { turns = await call(`/v1/aurora/history?n=${HISTORY_TURNS}`); } catch { return; }
      const fresh = turns.filter((x) => !shown.has(x.sid) && !(x.run_id && mine.has(x.run_id) && x.role !== "user"));
      const live = new Set(turns.filter((x) => x.run_id && mine.has(x.run_id)).map((x) => x.run_id));
      const add = fresh.filter((x) => !(x.role === "user" && live.has(x.run_id)));     // a question followed live: shown
      dietBubbles(messages);
      if (!add.length) return;
      const stick = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
      add.forEach(renderTurn);
      if (stick) scrollEnd(messages);
    };
    this.loadHistory = async () => {
      const turns = await call(`/v1/aurora/history?n=${HISTORY_TURNS}`);
      messages.replaceChildren();
      shown.clear();
      for (const turn of turns) {
        shown.add(turn.sid);
        if (turn.role === "user") { userBubble(turn.text, turn.attachments || [], turn.created_at, turn.reply_to); continue; }
        if (turn.role === "dream") { dreamBubble(turn); continue; }
        if (turn.role === "morning" || turn.role === "review") { morningBubble(turn); continue; }
        const b = auroraBubble(messages);
        renderPast(b, turn);
        actions(b.root, turn.text, replyTo(turn.text, turn.run_id));
        if (turn.suggestions?.length) offerDeeper(b, turn.suggestions);   // under every answer that has them (owner, 2026-10-05)
        b.root.classList.add("past");
        if (turn.run_id) mine.add(turn.run_id);
      }
      const n = turns.filter((x) => !["dream", "morning", "review"].includes(x.role)).length;
      if (n) messages.append(el("div", "divider", t("chat.history", { n })));
      await dietBubbles(messages);                    // a meal reminded and not answered yet
      scrollEnd(messages);
    };
    this.replay = async (run) => {
      userBubble(run.question, [], new Date(run.started * 1000).toISOString());
      await follow(run.id, auroraBubble(messages), messages);
    };

    // ---- what happens elsewhere: conversations from other devices and clients ----------------
    // The chat stays a chat: Aurora's autonomous work (REM, agents, approvals, harvester) lives in
    // Repairs, Diary and Activity, and the bell in the top bar says when something waits for the owner.
    const onActivity = async (a) => {
      if (["rem.review", "rem.morning", "rem.dream"].includes(a.event)) { this.catchUp(); return; }   // written while the page is open
      if (a.event === "diet.meal") { await dietBubbles(messages); scrollEnd(messages); return; }       // 🍽️ the meal of now
      if (a.event !== "run.begin" || !["webui", "openai", "acquire"].includes(a.payload.origin)) return;
      const id = a.payload.run_id;
      if (asking) await new Promise((ok) => setTimeout(ok, 800));      // maybe it is ours: its id is on the way
      if (mine.has(id)) return;
      mine.add(id);
      const stick = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
      userBubble(`${a.payload.question}`, [], new Date(a.ts * 1000).toISOString());
      const b = auroraBubble(messages);
      if (a.payload.origin !== "webui") b.root.classList.add("elsewhere");
      if (stick) scrollEnd(messages);
      const final = await follow(id, b, messages);
      if (final?.text) actions(b.root, final.text, replyTo(final.text, id));
      if (final?.diet) await dietCards(b, final.diet);
      if (final?.suggestions?.length) offerDeeper(b, final.suggestions);   // asked on another device: go deeper here too
    };
    let lastSeq = 0;
    this.watch = async () => {
      for (;;) {
        // reconnected after a sleep or a restart: from the last item seen, so nothing in between is lost
        try { await stream(`/v1/aurora/activity/stream${lastSeq ? `?after=${lastSeq}` : ""}`, (a) => { lastSeq = a.seq || lastSeq; onActivity(a); }); }
        catch (e) { if (e.status === 401) return; }
        this.catchUp();
        await new Promise((ok) => setTimeout(ok, 5000));               // reconnect after a restart of the API
      }
    };
    document.addEventListener("visibilitychange", () => { if (!document.hidden && this.loaded) this.catchUp(); });
    // 🎬 a video in progress (owner, 2026-10-06: pictures had their steps, videos nothing): a bar over the conversation,
    // the time gone over the time estimated — said as an estimate
    const bar = el("div", "video-progress hidden");
    messages.before(bar);
    const videoTick = async () => {
      if (document.hidden) return;
      let v;
      try { v = await call("/v1/aurora/video/status"); } catch { return; }
      bar.classList.toggle("hidden", !v.busy);
      if (!v.busy) return;
      const at = new Date(v.ready_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const fill = el("div", "video-fill"); fill.style.width = `${v.percent}%`;
      const track = el("div", "video-track"); track.append(fill);
      bar.replaceChildren(el("div", "", t("chat.video_progress", { title: v.title, p: v.percent, at })), track);
    };
    videoTick();
    setInterval(videoTick, 15000);
  },

  async enter() {
    // once: coming back from another page must not wipe the messages being followed
    if (!this.loaded) { await this.loadHistory(); this.loaded = true; }
    if (!this.watching) { this.watching = true; this.watch(); }
  },
};

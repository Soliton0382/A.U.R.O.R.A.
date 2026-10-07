// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The conversation: history on load, composer with attachments, live answers.
import { call, stream } from "../api.js";
import { bus } from "../bus.js";
import { clock, el, scrollEnd, toBase64, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { auroraBubble, follow, renderPast } from "./trace.js";
import { shareButton } from "../share.js";
import { view, viewLink } from "../viewer.js";
import * as voice from "../voice.js";

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
        <form class="ask">
          <button type="button" class="icon attach" data-i18n-title="chat.attach">📎</button>
          <button type="button" class="icon cam" data-i18n-title="chat.camera">📷</button>
          <button type="button" class="icon mic" data-i18n-title="chat.mic">🎙️</button>
          <button type="button" class="icon src"></button>
          <button type="button" class="icon voice"></button>
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

    root.querySelector(".attach").addEventListener("click", () => fileInput.click());
    // Camera and microphone: of this device (the phone's, through the browser) or of Aurora's machine (plugin
    // "senses"). A touch screen starts on this device, a PC on the machine; the owner's choice is remembered.
    // The owner's click is the consent; the browser asks its own permission the first time.
    const cam = root.querySelector(".cam");
    const mic = root.querySelector(".mic");
    const srcBtn = root.querySelector(".src");
    const shoot = root.querySelector(".shoot");
    const canRecord = !!(window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
    let source = "pc";
    try { source = localStorage.getItem("aurora.senses.source") || ""; } catch { /* storage unavailable */ }
    if (source !== "device" && source !== "pc") source = matchMedia("(pointer: coarse)").matches ? "device" : "pc";
    const showSource = () => {
      srcBtn.textContent = source === "device" ? "📱" : "🖥️";
      srcBtn.title = t(source === "device" ? "chat.src.device" : "chat.src.pc");
    };
    showSource();
    srcBtn.addEventListener("click", () => {
      source = source === "device" ? "pc" : "device";
      try { localStorage.setItem("aurora.senses.source", source); } catch { /* storage unavailable */ }
      showSource();
    });

    // a phone photo, made light before it leaves: at most 2048 px, upright, JPEG (also from HEIC when the browser reads it)
    const shrink = async (file) => {
      try {
        const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
        const k = Math.min(1, 2048 / Math.max(bmp.width, bmp.height));
        const cv = document.createElement("canvas");
        cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
        cv.getContext("2d").drawImage(bmp, 0, 0, cv.width, cv.height);
        const blob = await new Promise((ok) => cv.toBlob(ok, "image/jpeg", 0.85));
        return blob ? new File([blob], `foto-${Date.now()}.jpg`, { type: "image/jpeg" }) : file;
      } catch { return file; }
    };
    shoot.addEventListener("change", async () => {
      const f = shoot.files?.[0];
      shoot.value = "";
      if (f) addFiles([await shrink(f)]);
    });
    cam.addEventListener("click", async () => {
      if (source === "device") { shoot.click(); return; }
      cam.disabled = true;
      try {
        const r = await call("/v1/aurora/senses/photo", { method: "POST", body: "{}" });
        const bytes = Uint8Array.from(atob(r.data), (c) => c.charCodeAt(0));
        addFiles([new File([bytes], r.name, { type: r.mime })]);
      } catch (e) { input.placeholder = t("ev.error", { m: e.message }); }
      cam.disabled = false;
    });

    // Answers aloud (voice.js): off, when the owner spoke (the default), always; the device's own voices only.
    const voiceBtn = root.querySelector(".voice");
    let spoken = false;                              // the message in the box was dictated
    const showVoice = () => {
      const m = voice.mode();
      voiceBtn.textContent = m === "off" ? "🔇" : m === "always" ? "🔊" : "🗣️";
      voiceBtn.title = t(`chat.voice.${m}`);
    };
    if (voice.supported()) showVoice(); else voiceBtn.hidden = true;
    // a long press on the button: the device's own voices, each with ▶ to hear it; the choice stays on this device
    let pressTimer = null, longPress = false;
    const pickVoice = async () => {
      const code = lang.replace("_", "-");
      const [list, server] = await Promise.all([voice.localVoices(code), voice.serverAvailable(code)]);
      const box = el("div", "voice-pick");
      box.append(el("div", "meta", list.length || server ? t("chat.voice.pick") : t(`chat.voice.novoice.${await voice.why(code)}`)));
      if (server) {                                   // Aurora's own voice (Piper on her machine): on every device
        const row = el("div", "voice-row");
        const pick = el("button", voice.chosen() === voice.SERVER || !voice.chosen() ? "on" : "", `🌸 ${t("chat.voice.server")}`);
        const play = el("button", "", "▶");
        pick.type = play.type = "button";
        pick.addEventListener("click", () => { voice.choose(voice.SERVER); box.remove(); });
        play.addEventListener("click", () => voice.speakServer(t("chat.voice.sample"), code));
        row.append(play, pick);
        box.append(row);
      }
      for (const vo of list) {
        const row = el("div", "voice-row");
        const pick = el("button", vo.name === voice.chosen() || (!voice.chosen() && !server && vo === list[0]) ? "on" : "", vo.name);
        const play = el("button", "", "▶");
        pick.type = play.type = "button";
        pick.addEventListener("click", () => { voice.choose(vo.name); box.remove(); });
        play.addEventListener("click", () => voice.speak(t("chat.voice.sample"), vo.lang, vo));
        row.append(play, pick);
        box.append(row);
      }
      const close = el("button", "", "✕");
      close.type = "button";
      close.addEventListener("click", () => box.remove());
      box.append(close);
      root.querySelector(".conversation").append(box);
    };
    voiceBtn.addEventListener("pointerdown", () => { longPress = false; pressTimer = setTimeout(() => { longPress = true; pickVoice(); }, 600); });
    for (const evName of ["pointerup", "pointerleave", "pointercancel"]) voiceBtn.addEventListener(evName, () => clearTimeout(pressTimer));
    voiceBtn.addEventListener("contextmenu", (ev) => ev.preventDefault());
    voiceBtn.addEventListener("click", () => {
      if (longPress) { longPress = false; return; }
      if (voice.speaking()) { voice.stop(); return; }            // a tap while she speaks: silence
      voice.nextMode();
      showVoice();
    });
    const sayAloud = async (text) => {
      const r = await voice.speak(text, lang.replace("_", "-"));
      if (r === "blocked" || r === "server" || r === "offline") {   // the true reason (C177), not «only online voices»
        const msg = t(`chat.voice.${r}`);
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
    mic.addEventListener("click", async () => {
      if (source === "device") { recordHere(); return; }
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

    const userBubble = (text, files = [], when) => {
      const m = el("div", "msg user");
      if (files.length) { const row = el("div", "chips"); row.append(...files.map(chip)); m.append(row); }
      if (text) m.append(el("div", "", text));
      m.append(el("div", "meta", clock(when || new Date().toISOString())));
      messages.append(m);
    };

    // A dream of the last nights, among the turns: Aurora's own painting and the story.
    const dreamBubble = (d) => {
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
    };

    // The good morning (kno_morning): what she did and learned overnight, with "listen" (a tap: browsers speak only after one)
    // a second thought (kno_review): a past answer answered again, better, with its sources — the same bubble
    const morningBubble = (d) => {
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
    };

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
      userBubble(question, files);
      const b = auroraBubble(messages);
      scrollEnd(messages);
      try {
        const attachments = await Promise.all(files.map(async (f) => ({ name: f.name, mime: f.type, data: await toBase64(f) })));
        asking++;
        // "/agente <goal>" (or "/agent"): an agent works on the goal with its tools
        const goal = question.match(/^\/agen(?:te|t)\s+(.+)/s)?.[1];
        const { run_id } = await (goal
          ? call("/v1/aurora/agent", { method: "POST", body: JSON.stringify({ goal }) })
          : call("/v1/aurora/ask", { method: "POST", body: JSON.stringify({ question, attachments, suggest: true, ...(focus ? { focus } : {}) }) })
        ).finally(() => asking--);
        mine.add(run_id);
        const final = await follow(run_id, b, messages);
        if (aloud && final?.text) sayAloud(final.text);
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
      if (turn.role === "user") { userBubble(turn.text, turn.attachments || [], turn.created_at); return; }
      if (turn.role === "dream") { dreamBubble(turn); return; }
      if (turn.role === "morning" || turn.role === "review") { morningBubble(turn); return; }
      const b = auroraBubble(messages);
      renderPast(b, turn);
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
        if (turn.role === "user") { userBubble(turn.text, turn.attachments || [], turn.created_at); continue; }
        if (turn.role === "dream") { dreamBubble(turn); continue; }
        if (turn.role === "morning" || turn.role === "review") { morningBubble(turn); continue; }
        const b = auroraBubble(messages);
        renderPast(b, turn);
        if (turn.suggestions?.length) offerDeeper(b, turn.suggestions);   // under every answer that has them (owner, 2026-10-05)
        b.root.classList.add("past");
        if (turn.run_id) mine.add(turn.run_id);
      }
      const n = turns.filter((x) => !["dream", "morning", "review"].includes(x.role)).length;
      if (n) messages.append(el("div", "divider", t("chat.history", { n })));
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

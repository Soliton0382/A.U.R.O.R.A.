// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The conversation: history on load, composer with attachments, live answers.
import { call, stream } from "../api.js";
import { bus } from "../bus.js";
import { clock, el, scrollEnd, toBase64, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";
import { auroraBubble, follow, renderPast } from "./trace.js";

const HISTORY_TURNS = 8;          // 4 exchanges: the same memory Aurora keeps in context

// A file of a message: one just chosen (a File) or one kept by Aurora ({name, mime, url}, from the history).
function chip(file) {
  const type = file.type || file.mime || "";
  const kept = !(file instanceof Blob);
  const c = el(kept ? "a" : "span", "chip");
  if (kept) { c.href = file.url; c.target = "_blank"; c.rel = "noopener"; }
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

    const heard = (r) => {
      if (r.clear) input.value = (input.value ? input.value + " " : "") + r.text;
      else input.placeholder = t("chat.mic.none");
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
      let secs = 0;
      mic.classList.add("recording");
      mic.textContent = "⏹️ 0";
      const tick = setInterval(() => { mic.textContent = `⏹️ ${++secs}`; if (secs >= MAX) rec?.stop(); }, 1000);
      rec.onstop = async () => {
        clearInterval(tick);
        stream.getTracks().forEach((tr) => tr.stop());          // the phone's microphone is released at once
        const mime = rec.mimeType || type || "audio/webm";
        rec = null;
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
      rec.start();
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

    // Full-size view inside the page: a standalone PWA would open a new window in the system browser,
    // which has no device cookie (401).
    const lightbox = (src, alt) => {
      const box = el("div", "lightbox");
      const img = el("img");
      img.src = src;
      img.alt = alt;
      box.append(img);
      const close = () => { box.remove(); document.removeEventListener("keydown", onKey); };
      const onKey = (ev) => { if (ev.key === "Escape") close(); };
      box.addEventListener("click", close);
      document.addEventListener("keydown", onKey);
      document.body.append(box);
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
        img.addEventListener("click", () => lightbox(d.image, img.alt));
        m.append(img);
      }
      for (const para of d.text.split(/\n\s*\n/)) if (para.trim()) m.append(el("p", "", para.trim()));
      m.append(el("div", "meta", clock(d.created_at)));
      messages.append(m);
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
          : call("/v1/aurora/ask", { method: "POST", body: JSON.stringify({ question, attachments }) })
        ).finally(() => asking--);
        mine.add(run_id);
        const final = await follow(run_id, b, messages);
        if (final?.abstained && final.mode !== "self") offerAcquire(b, question);
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
    this.loadHistory = async () => {
      const turns = await call(`/v1/aurora/history?n=${HISTORY_TURNS}`);
      messages.replaceChildren();
      for (const turn of turns) {
        if (turn.role === "user") { userBubble(turn.text, turn.attachments || [], turn.created_at); continue; }
        if (turn.role === "dream") { dreamBubble(turn); continue; }
        const b = auroraBubble(messages);
        renderPast(b, turn);
        b.root.classList.add("past");
        if (turn.run_id) mine.add(turn.run_id);
      }
      const n = turns.filter((x) => x.role !== "dream").length;
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
      await follow(id, b, messages);
    };
    this.watch = async () => {
      for (;;) {
        try { await stream("/v1/aurora/activity/stream", (a) => { onActivity(a); }); }
        catch (e) { if (e.status === 401) return; }
        await new Promise((ok) => setTimeout(ok, 5000));               // reconnect after a restart of the API
      }
    };
  },

  async enter() {
    // once: coming back from another page must not wipe the messages being followed
    if (!this.loaded) { await this.loadHistory(); this.loaded = true; }
    if (!this.watching) { this.watching = true; this.watch(); }
  },
};

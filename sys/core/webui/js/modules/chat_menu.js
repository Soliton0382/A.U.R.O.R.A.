// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The composer's buttons as menus with their words (owner, 2026-10-08: «le icone cominciano ad essere tante... li
// gestirei come il menù vero e proprio»): 📎 a file or a photo; ⚙️ how much Aurora thinks (🧠), whose camera and
// microphone (📱 this device, 🖥️ Aurora's PC), answers aloud (🔊) and the voice. Every choice stays on this device.
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";
import * as voice from "../voice.js";
import { THINK, THINK_ICON, setThink, thinkMode } from "./chat_think.js";

const SRC_KEY = "aurora.senses.source";
const VOICE_ICON = { voice: "🗣️", always: "🔊", off: "🔇" };

// a panel over the composer, closed by ✕, by a tap outside it or by opening another
function panel(host, title) {
  host.querySelector(".compose-menu")?.remove();
  const box = el("div", "compose-menu");
  const close = el("button", "icon close", "✕");
  close.type = "button";
  close.addEventListener("click", () => box.remove());
  const head = el("div", "compose-head");
  head.append(el("strong", "", title), close);
  box.append(head);
  host.append(box);
  const outside = (ev) => {
    if (!box.isConnected) { document.removeEventListener("pointerdown", outside, true); return; }
    if (!box.contains(ev.target) && !ev.target.closest?.(".ask .icon")) { box.remove(); document.removeEventListener("pointerdown", outside, true); }
  };
  setTimeout(() => document.addEventListener("pointerdown", outside, true));
  return box;
}

// one row of a menu: the icon, the words, a line that says what it does; marked when it is the current choice
function row(icon, label, hint, on, click) {
  const b = el("button", `compose-row${on ? " on" : ""}`);
  b.type = "button";
  b.append(el("span", "ico", icon));
  const words = el("span", "words");
  words.append(el("span", "", label));
  if (hint) words.append(el("span", "hint", hint));
  b.append(words);
  if (on) b.append(el("span", "tick", "✓"));
  b.addEventListener("click", click);
  return b;
}

export function source() {
  let s = "";
  try { s = localStorage.getItem(SRC_KEY) || ""; } catch { /* storage unavailable */ }
  return s === "device" || s === "pc" ? s : matchMedia("(pointer: coarse)").matches ? "device" : "pc";
}

// 📎: a file (or a picture of the gallery) and a photo taken now, with the chosen camera
export function attachMenu(host, { file, shoot }) {
  const box = panel(host, `📎 ${t("chat.attach")}`);
  box.append(row("📄", t("chat.attach.file"), "", false, () => { box.remove(); file(); }),
    row("📷", t("chat.attach.shoot"), t(source() === "device" ? "chat.menu.src.device" : "chat.menu.src.pc"), false,
      () => { box.remove(); shoot(); }));
}

// ⚙️: the three choices of the chat, each a section of rows
export function settingsMenu(host, gear) {
  const box = panel(host, `⚙️ ${t("chat.menu.title")}`);
  const body = el("div", "compose-body");
  box.append(body);
  const draw = () => {
    const src = source();
    body.replaceChildren(
      el("div", "compose-section", `🧠 ${t("chat.menu.think")}`),
      ...THINK.map((m) => row(THINK_ICON[m], t(`chat.menu.think.${m || "setting"}`), t(`chat.think.${m || "setting"}`),
        thinkMode() === m, () => { setThink(m); draw(); showGear(gear); })),
      el("div", "compose-section", `🎥 ${t("chat.menu.source")}`),
      ...["device", "pc"].map((s) => row(s === "device" ? "📱" : "🖥️", t(`chat.menu.src.${s}`), "", src === s, () => {
        try { localStorage.setItem(SRC_KEY, s); } catch { /* storage unavailable */ }
        draw();
      })));
    if (voice.supported()) {
      body.append(el("div", "compose-section", `🔊 ${t("chat.menu.voice")}`),
        ...["voice", "always", "off"].map((m) => row(VOICE_ICON[m], t(`chat.menu.voice.${m}`), "", voice.mode() === m,
          () => { voice.setMode(m); if (m === "off") voice.stop(); draw(); })),
        row("🎚️", t("chat.menu.voice.pick"), "", false, () => { box.remove(); pickVoice(host); }));
    }
  };
  draw();
}

// the gear says what is chosen without opening it
export function showGear(gear) {
  const m = thinkMode();
  gear.title = `${t("chat.menu.title")} · ${t(`chat.menu.think.${m || "setting"}`)}`;
  gear.setAttribute("aria-label", gear.title);
  gear.dataset.think = m ? THINK_ICON[m] : "";
}

// the voices: Aurora's own (from her computer) and this device's, each with ▶ to hear it
export async function pickVoice(host) {
  const code = lang.replace("_", "-");
  const [list, server] = await Promise.all([voice.localVoices(code), voice.serverAvailable(code)]);
  const box = panel(host, `🎚️ ${t("chat.menu.voice.pick")}`);
  box.append(el("div", "meta", list.length || server ? t("chat.voice.pick") : t(`chat.voice.novoice.${await voice.why(code)}`)));
  const voiceRow = (name, on, choose, play) => {
    const r = el("div", "voice-row");
    const p = el("button", "", "▶");
    const pick = el("button", on ? "on" : "", name);
    p.type = pick.type = "button";
    pick.addEventListener("click", () => { choose(); box.remove(); });
    p.addEventListener("click", play);
    r.append(p, pick);
    return r;
  };
  if (server) {
    box.append(voiceRow(`🌸 ${t("chat.voice.server")}`, voice.chosen() === voice.SERVER || !voice.chosen(),
      () => voice.choose(voice.SERVER), () => voice.speakServer(t("chat.voice.sample"), code)));
  }
  for (const vo of list) {
    box.append(voiceRow(vo.name, vo.name === voice.chosen() || (!voice.chosen() && !server && vo === list[0]),
      () => voice.choose(vo.name), () => voice.speak(t("chat.voice.sample"), vo.lang, vo)));
  }
}

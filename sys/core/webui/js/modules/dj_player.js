// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📻 The music page's player, the Winamp way (owner, 2026-10-27: «hai presente le animazioni di winamp?? farei proprio
// un player dentro il dj stile winamp… con l'opzione di eliminazione, editing del testo»; then «più animazioni
// milkdrop che si alternano… la possibilità di importare musica propria nel player… le canzoni create e caricate
// finiscono nel player ma si possono selezionare per il mix… differenziare con icone»): a green LCD with the title
// running and the time; the buttons, volume, seek, shuffle, repeat, ⏏ import; a visualiser fed by the music (Web
// Audio) — spectrum, oscilloscope, MilkDrop's presets (dj_milk.js: fixed per click or ∞ in turn) — full screen, or
// over the whole page where the browser has none (the phone app's WebView); the playlist of everything, each with its
// icon (🎤 sung by Aurora, 🎵 yours, 💿 a remix or mix, 🎛️ a set), a tick to choose it for the next mix, 🗑️, and for a
// song ✏️ its words and 🎤 «sing it again», for a set its console.
import { call } from "../api.js";
import { el, toBase64 } from "../dom.js";
import { t } from "../i18n.js";
import { milkdrop, PRESETS } from "./dj_milk.js";

const MODES = ["spectrum", "scope", "milk"];
const PRESET_S = 14;                                   // a MilkDrop preset this long, then the next
const mmss = (s) => (Number.isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "--:--");
const nice = (name) => name.replace(/\.(mp3|wav|flac|ogg|m4a|aac|opus|webm)$/i, "").replace(/-\d{8}-\d{4}$/, "").replace(/[-_]+/g, " ");
const kindOf = (it) => (it.song ? "song" : it.set ? "set" : it.kind === "mixes" ? "mix" : "mine");
const ICON = { song: "🎤", set: "🎛️", mix: "💿", mine: "🎵" };

export function djPlayer({ reload, onSelect, onConsole }) {
  const box = el("section", "wa");
  const audio = el("audio");
  audio.preload = "metadata";
  // — the main window
  const main = el("div", "wa-main");
  const bar = el("div", "wa-bar", "AURORA·AMP");
  const lcd = el("div", "wa-lcd");
  const time = el("div", "wa-time", "0:00");
  const marquee = el("div", "wa-marquee"), mtext = el("span", "", t("dj.player.empty"));
  marquee.append(mtext);
  const info = el("div", "wa-info", "MP3 · 44 kHz · stereo");
  const mini = el("canvas", "wa-mini");
  lcd.append(time, marquee, info, mini);
  const seek = el("input", "wa-seek");
  Object.assign(seek, { type: "range", min: 0, max: 1000, value: 0 });
  const btn = (label, title) => { const b = el("button", "wa-btn", label); b.title = title; b.type = "button"; return b; };
  const prev = btn("⏮", t("dj.player.prev")), play = btn("▶", t("dj.player.play")), stop = btn("⏹", t("dj.player.stop"));
  const next = btn("⏭", t("dj.player.next")), shuf = btn("🔀", t("dj.player.shuffle")), rep = btn("🔁", t("dj.player.repeat"));
  const eject = el("label", "wa-btn wa-eject", "⏏");                 // Winamp's «open file»: your own music in
  eject.title = t("dj.player.import");
  const pick = el("input");
  Object.assign(pick, { type: "file", accept: "audio/*", multiple: true, hidden: true });
  eject.append(pick);
  const vol = el("input", "wa-vol");
  Object.assign(vol, { type: "range", min: 0, max: 100, value: 80 });
  const controls = el("div", "wa-controls");
  controls.append(prev, play, stop, next, shuf, rep, eject, el("span", "wa-vol-l", "🔊"), vol);
  const upOut = el("div", "wa-up muted");
  main.append(bar, lcd, seek, controls, upOut);
  // — the visualiser
  const vis = el("div", "wa-vis");
  const canvas = el("canvas", "wa-canvas");
  const modes = el("div", "wa-modes");
  const tag = el("div", "wa-tag");
  let mode = "milk";
  // MilkDrop's button (owner, 27 Oct: «ad ogni click del milkdrop farei selezione fissa dei vari stili per arrivare al
  // loop automatico… simbolo infinito e nomi»): ∞ the presets in turn; each click fixes the next one; after the last, ∞
  let fixed = -1;
  const milkLabel = () => `MilkDrop ${fixed < 0 ? "∞" : "· " + t(`dj.player.preset.${PRESETS[fixed]}`)}`;
  for (const m of MODES) {
    const b = btn(m === "milk" ? milkLabel() : t(`dj.player.mode.${m}`), "");
    b.dataset.mode = m;
    b.classList.toggle("on", m === mode);
    b.addEventListener("click", () => {
      if (m === "milk" && mode === "milk") {
        fixed = fixed + 1 >= PRESETS.length ? -1 : fixed + 1;
        if (fixed >= 0) preset = fixed;
        presetAt = performance.now(); tagAt = presetAt;
        b.textContent = milkLabel();
      }
      mode = m;
      modes.querySelectorAll("button[data-mode]").forEach((x) => x.classList.toggle("on", x.dataset.mode === m));
    });
    modes.append(b);
  }
  const full = btn("⛶", t("dj.player.full"));
  const unmax = btn("✕", t("dj.player.exit"));
  unmax.classList.add("wa-unmax");
  // over the page where the browser has no full screen (an app of before 0.4.1): the page up and held still, so the
  // visualiser is not scrolled away (owner, 27 Oct: «conviene fare salire la pagina perché scende»)
  const maxed = (on) => { if (on) window.scrollTo(0, 0); vis.classList.toggle("wa-max", on); document.body.classList.toggle("wa-maxed", on); };
  full.addEventListener("click", async () => {
    if (document.fullscreenElement) return document.exitFullscreen();
    if (vis.classList.contains("wa-max")) return maxed(false);
    // the phone app's WebView has no full screen of its own: the visualiser then covers the page
    try { if (!document.fullscreenEnabled || !vis.requestFullscreen) throw new Error("none"); await vis.requestFullscreen(); }
    catch { maxed(true); }
  });
  unmax.addEventListener("click", () => maxed(false));
  modes.append(full);
  vis.append(canvas, tag, modes, unmax);
  // — the playlist
  const list = el("ol", "wa-list");
  const legend = el("div", "wa-legend", `🎤 ${t("dj.player.k_song")} · 🎵 ${t("dj.player.k_mine")} · 💿 ${t("dj.player.k_mix")} · 🎛️ ${t("dj.player.k_set")} · ☑ ${t("dj.player.k_tick")}`);
  const editor = el("div", "wa-editor");
  editor.hidden = true;
  box.append(main, vis, el("div", "wa-bar", t("dj.player.playlist")), list, legend, editor, audio);

  let items = [], cur = -1, shuffle = false, repeat = 0, ctx = null, an = null, freq, wave, chosen = [];
  pick.addEventListener("change", async () => {
    for (const f of pick.files) {
      upOut.textContent = t("dj.uploading", { name: f.name });
      try { await call("/v1/aurora/dj/tracks", { method: "POST", body: JSON.stringify({ name: f.name, data: await toBase64(f) }) }); }
      catch (e) { upOut.textContent = t("ev.error", { m: e.message }); return; }
    }
    upOut.textContent = "";
    pick.value = "";
    reload();
  });
  const ensureAudio = () => {                      // Web Audio after a gesture (the browsers' autoplay rule)
    if (ctx) return;
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaElementSource(audio);
    an = ctx.createAnalyser();
    an.fftSize = 2048;
    an.smoothingTimeConstant = 0.78;
    src.connect(an);
    an.connect(ctx.destination);
    freq = new Uint8Array(an.frequencyBinCount);
    wave = new Uint8Array(an.fftSize);
  };
  const load = (i, go = true) => {
    if (!items.length) return;
    cur = (i + items.length) % items.length;
    const it = items[cur];
    audio.src = `/v1/aurora/dj/${it.kind}/${encodeURIComponent(it.name)}`;
    mtext.textContent = `${cur + 1}. ${nice(it.name)}  ***  ${nice(it.name)}  ***`;
    list.querySelectorAll("li").forEach((li, k) => li.classList.toggle("on", k === cur));
    if (go) { ensureAudio(); ctx.resume(); audio.play().catch(() => {}); }
  };
  const step = (d) => {                            // shuffle: any other track, never the same one again at once
    if (!shuffle || items.length < 2) return load(cur + d);
    let k = cur;
    while (k === cur) k = Math.floor(Math.random() * items.length);
    load(k);
  };
  play.addEventListener("click", () => {
    if (cur < 0) return load(0);
    ensureAudio(); ctx.resume();
    audio.paused ? audio.play() : audio.pause();
  });
  stop.addEventListener("click", () => { audio.pause(); audio.currentTime = 0; });
  prev.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));
  // the owner, 27 Oct: «i tasti riproduzione casuale e loop sembrano non funzionare» — they did, but an emoji takes no
  // colour: «on» is now the pressed look; the loop as in Winamp: off → 🔁 the playlist → 🔂 one track → off
  shuf.addEventListener("click", () => { shuffle = !shuffle; shuf.classList.toggle("on", shuffle); shuf.title = `${t("dj.player.shuffle")}: ${t(shuffle ? "dj.player.on" : "dj.player.off")}`; });
  rep.addEventListener("click", () => {
    repeat = (repeat + 1) % 3;
    rep.textContent = repeat === 2 ? "🔂" : "🔁";
    rep.classList.toggle("on", repeat > 0);
    rep.title = t(["dj.player.loop_off", "dj.player.loop_all", "dj.player.loop_one"][repeat]);
  });
  vol.addEventListener("input", () => { audio.volume = vol.value / 100; });
  audio.volume = 0.8;
  seek.addEventListener("input", () => { if (audio.duration) audio.currentTime = (seek.value / 1000) * audio.duration; });
  audio.addEventListener("play", () => { play.textContent = "⏸"; box.classList.add("playing"); });
  audio.addEventListener("pause", () => { play.textContent = "▶"; box.classList.remove("playing"); });
  audio.addEventListener("ended", () => {
    if (repeat === 2) return load(cur);                       // 🔂 the same track
    if (shuffle || cur < items.length - 1) return step(1);
    if (repeat === 1) load(0);                                // 🔁 the playlist again from the top
  });
  audio.addEventListener("timeupdate", () => {
    time.textContent = mmss(audio.currentTime);
    if (audio.duration) seek.value = String(Math.round((audio.currentTime / audio.duration) * 1000));
    info.textContent = `MP3 · ${mmss(audio.duration)} · 44 kHz · stereo`;
  });

  // — the words of a song: edited, and sung again
  const edit = async (it) => {
    const s = await call(`/v1/aurora/dj-song/${encodeURIComponent(it.name)}`);
    const title = el("input"), cap = el("textarea"), lyr = el("textarea");
    title.value = s.title || ""; cap.value = s.caption || ""; lyr.value = s.lyrics || "";
    cap.rows = 2; lyr.rows = 12;
    const save = btn(`💾 ${t("dj.player.save")}`, ""), again = btn(`🎤 ${t("dj.player.again")}`, ""), close = btn("✕", "");
    const out = el("span", "muted");
    save.addEventListener("click", async () => {
      try { await call(`/v1/aurora/dj-song/${encodeURIComponent(it.name)}`, { method: "PUT", body: JSON.stringify({ title: title.value, caption: cap.value, lyrics: lyr.value }) }); out.textContent = t("dj.player.saved"); }
      catch (e) { out.textContent = e.message; }
    });
    again.addEventListener("click", async () => {
      try {
        const r = await call("/v1/aurora/dj/song", { method: "POST", body: JSON.stringify({ title: title.value, caption: cap.value, lyrics: lyr.value, language: s.language || "en", seconds: s.seconds || 180 }) });
        out.textContent = t("dj.song.started", { title: r.title });
        out.dataset.working = "1";
        reload();
      } catch (e) { out.textContent = e.message; }
    });
    close.addEventListener("click", () => { editor.hidden = true; });
    const row = el("div", "appr-actions");
    row.append(save, again, close, out);
    editor.replaceChildren(el("strong", "", `✏️ ${nice(it.name)}`), el("label", "", t("dj.player.f_title")), title,
      el("label", "", t("dj.player.f_caption")), cap, el("label", "", t("dj.player.f_lyrics")), lyr, row);
    editor.hidden = false;
    editor.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const ref = (it) => (it.kind === "mixes" ? `mixes/${it.name}` : it.name);   // what the mixer takes
  const refresh = (s) => {
    const was = items[cur]?.name;
    items = [...s.mixes.map((f) => ({ ...f, kind: "mixes" })), ...s.tracks.map((f) => ({ ...f, kind: "tracks" }))];
    chosen = chosen.filter((r) => items.some((it) => ref(it) === r));
    list.replaceChildren(...(items.length ? items.map((it, k) => {
      const li = el("li", it.name === was ? "on" : "");
      const tick = el("input", "wa-tick");
      tick.type = "checkbox";
      tick.title = t("dj.player.k_tick");
      tick.checked = chosen.includes(ref(it));
      tick.addEventListener("change", () => {      // the order of the ticks: A, then B for the two decks
        chosen = chosen.filter((r) => r !== ref(it));
        if (tick.checked) chosen.push(ref(it));
        onSelect([...chosen]);
      });
      const k_ = kindOf(it);
      const name = el("span", "wa-name", `${ICON[k_]} ${nice(it.name)}`);
      name.title = t(`dj.player.k_${k_}`);
      name.addEventListener("click", () => load(k));
      const acts = el("span", "wa-acts");
      if (it.song) {
        const e = btn("✏️", t("dj.player.edit"));
        e.addEventListener("click", () => edit(it).catch((x) => alert(x.message)));
        acts.append(e);
      }
      if (it.set) {
        const c = btn("🎛️", t("dj.set.console"));
        c.addEventListener("click", () => onConsole(it.name));
        acts.append(c);
      }
      const del = btn("🗑️", t("up.delete"));
      del.addEventListener("click", async () => {
        if (!confirm(t("up.confirm", { name: it.name }))) return;
        if (k === cur) { audio.pause(); audio.removeAttribute("src"); cur = -1; }
        await call(`/v1/aurora/dj/${it.kind}/${encodeURIComponent(it.name)}`, { method: "DELETE" });
        reload();
      });
      acts.append(del);
      li.append(tick, name, acts);
      return li;
    }) : [el("li", "wa-none", t("dj.player.none"))]));
    cur = items.findIndex((x) => x.name === was);
    if (!items.length) mtext.textContent = t("dj.player.empty");
    onSelect([...chosen]);
  };

  // — the drawing, every frame while the page shows it
  let peaks = new Float32Array(48), hue = 0, preset = 0, presetAt = performance.now(), tagAt = 0;
  const g = canvas.getContext("2d"), gm = mini.getContext("2d");
  const fit = (c) => { const r = c.getBoundingClientRect(), d = window.devicePixelRatio || 1; if (c.width !== Math.round(r.width * d)) { c.width = Math.round(r.width * d); c.height = Math.round(r.height * d); } return [c.width, c.height]; };
  const bands = (n) => {                            // n logarithmic bands from the spectrum, 0..1
    const out = new Float32Array(n), N = freq.length;
    for (let i = 0; i < n; i++) {
      const a = Math.floor(Math.pow(N, i / n)), b = Math.max(a + 1, Math.floor(Math.pow(N, (i + 1) / n)));
      let m = 0; for (let k = a; k < b && k < N; k++) m = Math.max(m, freq[k]);
      out[i] = m / 255;
    }
    return out;
  };
  const milkDraw = milkdrop(canvas);              // the presets (dj_milk.js)
  const frame = (now) => {
    if (!box.isConnected) return;                    // the page left: the loop stops
    requestAnimationFrame(frame);
    const [w, h] = fit(canvas);
    if (an) { an.getByteFrequencyData(freq); an.getByteTimeDomainData(wave); }
    const live = an && !audio.paused;
    const b = live ? bands(48) : new Float32Array(48);
    const bass = (b[2] + b[3] + b[4] + b[5]) / 4, treble = (b[36] + b[40] + b[44]) / 3;
    hue = (hue + 0.4 + bass * 3) % 360;
    if (mode === "milk" && fixed < 0 && now - presetAt > PRESET_S * 1000) {   // ∞: the presets take turns, like MilkDrop's
      preset = (preset + 1) % PRESETS.length; presetAt = now; tagAt = now;
    }
    tag.textContent = mode === "milk" && now - tagAt < 2500 ? `✦ ${fixed < 0 ? "∞ " : ""}${t(`dj.player.preset.${PRESETS[preset]}`)}` : "";
    if (mode === "spectrum") {
      g.fillStyle = "#000"; g.fillRect(0, 0, w, h);
      const bw = w / 48;
      const grad = g.createLinearGradient(0, h, 0, 0);
      grad.addColorStop(0, "#1fbd2c"); grad.addColorStop(0.55, "#d6e021"); grad.addColorStop(1, "#ef3a1d");
      for (let i = 0; i < 48; i++) {
        const v = b[i] * h * 0.95;
        peaks[i] = Math.max(v, peaks[i] - h * 0.008);
        g.fillStyle = grad; g.fillRect(i * bw + 1, h - v, bw - 2, v);
        g.fillStyle = "#cfd8dc"; g.fillRect(i * bw + 1, h - peaks[i] - 3, bw - 2, 2);
      }
    } else if (mode === "scope") {
      g.fillStyle = "rgba(0,0,0,.35)"; g.fillRect(0, 0, w, h);
      g.lineWidth = 2 * (window.devicePixelRatio || 1); g.strokeStyle = `hsl(${hue},100%,60%)`; g.shadowColor = g.strokeStyle; g.shadowBlur = 12;
      g.beginPath();
      for (let i = 0; i < (wave ? wave.length : 0); i += 2) { const x = (i / wave.length) * w, y = h / 2 + ((live ? wave[i] : 128) - 128) / 128 * h * 0.45; i ? g.lineTo(x, y) : g.moveTo(x, y); }
      g.stroke(); g.shadowBlur = 0;
    } else if (mode === "milk") {
      milkDraw(PRESETS[preset], w, h, { b, wave, live, bass, treble, now, hue });
    }
    const [mw, mh] = fit(mini);                      // the LCD's own small spectrum
    gm.clearRect(0, 0, mw, mh);
    for (let i = 0; i < 24; i++) { const v = (b[i * 2] || 0) * mh; gm.fillStyle = "#39ff6a"; gm.fillRect(i * (mw / 24) + 1, mh - v, mw / 24 - 2, v); }
  };
  requestAnimationFrame(frame);
  return { box, refresh };
}

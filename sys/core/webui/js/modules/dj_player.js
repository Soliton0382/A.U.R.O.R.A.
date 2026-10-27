// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📻 The music page's player, the Winamp way (owner, 2026-10-27: «hai presente le animazioni di winamp?? farei proprio
// un player dentro il dj stile winamp… con l'opzione di eliminazione, editing del testo»; then «più animazioni
// milkdrop che si alternano… la possibilità di importare musica propria nel player… le canzoni create e caricate
// finiscono nel player ma si possono selezionare per il mix… differenziare con icone»): a green LCD with the title
// running and the time; the buttons, volume, seek, shuffle, repeat, ⏏ import; a visualiser fed by the music (Web
// Audio) — spectrum, oscilloscope, MilkDrop-like presets that take turns by themselves, a starfield — full screen, or
// over the whole page where the browser has none (the phone app's WebView); the playlist of everything, each with its
// icon (🎤 sung by Aurora, 🎵 yours, 💿 a remix or mix, 🎛️ a set), a tick to choose it for the next mix, 🗑️, and for a
// song ✏️ its words and 🎤 «sing it again», for a set its console.
import { call } from "../api.js";
import { el, toBase64 } from "../dom.js";
import { t } from "../i18n.js";

const MODES = ["spectrum", "scope", "milk", "stars"];
const PRESETS = ["rings", "tunnel", "kaleido", "plasma", "spiral"];
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
  const maxed = (on) => { vis.classList.toggle("wa-max", on); document.body.classList.toggle("wa-maxed", on); };
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

  let items = [], cur = -1, shuffle = false, repeat = false, ctx = null, an = null, freq, wave, chosen = [];
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
  const step = (d) => load(shuffle && items.length > 1 ? Math.floor(Math.random() * items.length) : cur + d);
  play.addEventListener("click", () => {
    if (cur < 0) return load(0);
    ensureAudio(); ctx.resume();
    audio.paused ? audio.play() : audio.pause();
  });
  stop.addEventListener("click", () => { audio.pause(); audio.currentTime = 0; });
  prev.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));
  shuf.addEventListener("click", () => { shuffle = !shuffle; shuf.classList.toggle("on", shuffle); });
  rep.addEventListener("click", () => { repeat = !repeat; rep.classList.toggle("on", repeat); });
  vol.addEventListener("input", () => { audio.volume = vol.value / 100; });
  audio.volume = 0.8;
  seek.addEventListener("input", () => { if (audio.duration) audio.currentTime = (seek.value / 1000) * audio.duration; });
  audio.addEventListener("play", () => { play.textContent = "⏸"; box.classList.add("playing"); });
  audio.addEventListener("pause", () => { play.textContent = "▶"; box.classList.remove("playing"); });
  audio.addEventListener("ended", () => (repeat ? load(cur) : cur < items.length - 1 || shuffle ? step(1) : null));
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
  let peaks = new Float32Array(48), stars = [], hue = 0, preset = 0, presetAt = performance.now(), tagAt = 0;
  const g = canvas.getContext("2d"), gm = mini.getContext("2d");
  const small = document.createElement("canvas");  // the plasma, drawn small and stretched
  small.width = 96; small.height = 54;
  const gs = small.getContext("2d"), img = gs.createImageData(96, 54);
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
  const feedback = (w, h, rot, zoom, fade) => {     // MilkDrop's heart: the last frame, turned and zoomed, under the new
    g.save(); g.globalAlpha = fade; g.translate(w / 2, h / 2); g.rotate(rot); g.scale(zoom, zoom);
    g.drawImage(canvas, -w / 2, -h / 2); g.restore();
  };
  const milk = (w, h, b, live, bass, treble, now) => {
    const P = PRESETS[preset], dpr = window.devicePixelRatio || 1, n = wave ? wave.length : 1;
    const wv = (k) => (live && wave ? (wave[Math.floor(k) % n] - 128) / 128 : 0);
    if (P === "rings") {
      feedback(w, h, 0.004 + bass * 0.02, 1.012 + bass * 0.05, 0.93);
      g.fillStyle = "rgba(0,0,0,.06)"; g.fillRect(0, 0, w, h);
      const r0 = Math.min(w, h) * (0.16 + bass * 0.18);
      g.lineWidth = 2.5 * dpr;
      for (let ring = 0; ring < 2; ring++) {
        g.strokeStyle = `hsla(${(hue + ring * 140) % 360},100%,${55 + treble * 30}%,.9)`;
        g.beginPath();
        for (let i = 0; i <= 360; i += 2) {
          const r = r0 * (1 + ring * 0.6) + wv((i / 360) * (n - 1)) * r0 * 0.9, a = (i * Math.PI) / 180 + hue / 60;
          const x = w / 2 + Math.cos(a) * r, y = h / 2 + Math.sin(a) * r;
          i ? g.lineTo(x, y) : g.moveTo(x, y);
        }
        g.stroke();
      }
    } else if (P === "tunnel") {                     // squares flying at you, the beat speeding them
      feedback(w, h, -0.01 - bass * 0.03, 1.04 + bass * 0.1, 0.9);
      g.fillStyle = "rgba(0,0,0,.08)"; g.fillRect(0, 0, w, h);
      const s = Math.min(w, h) * (0.08 + bass * 0.12);
      g.lineWidth = 3 * dpr;
      g.strokeStyle = `hsl(${hue},100%,${50 + treble * 40}%)`;
      g.save(); g.translate(w / 2, h / 2); g.rotate(hue / 40);
      g.strokeRect(-s, -s, 2 * s, 2 * s); g.restore();
    } else if (P === "kaleido") {                    // the wave in six mirrored slices
      feedback(w, h, 0.006, 0.985, 0.88);
      g.save(); g.translate(w / 2, h / 2);
      g.lineWidth = 2 * dpr;
      for (let k = 0; k < 6; k++) {
        g.rotate(Math.PI / 3);
        g.strokeStyle = `hsla(${(hue + k * 60) % 360},100%,60%,.85)`;
        g.beginPath();
        for (let i = 0; i < 128; i++) {
          const x = (i / 128) * Math.min(w, h) * 0.48, y = wv(i * 8) * Math.min(w, h) * (0.12 + bass * 0.2) * (k % 2 ? -1 : 1);
          i ? g.lineTo(x, y) : g.moveTo(x, y);
        }
        g.stroke();
      }
      g.restore();
    } else if (P === "plasma") {                     // a colour field folding with the bass and the highs
      const T = now / 1000, d = img.data;
      for (let y = 0; y < 54; y++) for (let x = 0; x < 96; x++) {
        const v = Math.sin(x / (8 - bass * 4) + T) + Math.sin(y / 6 + T * 1.3) + Math.sin((x + y) / (10 + treble * 6) + T * 0.7)
          + Math.sin(Math.hypot(x - 48, y - 27) / (5 - bass * 2) - T * 2);
        const hh = (hue + v * 45 + 360) % 360, c = (1 - Math.abs(((hh / 60) % 2) - 1));
        const [r, gg, bb] = hh < 60 ? [1, c, 0] : hh < 120 ? [c, 1, 0] : hh < 180 ? [0, 1, c] : hh < 240 ? [0, c, 1] : hh < 300 ? [c, 0, 1] : [1, 0, c];
        const L = 0.45 + 0.5 * Math.abs(Math.sin(v)), o = (y * 96 + x) * 4;
        d[o] = r * 255 * L; d[o + 1] = gg * 255 * L; d[o + 2] = bb * 255 * L; d[o + 3] = 255;
      }
      gs.putImageData(img, 0, 0);
      g.imageSmoothingEnabled = true; g.drawImage(small, 0, 0, w, h);
    } else {                                         // spiral: the spectrum thrown out along turning arms
      feedback(w, h, 0.02 + bass * 0.04, 1.006, 0.92);
      g.fillStyle = "rgba(0,0,0,.05)"; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 48; i++) {
        const a = i * 0.45 + hue / 20, r = (i / 48) * Math.min(w, h) * 0.5;
        g.fillStyle = `hsl(${(hue + i * 7) % 360},100%,${45 + b[i] * 45}%)`;
        g.beginPath(); g.arc(w / 2 + Math.cos(a) * r, h / 2 + Math.sin(a) * r, (1 + b[i] * 9) * dpr, 0, Math.PI * 2); g.fill();
      }
    }
  };
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
      milk(w, h, b, live, bass, treble, now);
    } else {                                         // stars: the beat pushes them out
      g.fillStyle = "rgba(0,0,0,.3)"; g.fillRect(0, 0, w, h);
      while (stars.length < 380) stars.push({ x: (Math.random() - 0.5) * w, y: (Math.random() - 0.5) * h, z: Math.random() * w });
      for (const s of stars) {
        s.z -= 2 + bass * 40;
        if (s.z <= 1) { s.x = (Math.random() - 0.5) * w; s.y = (Math.random() - 0.5) * h; s.z = w; }
        const k = 128 / s.z, x = w / 2 + s.x * k, y = h / 2 + s.y * k, r = Math.max(0.6, (1 - s.z / w) * 3.2);
        g.fillStyle = `hsl(${(hue + s.z / 4) % 360},90%,${60 + treble * 30}%)`;
        g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
      }
    }
    const [mw, mh] = fit(mini);                      // the LCD's own small spectrum
    gm.clearRect(0, 0, mw, mh);
    for (let i = 0; i < 24; i++) { const v = (b[i * 2] || 0) * mh; gm.fillStyle = "#39ff6a"; gm.fillRect(i * (mw / 24) + 1, mh - v, mw / 24 - 2, v); }
  };
  requestAnimationFrame(frame);
  return { box, refresh };
}

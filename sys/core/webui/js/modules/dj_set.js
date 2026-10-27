// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎛️ Aurora's set and its console (owner, 2026-10-27: «qualcosa di grafico accattivante che permetta davvero un mix
// autonomo fine brani»): the set's options (Aurora's order by key and tempo, or yours; the transitions' length), and
// for a set made (aud_set's timeline) two decks that spin with the track on each, its key on the Camelot wheel, the
// crossfader moving by itself through every transition, the whole set's waveform coloured track by track with the
// transitions shaded, and the tracklist — click anywhere to jump there.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const hue = (camelot) => ((parseInt(camelot, 10) - 1) * 30 + (camelot.endsWith("A") ? 0 : 12)) % 360;   // the wheel's colours
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// the options beside «Crea»: shown when two or more tracks are ticked
export function setPanel(ticked, done) {
  const box = el("div", "dj-set-panel");
  const order = el("select");
  for (const [v, k] of [["auto", "dj.set.order_auto"], ["mine", "dj.set.order_mine"]]) { const o = el("option", "", t(k)); o.value = v; order.append(o); }
  const bars = el("select");
  for (const b of [8, 16, 32]) { const o = el("option", "", t("dj.set.bars", { n: b })); o.value = String(b); bars.append(o); }
  bars.value = "16";
  const go = el("button", "approve", `🎛️ ${t("dj.set.go")}`);
  const out = el("span", "muted");
  go.addEventListener("click", async () => {
    const tracks = ticked();
    if (tracks.length < 2) { out.textContent = t("dj.set.pick"); return; }
    try {
      const r = await call("/v1/aurora/dj/set", { method: "POST", body: JSON.stringify({ tracks, keep_order: order.value === "mine", bars: Number(bars.value) }) });
      out.textContent = t("dj.started", { title: r.title });
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    done();
  });
  box.append(el("span", "", t("dj.set.title")), order, bars, go, out);
  return box;
}

function deck(side) {
  const d = el("div", `dj-c-deck dj-c-${side}`);
  const disc = el("div", "dj-c-disc");
  disc.append(el("div", "dj-c-label", side.toUpperCase()));
  const name = el("div", "dj-c-name", "—"), meta = el("div", "dj-c-meta", "");
  d.append(disc, name, meta);
  return { d, disc, name, meta };
}

// the console of one set: its timeline from the server, its audio, everything moved by the playhead
export async function setConsole(file) {
  const plan = await call(`/v1/aurora/dj-timeline/${encodeURIComponent(file)}`);
  const box = el("div", "dj-console");
  const audio = el("audio");
  audio.preload = "auto";
  audio.src = `/v1/aurora/dj/mixes/${encodeURIComponent(file)}`;
  const a = deck("a"), b = deck("b");
  const fader = el("div", "dj-c-fader"), knob = el("div", "dj-c-knob");
  fader.append(el("span", "", "A"), knob, el("span", "", "B"));
  const mid = el("div", "dj-c-mid");
  const play = el("button", "dj-c-play", "▶");
  const time = el("div", "dj-c-time", `0:00 / ${mmss(plan.seconds)}`);
  mid.append(el("div", "dj-c-bpm", `${plan.bpm} BPM`), play, time, fader);
  const decks = el("div", "dj-c-decks");
  decks.append(a.d, mid, b.d);
  const wave = el("canvas", "dj-c-wave");
  const list = el("ol", "dj-c-list");
  plan.tracks.forEach((tr, i) => {
    const li = el("li", "");
    li.style.setProperty("--h", hue(tr.camelot));
    li.append(el("span", "dj-c-cam", tr.camelot), el("span", "", ` ${tr.name}`),
      el("small", "muted", ` · ${mmss(tr.start)} · ${tr.bpm} BPM · ${tr.key}${tr.transition ? ` · ${t(`dj.set.kind.${tr.transition.kind}`)} ${tr.transition.bars} ${t("dj.set.bars_short")}` : ""}`));
    li.addEventListener("click", () => { audio.currentTime = (tr.transition ? tr.transition.from : tr.start); audio.play(); });
    list.append(li);
  });
  box.append(el("h4", "", `🎛️ ${file}`), decks, wave, list, audio);

  const draw = () => {
    const w = wave.clientWidth || 600, h = wave.clientHeight || 90, dpr = window.devicePixelRatio || 1;
    if (wave.width !== Math.round(w * dpr)) { wave.width = Math.round(w * dpr); wave.height = Math.round(h * dpr); }
    const g = wave.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const x = (s) => (s / plan.seconds) * w;
    for (const tr of plan.tracks) {                            // the transitions, shaded
      if (!tr.transition) continue;
      const grad = g.createLinearGradient(x(tr.transition.from), 0, x(tr.transition.to), 0);
      grad.addColorStop(0, "rgba(255,255,255,0)"); grad.addColorStop(0.5, "rgba(255,255,255,.10)"); grad.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = grad; g.fillRect(x(tr.transition.from), 0, x(tr.transition.to) - x(tr.transition.from), h);
    }
    const n = plan.peaks.length, bw = w / n, now = audio.currentTime || 0;
    for (let i = 0; i < n; i++) {                              // each bar in the colour of the track playing there
      const s = (i / n) * plan.seconds;
      const tr = [...plan.tracks].reverse().find((q) => q.start <= s) || plan.tracks[0];
      const v = plan.peaks[i] * (h / 2 - 2);
      g.fillStyle = `hsla(${hue(tr.camelot)}, 75%, ${s <= now ? 62 : 42}%, ${s <= now ? 1 : 0.75})`;
      g.fillRect(i * bw, h / 2 - v, Math.max(1, bw - 0.5), v * 2);
    }
    g.fillStyle = "#fff"; g.fillRect(x(now) - 1, 0, 2, h);    // the playhead
  };

  const update = () => {
    const now = audio.currentTime || 0;
    time.textContent = `${mmss(now)} / ${mmss(plan.seconds)}`;
    const k = Math.max(0, plan.tracks.findIndex((tr, i) => now < (plan.tracks[i + 1]?.transition?.to ?? Infinity)));
    const cur = plan.tracks[k], next = plan.tracks[k + 1];
    const into = next?.transition && now >= next.transition.from ? (now - next.transition.from) / (next.transition.to - next.transition.from) : 0;
    // decks alternate: even tracks on A, odd on B; the fader goes from the playing deck to the other in a transition
    const onA = k % 2 === 0;
    const [deckCur, deckNext] = onA ? [a, b] : [b, a];
    for (const [dk, tr, live] of [[deckCur, cur, true], [deckNext, next, into > 0]]) {
      dk.name.textContent = tr ? tr.name : "—";
      dk.meta.textContent = tr ? `${tr.bpm} → ${plan.bpm} BPM · ${tr.key} · ${tr.camelot}` : "";
      dk.disc.style.setProperty("--h", tr ? hue(tr.camelot) : 220);
      dk.disc.classList.toggle("dj-c-spinning", Boolean(tr) && live && !audio.paused);
      dk.d.classList.toggle("live", Boolean(tr) && live);
    }
    const pos = onA ? into : 1 - into;                          // 0 = A, 1 = B
    knob.style.left = `calc(${(pos * 100).toFixed(1)}% - 0px)`;
    draw();
    if (!audio.paused) requestAnimationFrame(update);
  };
  play.addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
  audio.addEventListener("play", () => { play.textContent = "⏸"; requestAnimationFrame(update); });
  audio.addEventListener("pause", () => { play.textContent = "▶"; update(); });
  audio.addEventListener("seeked", update);
  wave.addEventListener("click", (e) => {
    const r = wave.getBoundingClientRect();
    audio.currentTime = ((e.clientX - r.left) / r.width) * plan.seconds;
    update();
  });
  new ResizeObserver(() => draw()).observe(wave);
  requestAnimationFrame(update);
  return box;
}

// 🎤 a song from an idea (aud_song): the idea, the language it is sung in, how long, the user's lyrics if any; when the
// music model is not installed yet, what to install and where
export function songPanel(state, done) {
  const box = el("details", "report dj-song");
  box.open = true;
  box.append(el("summary", "", t("dj.song.title")));
  if (!(state.code && state.weights)) {
    box.append(el("p", "warn", t("dj.song.missing", { dir: state.dir, models: state.models })),
      el("pre", "", `git clone https://github.com/ACE-Step/ACE-Step-1.5.git ${state.dir}\ncd ${state.dir} && uv sync\nACESTEP_CHECKPOINTS_DIR=${state.models} uv run acestep-download`));
    return box;
  }
  const idea = el("textarea", "dj-song-idea");
  idea.rows = 3;
  idea.placeholder = t("dj.song.ph");
  const lang = el("select");
  for (const [v, n] of [["en", "English"], ["it", "Italiano"], ["es", "Español"], ["fr", "Français"], ["de", "Deutsch"], ["pt", "Português"], ["ja", "日本語"], ["zh", "中文"], ["ko", "한국어"]]) {
    const o = el("option", "", n); o.value = v; lang.append(o);
  }
  const secs = el("select");
  for (const s of [60, 120, 180, 240, 300]) { const o = el("option", "", t("dj.song.secs", { m: s / 60 })); o.value = String(s); secs.append(o); }
  secs.value = "180";
  const own = el("details");
  const lyr = el("textarea");
  lyr.rows = 6;
  lyr.placeholder = "[verse]\n…\n[chorus]\n…";
  own.append(el("summary", "", t("dj.song.own")), lyr);
  const go = el("button", "approve", `🎤 ${t("dj.song.go")}`);
  const out = el("span", "muted");
  go.addEventListener("click", async () => {
    try {
      const r = await call("/v1/aurora/dj/song", { method: "POST", body: JSON.stringify({ idea: idea.value, language: lang.value, seconds: Number(secs.value), lyrics: lyr.value }) });
      out.textContent = t("dj.song.started", { title: r.title });
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    done();
  });
  const row = el("div", "appr-actions");
  row.append(lang, secs, go, out);
  box.append(el("p", "muted", t("dj.song.hint")), idea, own, row);
  return box;
}

// a song's lyrics and caption, under its row
export async function songText(file) {
  const s = await call(`/v1/aurora/dj-song/${encodeURIComponent(file)}`);
  const box = el("div", "dj-song-text");
  box.append(el("strong", "", s.title), el("p", "muted", s.caption), el("pre", "", s.lyrics));
  return box;
}

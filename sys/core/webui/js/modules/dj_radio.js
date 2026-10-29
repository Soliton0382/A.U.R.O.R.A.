// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📻 Internet radio (aud_radio; owner, 28 Oct: «io però non ho premium… qualche radio internet che possiamo
// sfruttare?»): the genres as buttons, a search by name, the stations found with ▶ (played in the player, through
// Aurora, with its visualiser) and ☆ to keep one; the stations kept first. 🎓 Learn the style (aud_learn; owner,
// 29 Oct): a few minutes heard in memory, only the DJ's numbers kept — the styles learnt are in 🎓 Stili (dj_styles.js).
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

export function radioPanel(play) {
  const box = el("details", "report dj-radio");
  box.append(el("summary", "", `📻 ${t("dj.radio.title")}`), el("p", "muted", t("dj.radio.hint")));
  const presets = el("div", "dj-radio-presets");
  // every genre in families (aud_radio.GENRES): a family's chip opens its genres, each with its stations counted
  const families = el("div", "dj-radio-presets");
  const genresRow = el("div", "dj-radio-presets");
  const other = el("input");
  other.placeholder = t("dj.radio.other");
  other.setAttribute("list", "dj-radio-more");
  other.autocomplete = "off";
  const more = el("datalist");
  more.id = "dj-radio-more";
  const otherForm = el("form", "dj-radio-search");
  const otherGo = el("button", "", "🎼");
  otherGo.type = "submit";
  otherForm.append(other, more, otherGo);
  const form = el("form", "dj-radio-search");
  const q = el("input");
  q.placeholder = t("dj.radio.ph");
  const go = el("button", "", "🔎");
  go.type = "submit";
  form.append(q, go);
  const kept = el("div", "dj-radio-kept");
  // 🎓 how long to listen (a whole track is 5-8 minutes), and the listen going on: a countdown, then its outcome
  const howLong = el("select");
  for (const m of [1.5, 2.5, 4, 6, 8, 10, 15]) {
    const o = el("option", "", t("dj.learn.minutes", { m }));
    o.value = String(m * 60);
    if (m === 2.5) o.selected = true;
    howLong.append(o);
  }
  const learnLine = el("p", "muted");
  const learnText = el("span");
  const finish = el("button", "", `⏹ ${t("dj.learn.stop")}`);      // «Fine»: learn from what was heard so far
  finish.type = "button";
  finish.hidden = true;
  finish.addEventListener("click", async () => {
    finish.disabled = true;
    try { await call("/v1/aurora/dj/learn/stop", { method: "POST", body: "{}" }); } catch (e) { learnText.textContent = t("ev.error", { m: e.message }); }
    follow();
  });
  learnLine.append(learnText, " ", finish);
  let timer = null;
  const follow = async () => {
    clearTimeout(timer);
    let s;
    try { s = await call("/v1/aurora/dj/learn"); } catch { return; }
    if (s.running) {
      const left = Math.max(0, Math.round(s.seconds - s.elapsed));
      const listening = s.phase === "listening" && !s.stopping;
      learnText.textContent = listening
        ? t("dj.learn.left", { title: s.title, m: Math.floor(left / 60), s: String(left % 60).padStart(2, "0") })
        : t("dj.learn.analysing", { title: s.title });
      finish.hidden = !listening;
      finish.disabled = false;
      timer = setTimeout(follow, 1000);
    } else {
      finish.hidden = true;
      if (s.last) {
        learnText.textContent = `${s.last.ok ? "✅" : "⚠️"} ${s.last.text}`;
        if (s.last.ok && learnText.dataset.told !== String(s.last.at)) {     // once: the lists of the page follow
          learnText.dataset.told = String(s.last.at);
          window.dispatchEvent(new Event("dj-styles"));
        }
      }
    }
  };
  const found = el("ol", "dj-radio-list");
  const out = el("p", "muted");
  const learnBar = el("p", "muted");
  learnBar.append(`🎓 ${t("dj.learn.how_long")} `, howLong);
  // 🎓 or from one of the user's own tracks (owner, 29 Oct: «l'impara la potremmo mettere anche sulle canzoni che carico»)
  const fromTrack = el("p", "muted");
  const pick = el("select");
  const learnTrack = el("button", "", `🎓 ${t("dj.learn.track")}`);
  learnTrack.type = "button";
  learnTrack.addEventListener("click", async () => {
    if (!pick.value) return;
    const name = prompt(t("dj.learn.name"), pick.value.replace(/\.[^.]+$/, ""));
    if (name === null) return;
    try { await call("/v1/aurora/dj/learn", { method: "POST", body: JSON.stringify({ track: pick.value, name }) }); follow(); }
    catch (e) { learnText.textContent = t("ev.error", { m: e.message }); }
  });
  fromTrack.append(`${t("dj.learn.or_track")} `, pick, " ", learnTrack);
  call("/v1/aurora/dj").then((d) => {
    for (const tr of d.tracks) { const o = el("option", "", tr.name); o.value = tr.name; pick.append(o); }
    if (!d.tracks.length) fromTrack.hidden = true;
  }).catch(() => { fromTrack.hidden = true; });
  box.append(presets, families, genresRow, otherForm, form, kept, learnBar, fromTrack, learnLine, out, found);
  box.addEventListener("toggle", () => { if (box.open) follow(); else clearTimeout(timer); });
  let mine = [];

  const row = (s) => {
    const li = el("li");
    const p = el("button", "", "▶");
    p.type = "button";
    p.title = t("dj.radio.play");
    p.addEventListener("click", () => play(`/v1/aurora/radio/${s.id}/stream`, `📻 ${s.name}`));
    const on = mine.some((m) => m.id === s.id);
    const star = el("button", "", on ? "★" : "☆");
    star.type = "button";
    star.title = t(on ? "dj.radio.unkeep" : "dj.radio.keep");
    star.addEventListener("click", async () => {
      try { mine = (await call("/v1/aurora/radio/favourites", { method: "POST", body: JSON.stringify({ station: s, on: !on }) })).favourites; show(); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    });
    const info = [s.tags && s.tags.split(",").slice(0, 3).join(", "), s.country, s.codec && `${s.codec}${s.bitrate ? ` ${s.bitrate}k` : ""}`].filter(Boolean).join(" · ");
    const learn = el("button", "", "🎓");
    learn.type = "button";
    learn.title = t("dj.learn.title");
    learn.addEventListener("click", async () => {
      const name = prompt(t("dj.learn.name"), s.name);
      if (name === null) return;
      learn.disabled = true;
      try {
        await call("/v1/aurora/dj/learn", { method: "POST", body: JSON.stringify({ station: s.id, name, seconds: Number(howLong.value) }) });
        follow();
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
      learn.disabled = false;
    });
    li.append(p, star, learn, el("strong", "", ` ${s.name}`), el("span", "muted", info ? ` — ${info}` : ""));
    return li;
  };
  let last = [];
  const show = () => {
    kept.replaceChildren(...(mine.length ? [el("strong", "", `★ ${t("dj.radio.kept")}`), el("ol", "dj-radio-list")] : []));
    if (mine.length) kept.lastChild.append(...mine.map(row));
    found.replaceChildren(...last.map(row));
  };
  const shut = () => {                       // a genre picked outside the families: the family open closed
    families.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
    genresRow.replaceChildren();
  };
  const look = async (params, label) => {
    out.textContent = `✻ ${t("dj.radio.looking")}`;
    try {
      last = (await call(`/v1/aurora/radio/search?${new URLSearchParams(params)}`)).stations;
      out.textContent = t("dj.radio.found", { n: last.length, what: label });
      show();
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); if (q.value.trim()) shut(), look({ q: q.value.trim() }, q.value.trim()); });
  otherForm.addEventListener("submit", (e) => { e.preventDefault(); const g = other.value.trim().toLowerCase(); if (g) shut(), look({ tag: g }, g); });
  call("/v1/aurora/radio").then((s) => {
    mine = s.favourites;
    for (const p of s.presets) {
      const b = el("button", "", p.label);
      b.type = "button";
      b.addEventListener("click", () => { shut(); look({ tag: p.tag }, p.label); });
      presets.append(b);
    }
    const fams = (s.genres && s.genres.families) || [];
    const open = (f, chip) => {
      families.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === chip));
      genresRow.replaceChildren(...f.genres.map((g) => {
        const b = el("button", "", g.stations ? `${g.label} · ${g.stations}` : g.label);
        b.type = "button";
        b.addEventListener("click", () => look({ tag: g.tag }, g.label));
        return b;
      }));
    };
    for (const f of fams) {
      const chip = el("button", "cat-chip", f.label);
      chip.type = "button";
      chip.addEventListener("click", () => (chip.classList.contains("on") ? shut() : open(f, chip)));
      families.append(chip);
    }
    for (const tag of (s.genres && s.genres.more) || []) { const o = el("option"); o.value = tag; more.append(o); }
    show();
  }).catch(() => {});
  return box;
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The first run, five screens (ROADMAP 107): one question a screen in plain words — the name and the language, the
// access, how she reasons (the admin), the house, the look. Each screen starts from what is set NOW (the recommended
// answer only where nothing is), and saves only what was changed: going through it never undoes a setup. Once a person
// has seen it (any device), it does not open by itself again; the Appearance dialog opens it.
import { call } from "./api.js";
import { bus } from "./bus.js";
import { el } from "./dom.js";
import * as i18n from "./i18n.js";
import { applyTheme, current as currentTheme, THEMES } from "./theme.js";
import { current as currentStyle, setStyle, STYLES } from "./style.js";

const t = i18n.t;

export async function welcome(me, show) {
  const was = { name: me.person && me.person !== "Owner" ? me.person : "", lang: i18n.saved() };
  const want = { ...was, style: currentStyle(me.admin), theme: currentTheme(), house: "later" };
  const dlg = el("dialog", "modal welcome");
  dlg.setAttribute("aria-labelledby", "wl-q");
  let i = 0;
  let models = null;                                     // the admin's models, read once for screen 3
  let reason = { now: null, picked: null };
  let house = null;

  const choice = (items, picked, onPick) => {
    const box = el("div", "wl-choices");
    box.setAttribute("role", "radiogroup");
    for (const it of items) {
      const b = el("button", `wl-choice${it.id === picked ? " on" : ""}`);
      b.type = "button";
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(it.id === picked));
      const head = el("span", "wl-head");
      head.append(el("strong", "", it.label));
      if (it.tag) head.append(el("small", "wl-tag", it.tag));
      b.append(head, el("small", "muted", it.note || ""));
      b.addEventListener("click", () => { onPick(it.id); draw(); });
      box.append(b);
    }
    return box;
  };

  const screens = [
    () => {                                              // 1 · name and language
      const name = el("input");
      name.value = want.name;
      name.placeholder = t("wl.name_ph");
      name.autocomplete = "given-name";
      name.addEventListener("input", () => { want.name = name.value; });
      const label = el("label", "wl-label", t("wl.name"));
      label.append(name);
      return [label, choice([{ id: "it_IT", label: "Italiano" }, { id: "en_US", label: "English" }], want.lang, (id) => { want.lang = id; })];
    },
    () => {                                              // 2 · the access
      if (me.mode !== "multi") return [el("p", "", t("wl.access_single"))];
      const done = me.has_password && (!me.mfa || me.totp_on);
      return [el("p", done ? "ok" : "", t(done ? "wl.access_done" : "wl.access_todo"))];
    },
    () => {                                              // 3 · how she reasons
      if (!me.admin) return [el("p", "", t("wl.reason_user"))];
      if (!models) return [el("p", "muted", t("acc.checking"))];
      const items = ["local", "best", "cloud"].map((id) => ({ id, label: t(`mch.${id}`), tag: id === "best" ? t("mch.advised") : "",
        note: t(`wl.reason.${id}`) }));
      if (reason.now === "custom") items.push({ id: "custom", label: t("mch.custom"), tag: t("mm.now"), note: t("wl.reason.custom") });
      return [choice(items, reason.picked, (id) => { reason.picked = id; })];
    },
    () => {                                              // 4 · the house
      if (house === null) return [el("p", "muted", t("acc.checking"))];
      if (house > 0) return [el("p", "ok", t("wl.house_done", { n: house }))];
      return [choice([{ id: "now", label: t("wl.house_now"), tag: t("mch.advised"), note: t("wl.house_now_note") },
        { id: "later", label: t("wl.house_later"), note: t("wl.house_later_note") }], want.house, (id) => { want.house = id; })];
    },
    () => {                                              // 5 · the look: the style, then the colours
      const styles = choice(STYLES.map((id) => ({ id, label: t(`style.${id}`), note: t(`style.${id}.hint`) })), want.style,
        (id) => { want.style = id; setStyle(id); });
      const row = el("div", "theme-row");
      for (const th of THEMES) {
        const b = el("button", `theme-swatch${want.theme === th.id ? " on" : ""}`);
        b.type = "button";
        const dots = el("span", "dots");
        for (const c of th.dots) { const d = el("span"); d.style.background = c; dots.append(d); }
        b.append(dots, el("span", "", t(`theme.${th.id}`)));
        b.addEventListener("click", () => { want.theme = th.id; applyTheme(th.id, true); draw(); });
        row.append(b);
      }
      return [styles, el("h4", "", t("theme.colours")), row];
    },
  ];

  const out = el("p", "error wl-out");
  function draw() {
    const dots = el("div", "wl-dots");
    dots.setAttribute("aria-hidden", "true");
    for (let n = 0; n < 5; n++) dots.append(el("span", n <= i ? "on" : ""));
    const back = el("button", "", t("wl.back"));
    back.type = "button";
    back.disabled = i === 0;
    back.addEventListener("click", () => { i -= 1; out.textContent = ""; draw(); });
    const next = el("button", "approve", t(i === 4 ? "wl.start" : "wl.next"));
    next.type = "button";
    next.addEventListener("click", () => step(next));
    const bar = el("div", "wl-bar");
    bar.append(back, next);
    dlg.replaceChildren(dots, el("small", "muted", t("wl.count", { n: i + 1 })), el("h2", "", t(`wl.q${i + 1}`)),
      el("p", "muted", t(`wl.h${i + 1}`)), ...screens[i](), out, bar, el("small", "muted", t("wl.later")));
    dlg.querySelector("h2").id = "wl-q";
  }

  async function step(btn) {
    btn.disabled = true;
    out.textContent = "";
    try {
      if (i === 0) {                                     // saved only when changed
        if (want.name.trim() && want.name.trim() !== was.name) {
          await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify({ AURORA_OWNER_NAME: want.name.trim() }) });
          bus.emit("me-changed");
        }
        if (want.lang !== was.lang) { await i18n.load(want.lang); bus.emit("lang", { code: want.lang }); }
      }
      if (i === 2 && me.admin && models && reason.picked !== reason.now && reason.picked !== "custom") {
        const { useChoice } = await import("./modules/models_choice.js");
        await useChoice(reason.picked, models.m, models.s);
        reason.now = reason.picked;
      }
      if (i === 4) { await finish(); return; }
      i += 1;
      draw();
    } catch (e) { out.textContent = e.message; btn.disabled = false; }
  }

  async function finish() {
    try { await call("/v1/aurora/me/welcomed", { method: "POST" }); } catch { /* seen here at least */ }
    dlg.close();
    dlg.remove();
    if (me.mode === "multi" && !(me.has_password && (!me.mfa || me.totp_on))) show("users");   // the access first
    else if (house === 0 && want.house === "now") show("plugins");
    else show(want.style === "completo" ? "chat" : "today");
  }

  document.body.append(dlg);
  draw();
  dlg.showModal();
  dlg.addEventListener("cancel", (e) => e.preventDefault());           // Esc does not skip the first run by mistake
  // read together, each screen redrawn when its answer comes (the house can take seconds)
  const readModels = me.admin ? (async () => {
    const { choiceOf } = await import("./modules/models_presets.js");
    const [m, s] = await Promise.all([call("/v1/aurora/models"), call("/v1/aurora/models/modes")]);
    models = { m, s };
    reason.now = choiceOf(m.roles, s.mode);
    reason.picked = reason.now;
  })().catch(() => { models = null; }) : Promise.resolve();
  const readHouse = call("/v1/aurora/home/devices").then((d) => { house = d.devices.length; }).catch(() => { house = 0; });
  for (const p of [readModels, readHouse]) p.then(() => { if (dlg.open && (i === 2 || i === 3)) draw(); });
}

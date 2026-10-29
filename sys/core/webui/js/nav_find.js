// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔎 Search the menu (owner, 30 Oct: «un field cerca nel menù… quando si cerca qualcosa e non si ricorda dove si
// trova»): a word finds the pages whose title, area, words (nav.words.<id>: what a page is searched by, «password»
// on the users' page), headings or lead carry it; each found page is a button that opens it. A word of three letters
// or more also offers the settings filtered by it. Only the pages this person can open (usable: the role first).
import { el } from "./dom.js";
import * as i18n from "./i18n.js";

const MAX = 12;
const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// views, groups: modules.js; open(id): main.show; usable(v): the page shown to this person (not hidden in the menu)
export function navFind({ input, list, nav, views, groups, open, usable }) {
  const area = {};
  for (const g of groups) if (g.title) for (const id of g.views) area[id] = g;

  // what a page says of itself: title and area weigh more than what its page shows (headings, the lead line)
  function card(v) {
    const sec = document.getElementById(`view-${v.id}`);
    const heads = sec ? [...sec.querySelectorAll("h2, h3, h4")].map((h) => h.textContent.trim()).filter(Boolean) : [];
    const lead = sec?.querySelector("p.muted")?.textContent.trim() || "";
    const g = area[v.id];
    const key = `nav.words.${v.id}`;
    const words = i18n.t(key) === key ? "" : i18n.t(key);
    return { v, title: i18n.t(v.title), area: g ? `${g.icon} ${i18n.t(g.title)}` : "", words, heads, lead };
  }

  function search(q) {
    const words = fold(q).split(/\s+/).filter(Boolean);
    const out = [];
    for (const v of views) {
      if (!usable(v)) continue;
      const c = card(v);
      const fields = [[fold(c.title), 4], [fold(c.words), 3], [fold(c.area), 2], ...c.heads.map((h) => [fold(h), 1]), [fold(c.lead), 1]];
      let score = 0, where = "";
      const all = words.every((w) => fields.some(([f]) => f.includes(w)));
      if (!all) continue;
      for (const [f, wt] of fields) for (const w of words) if (f.includes(w)) score += wt * (f.startsWith(w) ? 2 : 1);
      if (!words.some((w) => fold(c.title).includes(w) || fold(c.words).includes(w))) {   // found inside the page: by what
        where = c.heads.find((h) => words.some((w) => fold(h).includes(w))) || c.lead;
      }
      out.push({ c, score, where });
    }
    return out.sort((a, b) => b.score - a.score).slice(0, MAX);
  }

  function row(icon, title, sub, go) {
    const b = el("button", "nav-found-row");
    b.type = "button";
    const txt = el("span", "label");
    txt.append(el("span", "", title));
    if (sub) txt.append(el("small", "muted", sub.length > 70 ? `${sub.slice(0, 69)}…` : sub));
    b.append(el("span", "ic", icon), txt);
    b.addEventListener("click", () => { input.value = ""; draw(); go(); });
    return b;
  }

  function draw() {
    const q = input.value.trim();
    nav.classList.toggle("hidden", !!q);
    list.classList.toggle("hidden", !q);
    if (!q) { list.replaceChildren(); return; }
    const found = search(q).map(({ c, where }) => row(c.v.icon, c.title, where || c.area, () => open(c.v.id)));
    if (!found.length) found.push(el("p", "muted nav-found-none", i18n.t("nav.find_none")));
    const settings = views.find((v) => v.id === "settings");
    if (q.length >= 3 && settings && usable(settings)) {
      found.push(row("⚙️", i18n.t("nav.find_settings", { q }), "", () => {
        open("settings");
        const f = document.querySelector("#view-settings .settings-filter");
        if (f) { f.value = q; f.dispatchEvent(new Event("input")); }
      }));
    }
    list.replaceChildren(...found);
  }

  // the browser's saved login is never written here (owner, 30 Oct: «c'è sempre selezionato <il nome di accesso> nella ricerca»):
  // a password manager fills no read-only field, so the field is read-only until it is touched; and a value the
  // browser put in all the same (:autofill) is wiped
  const editable = () => input.removeAttribute("readonly");
  input.addEventListener("focus", editable);
  input.addEventListener("pointerdown", editable);
  const filled = () => { try { return input.matches(":autofill"); } catch { return input.matches(":-webkit-autofill"); } };
  const wipe = () => { if (input.value && filled()) { input.value = ""; draw(); } };
  input.addEventListener("input", () => { if (filled()) { input.value = ""; } draw(); });
  input.addEventListener("blur", () => { if (!input.value) input.setAttribute("readonly", ""); });
  document.getElementById("menu")?.addEventListener("click", wipe);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && input.value) { e.stopPropagation(); input.value = ""; draw(); }
    if (e.key === "Enter") list.querySelector("button")?.click();
  });
}

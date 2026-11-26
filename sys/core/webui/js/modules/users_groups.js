// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 👥 Groups and access (owner, 27 Nov: «gli utenti inseribili in gruppi… l'accesso ai plugin… tramite la selezione
// utenti o tramite selezione gruppi»): the admin makes groups and decides, for each plugin and add-on, whether everyone
// may use it or only the users and groups chosen. The admin always may. A plugin is open by default, an add-on is not.
import { call } from "../api.js";
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";

// C753: el() takes a text only (dom.js); a box of elements is made here, its children appended
function make(tag, cls, ...kids) {
  const e = el(tag, cls);
  e.append(...kids.filter((k) => k !== null && k !== undefined));
  return e;
}

// the same pills as the rest of Aurora (🧠 Models' tabs, the categories): a click turns one on or off
function checks(names, chosen, cls) {
  return make("div", `prj-tabs ${cls}`, ...names.map((n) => {
    const b = el("button", `cat-chip${chosen.includes(n) ? " on" : ""}`, n);
    b.type = "button"; b.dataset.value = n;
    b.addEventListener("click", () => b.classList.toggle("on"));
    return b;
  }));
}
const picked = (box) => [...box.querySelectorAll(".cat-chip.on")].map((b) => b.dataset.value);

export async function renderGroups(box, accessBox = null) {
  const d = await call("/v1/aurora/users/groups");
  const groupsBox = el("div", "groups");
  for (const [name, members] of Object.entries(d.groups)) {
    const m = checks(d.users, members, "members");
    const save = el("button", "", t("groups.save"));
    const del = el("button", "danger", t("groups.delete"));
    save.addEventListener("click", async () => {
      await call(`/v1/aurora/users/groups/${encodeURIComponent(name)}`, { method: "PUT", body: JSON.stringify({ members: picked(m) }) });
      renderGroups(box, accessBox);
    });
    del.addEventListener("click", async () => {
      await call(`/v1/aurora/users/groups/${encodeURIComponent(name)}`, { method: "PUT", body: JSON.stringify({ delete: true }) });
      renderGroups(box, accessBox);
    });
    groupsBox.append(make("div", "card", el("b", "", `👥 ${name}`), m, make("div", "row", save, del)));
  }
  const newName = el("input");
  newName.placeholder = t("groups.new");
  const add = el("button", "", t("groups.add"));
  add.addEventListener("click", async () => {
    const n = newName.value.trim().toLowerCase();
    if (!n) return;
    try {
      await call(`/v1/aurora/users/groups/${encodeURIComponent(n)}`, { method: "PUT", body: JSON.stringify({ members: [] }) });
      renderGroups(box, accessBox);
    } catch (e) { newName.setCustomValidity(String(e.message || e)); newName.reportValidity(); }
  });
  groupsBox.append(make("div", "row", newName, add));

  // N165: by area, as the menu (life, home, work, chat…), then the connectors and tools (plugins in no feature)
  const accessList = el("div", "access");
  const AREAS = ["chat", "life", "home", "work", "admin", "tools"];
  const areaBox = {};
  for (const area of AREAS) {
    areaBox[area] = el("div", "access-area");
    areaBox[area].append(el("h3", "setting-cat", t(`groups.area.${area}`)));
  }
  for (const a of d.access) {
    const all = el("button", `cat-chip${a.all ? " on" : ""}`, t("groups.everyone"));
    all.type = "button";
    all.addEventListener("click", () => all.classList.toggle("on"));
    const users = checks(d.users, a.users || [], "users");
    const groups = Object.keys(d.groups).length ? checks(Object.keys(d.groups), a.groups || [], "groups")
      : el("p", "muted", t("groups.none"));          // no group yet: said, with where to make one
    const out = el("span", "muted");
    const save = el("button", "", t("groups.save"));
    save.addEventListener("click", async () => {
      try {
        await call(`/v1/aurora/access/${encodeURIComponent(a.feature)}`, { method: "PUT",
          body: JSON.stringify({ all: all.classList.contains("on"), users: picked(users), groups: picked(groups) }) });
        out.textContent = "✅";
      } catch (e) { out.textContent = `⚠️ ${e.message || e}`; }
    });
    const label = `${a.icon || "🔌"} ${(lang.startsWith("it") ? a.it : a.en) || a.feature}`;
    const allLabel = make("div", "prj-tabs", all);
    (areaBox[a.area] || areaBox.tools).append(make("details", "card", el("summary", "", `${label} — ${a.all ? t("groups.everyone") : t("groups.chosen")}${a.default ? ` (${t("groups.default")})` : ""}`),
      allLabel, el("p", "muted", t("groups.users")), users, el("p", "muted", t("groups.groups")), groups, make("div", "row", save, out)));
  }
  for (const area of AREAS) if (areaBox[area].children.length > 1) accessList.append(areaBox[area]);
  box.replaceChildren(el("p", "muted", t("groups.hint")), groupsBox);
  if (accessBox) accessBox.replaceChildren(el("p", "muted", t("groups.access_hint")), credBox(), accessList);
}

// 🔑 N167 (owner, 27 Nov: «togli le mie credenziali e token dagli altri utenti»): the admin's own accounts found, the
// same value, in another user's settings — names only — and emptied with a click
function credBox() {
  const box = make("div", "card cred-box", el("b", "", `🔑 ${t("cred.title")}`), el("p", "muted", t("cred.hint")));
  const out = el("div", "muted");
  const check = el("button", "", `🔍 ${t("cred.check")}`);
  check.addEventListener("click", async () => {
    out.textContent = "…";
    try {
      const { copies } = await call("/v1/aurora/users/credentials");
      const who = Object.entries(copies);
      if (!who.length) { out.textContent = `✅ ${t("cred.none")}`; return; }
      const clear = el("button", "danger", `🧹 ${t("cred.clear")}`);
      clear.addEventListener("click", async () => {
        clear.disabled = true;
        try { const r = await call("/v1/aurora/users/credentials/clear", { method: "POST", quiet: true }); out.textContent = `✅ ${t("cred.cleared", { n: Object.values(r.cleared).flat().length })}`; }
        catch (e) { out.textContent = `⚠️ ${e.message}`; }
      });
      out.replaceChildren(...who.map(([u, keys]) => el("div", "", `👤 ${u}: ${keys.join(", ")}`)), clear);
    } catch (e) { out.textContent = `⚠️ ${e.message}`; }
  });
  box.append(make("div", "row", check), out);
  return box;
}

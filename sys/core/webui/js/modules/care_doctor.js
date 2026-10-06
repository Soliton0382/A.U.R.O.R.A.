// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ⚕️ The doctors' cards (owner, 2026-10-06): the hours of the week, phone, address, how to book, notes — instead of
// looking for the photo of the hours in a chat. Sealed with the user's key (hlt_doctor); Aurora reads them locally.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat"];
const FIELDS = ["role", "name", "phone", "address", "booking"];

function input(value, placeholder, cls = "") {
  const i = el("input", cls);
  i.value = value || "";
  i.placeholder = placeholder;
  return i;
}

function card(c, today) {
  const box = el("details", "report doc-card");
  box.open = true;
  box.dataset.id = c.id || "";
  const title = [c.role, c.name].filter(Boolean).join(" — ") || t("care.doc.new");
  box.append(el("summary", "", `⚕️ ${title}${c.phone ? ` · 📞 ${c.phone}` : ""}`));
  const fields = el("div", "doc-fields");
  for (const f of FIELDS) {
    const i = input(c[f], t(`care.doc.${f}`));
    i.dataset.f = f;
    fields.append(i);
  }
  const table = el("table", "doc-hours");
  const head = el("tr");
  head.append(el("th", "", ""), el("th", "", t("care.doc.am")), el("th", "", t("care.doc.pm")));
  table.append(head);
  for (const d of DAYS) {
    const tr = el("tr", d === today ? "today" : "");
    tr.append(el("th", "", t(`care.doc.${d}`)));
    for (const p of ["am", "pm"]) {
      const td = el("td");
      const i = input(c.hours?.[d]?.[p], p === "am" ? "9:00–12:00" : "16:00–19:00");
      i.dataset.d = d;
      i.dataset.p = p;
      td.append(i);
      tr.append(td);
    }
    table.append(tr);
  }
  const notes = el("textarea", "doc-notes");
  notes.value = c.notes || "";
  notes.placeholder = t("care.doc.notes");
  const del = el("button", "danger", `🗑️ ${t("care.doc.remove")}`);
  del.type = "button";
  del.addEventListener("click", () => { if (confirm(t("care.doc.remove_q", { name: title }))) box.remove(); });
  box.append(fields, table, notes, el("div", "appr-actions"));
  box.lastChild.append(del);
  return box;
}

function read(box) {
  const c = { id: box.dataset.id, hours: {} };
  box.querySelectorAll("[data-f]").forEach((i) => { c[i.dataset.f] = i.value; });
  box.querySelectorAll("[data-d]").forEach((i) => { (c.hours[i.dataset.d] ??= {})[i.dataset.p] = i.value; });
  c.notes = box.querySelector(".doc-notes").value;
  return c;
}

export async function renderDoctors(root) {
  const today = DAYS[(new Date().getDay() + 6) % 7];        // Monday first; Sunday is none of them
  const list = el("div", "doc-list");
  const out = el("span", "muted");
  let doctors = [];
  try { ({ doctors } = await call("/v1/aurora/care/doctors")); }
  catch (e) { root.replaceChildren(el("p", "muted", t("ev.error", { m: e.message }))); return; }
  list.append(...doctors.map((c) => card(c, today)));
  const add = el("button", "", `➕ ${t("care.doc.add")}`);
  add.type = "button";
  add.addEventListener("click", () => list.append(card({ role: doctors.length ? "" : t("care.doc.family") }, today)));
  const save = el("button", "primary", `💾 ${t("care.doc.save")}`);
  save.type = "button";
  save.addEventListener("click", async () => {
    try {
      const r = await call("/v1/aurora/care/doctors", { method: "PUT", body: JSON.stringify({ doctors: [...list.children].map(read) }) });
      doctors = r.doctors;
      list.replaceChildren(...doctors.map((c) => card(c, today)));
      out.textContent = `✅ ${t("care.doc.saved")}`;
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
  });
  const bar = el("div", "appr-actions");
  bar.append(add, save, out);
  root.replaceChildren(list, bar);
  if (!doctors.length) add.click();                            // the first card ready to fill
}

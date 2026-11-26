// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ♻️ restore (owner, 2026-10-06; 27 Nov: «quei comandi mettiamoli nella sezione di backup e restore… si possa fare non
// solo da riga di comando ma anche dalla web ui»). Each copy with what goes back — parts and users as pills, the same
// command to copy for a terminal — and a ♻️ button that asks the password and the authenticator's code again, hands
// the request to root (aurora-restore) and waits for Aurora to come back with the result. Evidentia's copies apart.
import { call } from "./api.js";
import { el } from "./dom.js";
import { t } from "./i18n.js";

const MARK = { same: "✅", migrate: "🔄", unknown: "ℹ️", newer: "⛔" };

function pills(items, on = true) {
  const box = el("div", "prj-tabs");
  for (const [value, label] of items) {
    const b = el("button", `cat-chip${on ? " on" : ""}`, label);
    b.type = "button";
    b.dataset.value = value;
    b.addEventListener("click", () => { b.classList.toggle("on"); box.dispatchEvent(new Event("change")); });
    box.append(b);
  }
  return box;
}
const chosen = (box) => [...box.querySelectorAll(".cat-chip.on")].map((b) => b.dataset.value);
const all = (box) => box.querySelectorAll(".cat-chip").length === chosen(box).length;
// C753: el() takes a text only (dom.js): a row of elements is made here
function row(cls, ...kids) {
  const e = el("div", cls);
  e.append(...kids);
  return e;
}

// the password and the code, asked in the page (never a browser dialog)
function confirmBox(onGo) {
  const f = el("form", "ev restore-confirm");
  const pw = el("input");
  pw.type = "password"; pw.autocomplete = "current-password"; pw.placeholder = t("rs.password");
  const code = el("input");
  code.inputMode = "numeric"; code.autocomplete = "one-time-code"; code.placeholder = t("rs.code"); code.size = 8;
  const go = el("button", "danger", `♻️ ${t("rs.go")}`);
  go.type = "submit";
  const out = el("span", "muted");
  f.append(el("span", "", t("rs.confirm")), pw, code, go, out);
  f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    go.disabled = true;
    out.textContent = "…";
    try { await onGo({ password: pw.value, code: code.value.trim() }, out); }
    catch (e) { out.textContent = t("ev.error", { m: e.message }); go.disabled = false; }
  });
  return f;
}

// Aurora stops during a restore: the result is read again until she answers
async function follow(out) {
  out.textContent = t("rs.running");
  const t0 = Date.now();
  for (;;) {
    await new Promise((r) => setTimeout(r, 5000));
    let r = null;
    try { r = await call("/v1/aurora/backup/restore"); } catch { out.textContent = t("rs.away"); continue; }
    if (r && r.ok === true) { out.textContent = t("rs.done", { s: r.snapshot, aside: r.aside || "" }); return; }
    if (r && r.ok === false) { out.textContent = t("ev.error", { m: r.error || "?" }); return; }
    if (Date.now() - t0 > 6 * 3600e3) return;
  }
}

async function ask(body, out) {
  await call("/v1/aurora/backup/restore", { method: "POST", body: JSON.stringify(body) });
  follow(out);
}

function command(base, parts, users) {
  let c = base;
  if (parts && !all(parts)) c += ` --parts ${chosen(parts).join(",")}`;
  if (users && chosen(users).length) c += chosen(users).map((u) => ` --user ${u}`).join("");
  return c;
}

function auroraRow(r, users) {
  const wrap = el("div", "restore-row");
  const head = el("div", "ev");
  head.append(el("span", "ic", MARK[r.compat.verdict] || "•"), el("strong", "", r.snapshot),
    el("span", "muted", `${r.files} file · ${(r.bytes / 1e9).toFixed(1)} GB · ${t(`bk.v.${r.compat.verdict}`)}`));
  wrap.append(head);
  if (r.compat.verdict === "newer") { head.append(el("span", "error", r.compat.why)); return wrap; }
  const parts = pills(Object.entries(r.parts || {}).filter(([, v]) => v.files)
    .map(([name, v]) => [name, `${t(`bk.part.${name}`)} · ${(v.bytes / 1e9).toFixed(v.bytes < 1e8 ? 3 : 1)} GB`]));
  const who = pills(users.map((u) => [u, `👤 ${u}`]), false);
  const cmd = el("code", "restore-cmd");
  const show = () => { cmd.textContent = command(r.command, parts, who); };
  parts.addEventListener("change", show);
  who.addEventListener("change", show);
  show();
  const copy = el("button", "", `📋 ${t("bk.copy")}`);
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(cmd.textContent); copy.textContent = `✅ ${t("idea.copied")}`; } catch { /* shown already */ }
  });
  const open = el("button", "", `♻️ ${t("rs.here")}`);
  const slot = el("div");
  open.addEventListener("click", () => {
    if (!chosen(parts).length) return;
    slot.replaceChildren(confirmBox((cred, out) => ask({ kind: "aurora", snapshot: r.snapshot,
      parts: all(parts) ? [] : chosen(parts), users: chosen(who), ...cred }, out)));
  });
  wrap.append(el("p", "muted", t("rs.parts")), parts);
  if (users.length) wrap.append(el("p", "muted", t("rs.users")), who);
  wrap.append(row("ev", cmd, copy, open), slot);
  return wrap;
}

async function evidentiaBox() {
  const e = await call("/v1/aurora/backup/evidentia").catch(() => null);
  if (!e || !e.installed) return null;
  const box = el("div", "restore-evidentia");
  box.append(el("h4", "", `🕵️ ${t("rs.evidentia")}`), el("p", "muted", t("rs.evidentia_hint")));
  // a run of the code before the list (27 Nov) said only «ok»: its last copy is still there, as «latest»
  const names = e.snapshots.length ? e.snapshots : e.last?.ok ? ["latest"] : [];
  if (!names.length) { box.append(el("p", "muted", t("rs.evidentia_none"))); return box; }
  if (e.last?.ok) box.append(el("p", "muted", t("rs.evidentia_last", { d: new Date(e.last.at * 1000).toLocaleString(), n: e.last.files, gb: ((e.last.bytes || 0) / 1e9).toFixed(1) })));
  for (const s of names) {
    const cmd = el("code", "restore-cmd", e.command.replace("<copia>", s));
    const open = el("button", "", `♻️ ${t("rs.here")}`);
    const slot = el("div");
    open.addEventListener("click", () => slot.replaceChildren(confirmBox((cred, out) => ask({ kind: "evidentia", snapshot: s, ...cred }, out))));
    box.append(row("ev", el("strong", "", s === "latest" ? t("rs.latest") : s), cmd, open), slot);
  }
  return box;
}

export function restoreBox() {
  const d = el("details", "report");
  d.append(el("summary", "", `♻️ ${t("bk.restore")}`));
  const body = el("div");
  d.append(body);
  d.addEventListener("toggle", async () => {
    if (!d.open || body.dataset.done) return;
    body.dataset.done = "1";
    body.replaceChildren(el("p", "muted", t("bk.reading")));
    let rows;
    try { rows = await call("/v1/aurora/backup/snapshots"); } catch (e) { body.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
    const users = await call("/v1/aurora/users").then((x) => (x.users || []).map((u) => u.name)).catch(() => []);
    const last = await call("/v1/aurora/backup/restore").catch(() => ({}));
    body.replaceChildren(el("p", "muted", t("bk.selective")), el("p", "muted", t("rs.hint")));
    if (last && last.ok !== undefined) body.append(el("p", last.ok ? "muted" : "error",
      last.ok ? t("rs.last", { s: last.snapshot, k: last.kind }) : t("ev.error", { m: last.error || "?" })));
    // the newest copy open; the others under «copie precedenti» (ten copies open were a very long page)
    if (rows.length) body.append(auroraRow(rows[0], users));
    if (rows.length > 1) {
      const older = el("details", "restore-older");
      older.append(el("summary", "", t("rs.older", { n: rows.length - 1 })), ...rows.slice(1).map((r) => auroraRow(r, users)));
      body.append(older);
    }
    const evd = await evidentiaBox();
    if (evd) body.append(evd);
  });
  return d;
}

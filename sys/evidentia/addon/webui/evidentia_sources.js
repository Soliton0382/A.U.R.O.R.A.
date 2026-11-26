// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📥 The folders to read in, chosen here (R22; owner, 27 Nov: «dalla web ui selezionare le cartelle dove si trovano i
// file da ingerire»): the roots this installation names (the originals' folder, the NAS's), a folder walked by its
// names, what it holds, and «Ingerisci» — the inventory as a terminal runs it, one at a time, its progress read again
// while it runs. A document already in the archive found here only changes its path.
import { call } from "/static/js/api.js";
import { el } from "/static/js/dom.js";
import { t } from "/static/js/i18n.js";

const API = "/v1/aurora/evidentia/sources";
const n = (x) => Number(x || 0).toLocaleString();

function pill(label, on, click) {
  const b = el("button", `cat-chip${on ? " on" : ""}`, label);
  b.type = "button";
  b.addEventListener("click", click);
  return b;
}

export function sourcesCard() {
  const card = el("div", "evd-card evd-sources");
  card.append(el("h3", "", `📥 ${t("evd.src_title")}`), el("p", "muted", t("evd.src_hint")));
  const top = el("div", "prj-tabs");
  const crumbs = el("div", "evd-crumbs");
  const list = el("div", "evd-dirs");
  const what = el("p", "");
  const act = el("div", "ev");
  const state = el("div", "muted evd-ingest");
  card.append(top, crumbs, what, list, act, state);
  const at = { root: 0, path: "", images: false, roots: [] };
  let timer = null;

  const showState = (s) => {
    state.replaceChildren();
    if (!s) return;
    if (s.running) state.append(el("p", "", t("evd.src_running", { p: s.path || "/" })));
    for (const l of s.lines || []) state.append(el("div", "evd-code", l));
    clearTimeout(timer);
    if (s.running && card.isConnected !== false) timer = setTimeout(async () => showState(await call(`${API}/ingest`).catch(() => null)), 5000);
  };

  const go = async () => {
    list.replaceChildren(el("p", "muted", "…"));
    let d;
    try { d = await call(`${API}/browse?root=${at.root}&path=${encodeURIComponent(at.path)}`); }
    catch (e) { list.replaceChildren(el("p", "error", e.message)); return; }
    const parts = at.path ? at.path.split("/") : [];
    crumbs.replaceChildren(pill(`📂 ${t(`evd.src_root_${at.roots[at.root]?.kind || "nas"}`)}`, !parts.length, () => { at.path = ""; go(); }),
      ...parts.map((p, i) => pill(p, i === parts.length - 1, () => { at.path = parts.slice(0, i + 1).join("/"); go(); })));
    what.textContent = t("evd.src_holds", { pdf: n(d.pdfs), img: n(d.images), other: n(d.other), dirs: n(d.dirs.length + d.more_dirs) });
    list.replaceChildren(...d.dirs.map((x) => pill(`📁 ${x}`, false, () => { at.path = at.path ? `${at.path}/${x}` : x; go(); })));
    if (d.more_dirs) list.append(el("span", "muted", t("evd.src_more", { n: n(d.more_dirs) })));
    const img = pill(`🖼️ ${t("evd.src_images")}`, at.images, () => { at.images = !at.images; img.classList.toggle("on", at.images); });
    const read = el("button", "approve", `📥 ${t("evd.src_read")}`);
    read.disabled = !(d.pdfs || d.images);
    read.addEventListener("click", async () => {
      read.disabled = true;
      try { showState(await call(`${API}/ingest`, { method: "POST", quiet: true, body: JSON.stringify({ root: at.root, path: at.path, images: at.images }) })); }
      catch (e) { state.replaceChildren(el("p", "error", e.message)); read.disabled = false; }
    });
    act.replaceChildren(img, read);
  };

  (async () => {
    let r;
    try { r = await call(API); } catch (e) { card.append(el("p", "error", e.message)); return; }
    const me = await call("/v1/aurora/me").catch(() => ({ admin: true }));
    if (!me.admin) card.append(nasForm());                // N168: a user's own NAS folder (the admin's: at install)
    at.roots = r.roots;
    if (!r.roots.length) { what.textContent = t("evd.src_none"); return; }
    top.replaceChildren(...r.roots.map((x) => pill(`${x.reachable ? "✅" : "⚠️"} ${t(`evd.src_root_${x.kind}`)}`, x.id === at.root,
      () => { at.root = x.id; at.path = ""; [...top.children].forEach((b, i) => b.classList.toggle("on", i === x.id)); go(); })));
    const first = r.roots.find((x) => x.reachable);
    if (first) { at.root = first.id; [...top.children].forEach((b, i) => b.classList.toggle("on", i === first.id)); go(); }
    else what.textContent = t("evd.src_unreachable");
    showState(r.ingest);
  })();
  card.dataset.busy = "";                             // never redrawn away while a folder is chosen (main.js, C757)
  return card;
}

// 🔗 N168 (owner, 27 Nov: «è importante che ognuno possa collegare il percorso che vuole»): this user's own NAS folder,
// mounted read only by root for Evidentia; the password goes to root's credentials file, never kept here
function nasForm() {
  const box = el("details", "evd-nas");
  box.append(el("summary", "", `🔗 ${t("evd.nas_title")}`), el("p", "muted", t("evd.nas_hint")));
  const url = el("input"); url.placeholder = "smb://nas.example/condivisione/cartella"; url.autocomplete = "off";
  const user = el("input"); user.placeholder = t("evd.nas_user"); user.autocomplete = "off";
  const pw = el("input"); pw.type = "password"; pw.placeholder = t("evd.nas_password"); pw.autocomplete = "new-password";
  const go = el("button", "approve", t("evd.nas_go"));
  const out = el("p", "muted");
  const say = async () => {
    const s = await call("/v1/aurora/evidentia-nas").catch(() => ({}));
    out.textContent = s.ok ? t("evd.nas_ok", { n: s.folders ?? 0 }) : s.error ? `⚠️ ${s.error}` : "";
  };
  go.addEventListener("click", async () => {
    go.disabled = true;
    out.textContent = "…";
    try {
      await call("/v1/aurora/evidentia-nas", { method: "POST", quiet: true, body: JSON.stringify({ url: url.value.trim(), nas_user: user.value, password: pw.value }) });
      pw.value = "";
      setTimeout(say, 8000);                           // root mounts it meanwhile
    } catch (e) { out.textContent = `⚠️ ${e.message}`; }
    go.disabled = false;
  });
  const row = el("div", "ev");
  row.append(url, user, pw, go);
  box.append(row, out);
  say();
  return box;
}

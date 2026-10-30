// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🪪 The people of this Aurora (sys_people, api/people; owner, 30 Oct): my card — its fields, each with whether the
// others see it —, my biography with Aurora's proposals from my own memories (a line enters with my yes), the
// relations asked and confirmed by both, and the others' cards as they let me see them.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";

const FIELDS = [["name", "text"], ["birth", "date"], ["city", "text"], ["work", "text"]];
const STYLES = ["watercolor", "cartoon", "anime", "pixel", "oil", "3d", "space"];
const pic = (user, kind = "") => `/v1/aurora/people/${encodeURIComponent(user)}/picture?${kind ? `kind=${kind}&` : ""}t=${Date.now()}`;

export default {
  id: "people",
  icon: "🪪",
  title: "nav.people",

  mount(root) {
    useCss("/static/css/people.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.people"></h2><p class="muted" data-i18n="ppl.lead"></p>
      <div class="ppl-asks"></div>
      <h3 class="setting-cat" data-i18n="ppl.mine"></h3><div class="ppl-pic"></div><form class="ppl-card"></form>
      <h3 class="setting-cat" data-i18n="ppl.bio"></h3><p class="muted" data-i18n="ppl.bio_hint"></p><div class="ppl-bio"></div>
      <h3 class="setting-cat" data-i18n="ppl.relations"></h3><div class="ppl-rel"></div>
      <h3 class="setting-cat" data-i18n="ppl.others"></h3><div class="ppl-grid"></div>`;
    apply(root);
    this.root = root;
  },

  async send(path, method, body) {
    try { this.draw(await call(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) })); }
    catch (e) { alert(e.message); }
  },

  async enter() { this.draw(await call("/v1/aurora/people")); },

  draw(v) {
    this.v = v;
    const mine = v.cards[v.me] || {};
    const code = lang.slice(0, 2);
    const kind = (k, back = false) => (v.kinds[k] || {})[back ? `${code}_back` : code] || k;
    const others = Object.values(v.cards).filter((c) => c.user !== v.me);
    // what waits for my answer: a relation another said
    const asks = v.relations.filter((r) => r.state === "pending" && r.b === v.me);
    this.root.querySelector(".ppl-asks").replaceChildren(...asks.map((r) => {
      const row = el("div", "ppl-ask");
      row.append(el("span", "", t("ppl.ask", { who: r.a, what: kind(r.kind) })));
      for (const yes of [true, false]) {
        const b = el("button", yes ? "primary" : "", yes ? `✔ ${t("ppl.confirm")}` : `✘ ${t("ppl.refuse")}`);
        b.type = "button";
        b.addEventListener("click", () => this.send(`/v1/aurora/people/relations/${r.id}`, "POST", { yes }));
        row.append(b);
      }
      return row;
    }));
    this.drawPicture(v, mine);
    // my card: each field with its «visible to the others»
    const form = this.root.querySelector(".ppl-card");
    const vis = mine.visible || {};
    const rows = FIELDS.map(([k, type]) => {
      const l = el("div", "ppl-field");
      const i = el("input");
      i.name = k;
      i.type = type;
      i.value = mine[k] || "";
      i.placeholder = t(`ppl.f.${k}_ph`);
      const eye = el("label", "ppl-eye");
      const c = el("input");
      c.type = "checkbox";
      c.name = `v_${k}`;
      c.checked = k === "name" ? true : !!vis[k];
      c.disabled = k === "name";
      eye.append(c, el("span", "", t("ppl.visible")));
      l.append(el("span", "ppl-label", t(`ppl.f.${k}`)), i, eye);
      return l;
    });
    const social = el("div", "ppl-field");
    const links = el("textarea");
    links.name = "social";
    links.rows = 2;
    links.placeholder = t("ppl.f.social_ph");
    links.value = (mine.social || []).map((s) => (s.label ? `${s.label} ${s.url}` : s.url)).join("\n");
    const eye = el("label", "ppl-eye");
    const sc = el("input");
    sc.type = "checkbox";
    sc.name = "v_social";
    sc.checked = !!vis.social;
    eye.append(sc, el("span", "", t("ppl.visible")));
    social.append(el("span", "ppl-label", t("ppl.f.social")), links, eye);
    const save = el("button", "primary", `💾 ${t("ppl.save")}`);
    save.type = "submit";
    const out = el("span", "muted");
    const bar = el("div", "appr-actions");
    bar.append(save, out);
    form.replaceChildren(...rows, social, bar);
    form.onsubmit = async (ev) => {
      ev.preventDefault();
      const body = { visible: {} };
      for (const [k] of FIELDS) {
        body[k] = form.elements[k].value;
        if (k !== "name") body.visible[k] = form.elements[`v_${k}`].checked;
      }
      body.visible.social = form.elements.v_social.checked;
      body.social = links.value.split("\n").map((x) => x.trim()).filter(Boolean).map((x) => {
        const m = x.match(/^(.*?)\s*(https:\/\/\S+)$/);
        return m ? { label: m[1], url: m[2] } : { label: "", url: x };
      });
      try { this.draw(await call("/v1/aurora/people/me", { method: "PUT", body: JSON.stringify(body) })); out.textContent = t("ppl.saved"); }
      catch (e) { out.textContent = e.message; }
    };
    // my biography: my lines, my yes to Aurora's proposals
    const bio = el("div", "ppl-bio-box");
    for (const b of mine.bio || []) {
      const row = el("div", "ppl-line");
      const x = el("button", "", "🗑️");
      x.type = "button";
      x.addEventListener("click", () => this.send(`/v1/aurora/people/me/bio/${b.id}`, "DELETE"));
      row.append(el("span", "", b.text), x);
      bio.append(row);
    }
    const bioVis = el("label", "ppl-eye");
    const bv = el("input");
    bv.type = "checkbox";
    bv.checked = !!vis.bio;
    bv.addEventListener("change", () => this.send("/v1/aurora/people/me", "PUT", { visible: { bio: bv.checked } }));
    bioVis.append(bv, el("span", "", t("ppl.bio_visible")));
    const add = el("form", "appr-actions ppl-bio-add");
    const line = el("textarea");                      // a short paragraph, up to 600 characters (owner, 30 Oct)
    line.rows = 3;
    line.maxLength = 600;
    line.placeholder = t("ppl.bio_ph");
    const go = el("button", "", t("ppl.add"));
    go.type = "submit";
    add.append(line, go);
    add.addEventListener("submit", (ev) => { ev.preventDefault(); if (line.value.trim()) this.send("/v1/aurora/people/me/bio", "POST", { text: line.value }); });
    const propose = el("button", "", `💡 ${t("ppl.propose")}`);
    propose.type = "button";
    const said = el("span", "muted");
    propose.addEventListener("click", async () => {
      propose.disabled = true;
      propose.textContent = `⏳ ${t("ppl.proposing")}`;
      try {
        const r = await call("/v1/aurora/people/me/propose", { method: "POST", body: "{}" });
        this.draw(r);                                   // and say what came of it: «nothing happens» was 0 lines unsaid
        const box = this.root.querySelector(".ppl-propose-said");
        if (box) box.textContent = r.why === "no_memories" ? t("ppl.prop_none_mem") : r.proposed ? t("ppl.prop_n", { n: r.proposed })
          : r.found ? t("ppl.prop_known") : t("ppl.prop_none");
      } catch (e) { propose.disabled = false; propose.textContent = `💡 ${t("ppl.propose")}`; said.textContent = e.message; }
    });
    said.className = "muted ppl-propose-said";
    bio.append(bioVis, add, propose, said);
    for (const p of mine.proposals || []) {
      const row = el("div", "ppl-line ppl-proposal");
      row.append(el("span", "", `💡 ${p.text}`));
      for (const yes of [true, false]) {
        const b = el("button", yes ? "primary" : "", yes ? "✔" : "✘");
        b.type = "button";
        b.title = yes ? t("ppl.keep") : t("ppl.never");
        b.addEventListener("click", () => this.send(`/v1/aurora/people/me/proposals/${p.id}`, "POST", { yes }));
        row.append(b);
      }
      bio.append(row);
    }
    this.root.querySelector(".ppl-bio").replaceChildren(bio);
    // the relations: confirmed, asked by me and waiting, and a new one
    const rel = el("div", "ppl-rel-box");
    for (const r of v.relations.filter((x) => x.a === v.me || x.b === v.me)) {
      const other = r.a === v.me ? r.b : r.a;
      const row = el("div", "ppl-line");
      const said = r.a === v.me ? t("ppl.i_am", { what: kind(r.kind), who: other }) : t("ppl.is_me", { who: other, what: kind(r.kind) });
      const x = el("button", "", "🗑️");
      x.type = "button";
      x.addEventListener("click", () => { if (confirm(t("ppl.drop_q"))) this.send(`/v1/aurora/people/relations/${r.id}`, "DELETE"); });
      row.append(el("span", "", `${r.state === "confirmed" ? "✅" : "⏳"} ${said}`), x);
      rel.append(row);
    }
    if (others.length) {
      const f = el("form", "appr-actions");
      const what = el("select");
      for (const k of Object.keys(v.kinds)) { const o = el("option", "", kind(k)); o.value = k; what.append(o); }
      const who = el("select");
      for (const c of others) { const o = el("option", "", c.name || c.user); o.value = c.user; who.append(o); }
      const go2 = el("button", "", t("ppl.ask_btn"));
      go2.type = "submit";
      f.append(el("span", "", t("ppl.i_am_pre")), what, el("span", "", t("ppl.of")), who, go2);
      f.addEventListener("submit", (ev) => { ev.preventDefault(); this.send("/v1/aurora/people/relations", "POST", { to: who.value, kind: what.value }); });
      rel.append(f);
    } else rel.append(el("p", "muted", t("ppl.alone")));
    this.root.querySelector(".ppl-rel").replaceChildren(rel);
    // the others, as they let me see them
    this.root.querySelector(".ppl-grid").replaceChildren(...(others.length ? others.map((c) => {
      const tile = el("div", "ppl-tile");
      if (c.picture) { const img = el("img", "ppl-face"); img.src = pic(c.user); img.alt = ""; tile.append(img); }
      tile.append(el("strong", "", `${c.admin ? "🛠️ " : "👤 "}${c.name || c.user}`));
      if (c.admin) tile.append(el("span", "muted", t("ppl.creator")));
      for (const r of v.relations.filter((x) => x.state === "confirmed" && (x.a === c.user || x.b === c.user) && (x.a === v.me || x.b === v.me))) {
        tile.append(el("span", "", `👥 ${r.a === c.user ? kind(r.kind) : kind(r.kind, true)}`));   // what they are to me
      }
      if (c.birth) tile.append(el("span", "", `🎂 ${c.birth.split("-").reverse().join("/")}`));
      if (c.city) tile.append(el("span", "", `📍 ${c.city}`));
      if (c.work) tile.append(el("span", "", `💼 ${c.work}`));
      for (const s of c.social || []) { const a = el("a", "", `🔗 ${s.label || s.url}`); a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer"; tile.append(a); }
      for (const b of c.bio || []) tile.append(el("span", "muted", `· ${b.text}`));
      return tile;
    }) : [el("p", "muted", t("ppl.alone"))]));
  },

  // 🖼️ my picture: a photo I give, an avatar Aurora makes (from the photo or from words, local models only), which
  // one my card shows, and whether the others see it (owner, 30 Oct: «il profilo classico… la foto… un avatar»)
  drawPicture(v, mine) {
    const box = el("div", "ppl-pic-box");
    const face = el("div", "ppl-face-big");
    if (mine.picture) { const img = el("img"); img.src = pic(v.me, mine.picture); img.alt = ""; face.append(img); }
    else face.append(el("span", "", "👤"));
    const tools = el("div", "ppl-pic-tools");
    const up = el("label", "ppl-upload");
    const file = el("input");
    file.type = "file";
    file.accept = "image/jpeg,image/png,image/webp";
    file.hidden = true;
    up.append(el("span", "", `📷 ${t("ppl.photo_up")}`), file);
    file.addEventListener("change", async () => {
      const f = file.files[0];
      if (!f) return;
      try { this.draw(await call("/v1/aurora/people/me/photo", { method: "PUT", body: f, headers: { "Content-Type": f.type || "application/octet-stream" } })); }
      catch (e) { alert(e.message); }
    });
    const show = el("div", "ppl-show");
    for (const k of ["photo", "avatar", ""]) {
      if (k && !(mine.pictures || []).includes(k)) continue;
      const l = el("label", "ppl-eye");
      const r = el("input");
      r.type = "radio";
      r.name = "ppl-show";
      r.checked = (mine.picture || "") === k;
      r.addEventListener("change", () => this.send("/v1/aurora/people/me/picture", "POST", { use: k }));
      l.append(r, el("span", "", t(`ppl.show.${k || "none"}`)));
      show.append(l);
    }
    const eye = el("label", "ppl-eye");
    const ev = el("input");
    ev.type = "checkbox";
    ev.checked = !!(mine.visible || {}).picture;
    ev.addEventListener("change", () => this.send("/v1/aurora/people/me", "PUT", { visible: { picture: ev.checked } }));
    eye.append(ev, el("span", "", t("ppl.pic_visible")));
    // the avatar
    const av = el("form", "appr-actions ppl-avatar");
    const style = el("select");
    for (const s of STYLES) { const o = el("option", "", t(`ppl.style.${s}`)); o.value = s; style.append(o); }
    const from = el("label", "ppl-eye");
    const fp = el("input");
    fp.type = "checkbox";
    fp.checked = (mine.pictures || []).includes("photo");
    fp.disabled = !fp.checked;
    from.append(fp, el("span", "", t("ppl.from_photo")));
    const words = el("input");
    words.placeholder = t("ppl.avatar_words");
    const go = el("button", "", `🎨 ${t("ppl.avatar_go")}`);
    go.type = "submit";
    const out = el("span", "muted");
    av.append(style, from, words, go, out);
    av.addEventListener("submit", async (e) => {
      e.preventDefault();
      go.disabled = true;
      out.textContent = `⏳ ${t("ppl.avatar_wait")}`;
      try { this.draw(await call("/v1/aurora/people/me/avatar", { method: "POST", body: JSON.stringify({ style: style.value, from_photo: fp.checked, words: words.value }) })); }
      catch (err) { out.textContent = err.message; go.disabled = false; }
    });
    tools.append(up, show, eye, av, el("p", "muted", t("ppl.avatar_hint")));
    box.append(face, tools);
    this.root.querySelector(".ppl-pic").replaceChildren(box);
  },
};

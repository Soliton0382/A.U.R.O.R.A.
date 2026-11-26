// 🕸️ Evidentia's web (this installation's own, never published; owner, 10 Nov: «sarebbe carino vedere la ragnatela
// nella WebUI di aurora»): who wrote to whom, drawn. A name gives its node and its documented ties (Evidentia's
// network: e-mail headers only, each tie of a kind — wrote_to, copied); a click on a node moves laterally (its own
// ties join the drawing); a click on a tie lists the messages it is made of, each opening its page; two names give
// the shortest chain. A private person is a grey dot with a label, never expanded, never named.
import { call } from "/static/js/api.js";
import { el, useCss } from "/static/js/dom.js";
import { t } from "/static/js/i18n.js";
import { API, citeButton, seenButton } from "./evidentia_view.js";
import { pack } from "./evidentia_pack.js";

const SVG = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const MAX_NODES = 160;

export default {
  id: "evd_net",
  adminOnly: true,
  icon: "🕸️",
  title: "nav.evd_net",

  mount(root) {
    root.classList.add("page");
    useCss("/static/addons/evidentia/evidentia.css");
    this.nodes = new Map();          // key → {key, name, public, x, y, vx, vy, open, size}
    this.links = new Map();          // "a|b" → {a, b, kinds:Set, n}
    const bar = el("form", "evd-bar");
    this.who = Object.assign(el("input"), { placeholder: t("evd.net_who"), style: "min-width:14rem" });
    const go = el("button", "approve", `🔎 ${t("evd.net_go")}`);
    this.to = Object.assign(el("input"), { placeholder: t("evd.net_to"), style: "min-width:12rem" });
    const chain = el("button", "", `🧵 ${t("evd.net_chain")}`);
    chain.type = "button";
    const clear = el("button", "", `🧹 ${t("evd.net_clear")}`);
    clear.type = "button";
    const give = el("button", "", `📦 ${t("evd.pack_title")}`);   // the web handed to the investigation (12 Nov)
    give.type = "button";
    give.addEventListener("click", () => pack(this));
    bar.append(this.suggest(this.who, (name) => this.start(name)), go,
      this.suggest(this.to, () => this.chain(this.who.value, this.to.value)), chain, clear, give);
    bar.addEventListener("submit", (e) => { e.preventDefault(); this.start(this.who.value); });
    chain.addEventListener("click", () => this.chain(this.who.value, this.to.value));
    clear.addEventListener("click", () => this.reset());
    this.status = el("p", "muted", t("evd.net_hint"));
    const wrap = el("div", "evd-net");
    this.svg = svgEl("svg", { class: "evd-net-svg", viewBox: "-500 -320 1000 640" });
    this.side = el("div", "evd-card evd-net-side");
    const stage = el("div", "evd-net-stage");
    const zoom = el("div", "evd-net-zoom");
    for (const [label, f] of [["＋", 0.8], ["−", 1.25], ["⟲", 0]]) {
      const b = el("button", "", label);
      b.type = "button";
      b.addEventListener("click", () => (f ? this.zoomBy(f) : this.fit()));
      zoom.append(b);
    }
    stage.append(this.svg, zoom);
    wrap.append(stage, this.side);
    this.pannable();
    root.append(el("h2", "", `🕸️ ${t("nav.evd_net")}`), bar, this.status, wrap,
      el("p", "muted", t("evd.net_legend")));
  },

  enter() { if (!this.nodes.size) this.draw(); },

  // a field that proposes the people who fit while one types (owner, 10 Nov: «come il campo ricerca, mentre scrivi ti
  // propone nomi… così uno clicca quello che vuole»): a short pause after the last key, then the network's people
  suggest(input, picked) {
    const wrap = el("span", "evd-ac");
    const list = el("div", "evd-ac-list");
    list.hidden = true;
    let timer = 0, asked = "";
    const close = () => { list.hidden = true; };
    input.setAttribute("autocomplete", "off");
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) { close(); return; }
      timer = setTimeout(async () => {
        asked = q;
        let people = [];
        try { ({ people } = await call(`${API}/network/people?q=${encodeURIComponent(q)}&n=8`)); } catch { /* none */ }
        if (asked !== input.value.trim()) return;           // typed on meanwhile: an older answer
        list.replaceChildren(...people.map((p) => {
          const b = el("button", "evd-item");
          b.type = "button";
          b.append(el("span", "", `👤 ${p.name}`), el("small", "", t("evd.net_person", { p: p.peers, d: p.docs })));
          b.addEventListener("mousedown", (ev) => { ev.preventDefault(); input.value = p.name; close(); picked(p.name); });
          return b;
        }));
        list.hidden = !people.length;
      }, 250);
    });
    input.addEventListener("blur", () => setTimeout(close, 150));
    input.addEventListener("keydown", (ev) => { if (ev.key === "Escape") close(); });
    wrap.append(input, list);
    return wrap;
  },

  // zoom and pan like the traceroute's globe (owner, 10 Nov: «la rete la farei zoomabile… come il traceroute in
  // security»): the wheel or two fingers zoom where they point, the background dragged moves, a double click fits all
  view(vb) {
    this.vb = vb;
    this.svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  },

  zoomBy(f, cx, cy) {
    const vb = this.vb || { x: -500, y: -320, w: 1000, h: 640 };
    const w = Math.max(120, Math.min(vb.w * f, 8000)), h = w * vb.h / vb.w;
    const px = cx ?? vb.x + vb.w / 2, py = cy ?? vb.y + vb.h / 2;
    this.view({ x: px - (px - vb.x) * w / vb.w, y: py - (py - vb.y) * h / vb.h, w, h });
  },

  fit() {
    const ns = [...this.nodes.values()];
    if (!ns.length) { this.view({ x: -500, y: -320, w: 1000, h: 640 }); return; }
    const xs = ns.map((n) => n.x), ys = ns.map((n) => n.y);
    const x0 = Math.min(...xs) - 80, x1 = Math.max(...xs) + 160, y0 = Math.min(...ys) - 60, y1 = Math.max(...ys) + 60;
    const w = Math.max(x1 - x0, (y1 - y0) * 1000 / 640, 400);
    this.view({ x: (x0 + x1) / 2 - w / 2, y: (y0 + y1) / 2 - w * 0.32, w, h: w * 0.64 });
  },

  point(ev) {
    const pt = this.svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    return pt.matrixTransform(this.svg.getScreenCTM().inverse());
  },

  pannable() {
    const touches = new Map();
    let pan = null, pinch = null;
    this.svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const p = this.point(e);
      this.zoomBy(Math.exp(e.deltaY * 0.0015), p.x, p.y);
    }, { passive: false });
    this.svg.addEventListener("dblclick", (e) => { if (e.target === this.svg) this.fit(); });
    this.svg.addEventListener("pointerdown", (e) => {
      touches.set(e.pointerId, e);
      if (touches.size === 2) {
        const [a, b] = [...touches.values()];
        pinch = { d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY), vb: { ...this.vb } };
        pan = null;
      } else if (e.target === this.svg) {
        pan = { x: e.clientX, y: e.clientY, vb: { ...(this.vb || { x: -500, y: -320, w: 1000, h: 640 }) } };
      }
    });
    this.svg.addEventListener("pointermove", (e) => {
      if (!touches.has(e.pointerId)) return;
      touches.set(e.pointerId, e);
      if (pinch && touches.size === 2) {
        const [a, b] = [...touches.values()];
        const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        this.view(pinch.vb);
        this.zoomBy(pinch.d / Math.max(d, 1));
      } else if (pan) {
        const k = pan.vb.w / this.svg.clientWidth;
        this.view({ ...pan.vb, x: pan.vb.x - (e.clientX - pan.x) * k, y: pan.vb.y - (e.clientY - pan.y) * k });
      }
    });
    const end = (e) => { touches.delete(e.pointerId); if (touches.size < 2) pinch = null; if (!touches.size) pan = null; };
    this.svg.addEventListener("pointerup", end);
    this.svg.addEventListener("pointercancel", end);
  },

  reset() {
    cancelAnimationFrame(this.raf);
    this.nodes.clear(); this.links.clear(); this.draw(); this.side.replaceChildren();
  },

  node(p, at) {
    const k = p.key || p.name;
    if (!this.nodes.has(k)) {
      const a = Math.random() * Math.PI * 2, r = at ? 60 : 0;
      this.nodes.set(k, { key: p.key, name: p.name, public: p.public !== false || p.asked === true, open: false, size: 1,
        x: (at?.x || 0) + Math.cos(a) * r, y: (at?.y || 0) + Math.sin(a) * r, vx: 0, vy: 0 });
    }
    return this.nodes.get(k);
  },

  link(a, b, kind, n) {
    const id = [a.key || a.name, b.key || b.name].sort().join("|");
    const l = this.links.get(id) || { a, b, kinds: new Set(), n: 0 };
    l.kinds.add(kind.replace(/_by$/, ""));
    l.n += n;
    this.links.set(id, l);
    a.size = Math.max(a.size, Math.log2(2 + l.n));
    b.size = Math.max(b.size, Math.log2(2 + l.n));
  },

  async start(name) {
    if (!name.trim()) return;
    this.reset();
    await this.expand(name.trim(), null);
  },

  // a lateral move: the person's ties join the drawing
  async expand(name, from) {
    this.status.textContent = "…";
    const res = await fetch(`${API}/network/contacts?name=${encodeURIComponent(name)}&n=24`, { credentials: "same-origin" });
    const r = await res.json().catch(() => ({}));
    if (res.status === 300 || (!res.ok && !from)) {      // a part of a name (owner, 10 Nov: «anche solo un nome o un
      return this.choose(name, r.candidates);           // cognome o suffissi come president»): who fits, to choose
    }
    if (!res.ok) { this.status.textContent = t("evd.off", { m: r.detail || res.status }); return; }
    const me = this.node(r.person, from);
    me.open = true;
    for (const c of r.contacts) {
      if (this.nodes.size >= MAX_NODES && !this.nodes.has(c.key || c.name)) break;
      this.link(me, this.node(c, me), c.tie, c.messages);
    }
    this.status.textContent = t("evd.net_count", { n: this.nodes.size, l: this.links.size }) +
      (r.protected_left_out ? ` · ${t("evd.net_protected", { n: r.protected_left_out })}` : "");
    this.show(me, r);
    this.settle();
  },

  // the people a part of a name fits, most documented first: one click and their web
  async choose(part, candidates) {
    let list = candidates;
    if (!list) {
      try { ({ people: list } = await call(`${API}/network/people?q=${encodeURIComponent(part)}&n=20`)); } catch { list = []; }
    }
    this.status.textContent = list.length ? t("evd.net_choose", { n: list.length }) : t("evd.net_nobody");
    const box = this.side;
    box.replaceChildren(el("h3", "", `🔎 ${part}`));
    for (const p of list) {
      const b = el("button", "evd-item");
      b.append(el("span", "", `👤 ${p.name}`), el("small", "", t("evd.net_person", { p: p.peers, d: p.docs })));
      b.addEventListener("click", () => { this.who.value = p.name; this.start(p.name); });
      box.append(b);
    }
  },

  async chain(a, b) {
    if (!a.trim() || !b.trim()) return;
    let r;
    try { r = await call(`${API}/network/path?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&depth=3`); } catch (e) {
      this.status.textContent = t("evd.off", { m: e.message }); return;
    }
    if (!r.chain.length) { this.status.textContent = t("evd.net_nochain"); return; }
    this.reset();
    let prev = this.node({ ...r.a, key: r.a.key });
    for (const step of r.chain) {
      const next = this.node({ name: step.to, key: step.to === r.b.name ? r.b.key : undefined }, prev);
      this.link(prev, next, step.tie, 1);
      prev = next;
    }
    const box = this.side;
    box.replaceChildren(el("h3", "", `🧵 ${r.a.name} → ${r.b.name}`));
    for (const s of r.chain) {
      const row = el("div", "evd-lead");
      row.append(el("div", "", `${s.from} → ${s.to} · ${t(`evd.tie_${s.tie}`)}${s.day ? ` · ${s.day}` : ""}`),
        citeButton({ doc: s.doc, page: s.page, cite: `${s.doc.split(":")[1]} p. ${s.page}` }));
      box.append(row);
    }
    this.status.textContent = t("evd.net_chain_found", { n: r.chain.length });
    this.settle();
  },

  // the side card: a person and their ties, each with where it is seen
  show(n, r) {
    const box = this.side;
    box.replaceChildren(el("h3", "", `👤 ${n.name}`));
    if (r) {
      box.append(el("p", "muted", t("evd.net_person", { p: r.person.peers || 0, d: r.person.docs || 0 })));
      for (const c of r.contacts.slice(0, 14)) {
        const row = el("div", "evd-lead");
        row.append(el("div", "", `${c.name} · ${t(`evd.tie_${c.tie}`)} · ${c.messages}` + (c.first ? ` · ${c.first} → ${c.last}` : "")),
          ...c.seen_in.map(seenButton));
        box.append(row);
      }
    }
  },

  async tie(l) {
    if (!l.a.public || !l.b.public) { this.side.replaceChildren(el("p", "muted", t("evd.net_private"))); return; }
    let r;
    try { r = await call(`${API}/network/between?a=${encodeURIComponent(l.a.name)}&b=${encodeURIComponent(l.b.name)}`); } catch (e) {
      this.side.replaceChildren(el("p", "muted", t("evd.off", { m: e.message }))); return;
    }
    const box = this.side;
    box.replaceChildren(el("h3", "", `✉️ ${l.a.name} ↔ ${l.b.name} (${r.messages.length})`));
    for (const m of r.messages.slice(0, 60)) {
      const row = el("div", "evd-lead");
      row.append(el("div", "", `${m.day || "—"} · ${m.from === "a" ? l.a.name : l.b.name} → · ${m.subject || t("evd.net_nosubject")}`),
        citeButton({ doc: m.doc, page: m.page, cite: `${m.doc.split(":")[1]} p. ${m.page}` }));
      box.append(row);
    }
  },

  // a few hundred steps of a small force layout: nodes push each other away, ties pull, everything drifts to the middle
  settle() {
    cancelAnimationFrame(this.raf);
    let steps = 260;
    const tick = () => {
      const ns = [...this.nodes.values()];
      for (const a of ns) {
        for (const b of ns) {
          if (a === b) continue;
          const dx = a.x - b.x, dy = a.y - b.y, d2 = Math.max(dx * dx + dy * dy, 25);
          const f = 1800 / d2;
          a.vx += dx * f / Math.sqrt(d2); a.vy += dy * f / Math.sqrt(d2);
        }
        a.vx -= a.x * 0.004; a.vy -= a.y * 0.006;
      }
      for (const l of this.links.values()) {
        const dx = l.b.x - l.a.x, dy = l.b.y - l.a.y, d = Math.max(Math.hypot(dx, dy), 1);
        const f = (d - 110) * 0.02;
        l.a.vx += dx / d * f; l.a.vy += dy / d * f; l.b.vx -= dx / d * f; l.b.vy -= dy / d * f;
      }
      for (const n of ns) {
        if (n.dragging) continue;
        const room = Math.max(1, Math.sqrt(ns.length / 30));       // more people, more room (then zoom and pan)
        n.x = Math.max(-480 * room, Math.min(480 * room, n.x + n.vx)); n.y = Math.max(-300 * room, Math.min(300 * room, n.y + n.vy));
        n.vx *= 0.6; n.vy *= 0.6;
      }
      this.draw();
      if (--steps > 0) this.raf = requestAnimationFrame(tick);
      else if (this.nodes.size > 30) this.fit();             // a big web: all of it in view once it settles
    };
    tick();
  },

  // the elements made once per node and tie, then only moved (a click while the drawing settles is not lost)
  draw() {
    if (!this.layer) { this.layer = { ties: svgEl("g"), nodes: svgEl("g") }; }
    if (this.svg.firstChild !== this.layer.ties) this.svg.replaceChildren(this.layer.ties, this.layer.nodes);
    if (!this.links.size && !this.nodes.size) { this.layer.ties.replaceChildren(); this.layer.nodes.replaceChildren(); }
    for (const l of this.links.values()) {
      if (!l.el) {
        l.el = svgEl("line", { class: `evd-net-tie ${l.kinds.has("wrote_to") ? "wrote" : "copied"}` });
        l.el.append(svgEl("title"));
        l.el.addEventListener("click", () => this.tie(l));
        this.layer.ties.append(l.el);
      }
      l.el.setAttribute("stroke-width", Math.min(1 + Math.log2(1 + l.n), 7));
      l.el.firstChild.textContent = `${l.a.name} ↔ ${l.b.name}: ${l.n}`;
      for (const [k, v] of Object.entries({ x1: l.a.x, y1: l.a.y, x2: l.b.x, y2: l.b.y })) l.el.setAttribute(k, v);
    }
    for (const n of this.nodes.values()) {
      if (!n.el) {
        n.el = svgEl("circle");
        n.el.addEventListener("click", () => { if (n.public && !n.moved) this.expand(n.name, n); n.moved = false; });
        this.dragable(n.el, n);
        n.label = svgEl("text", { class: "evd-net-label" });
        n.label.textContent = n.name;
        this.layer.nodes.append(n.el, n.label);
      }
      const r = 6 + n.size * 2.5;
      n.el.setAttribute("class", `evd-net-node${n.public ? "" : " private"}${n.open ? " open" : ""}`);
      for (const [k, v] of Object.entries({ cx: n.x, cy: n.y, r })) n.el.setAttribute(k, v);
      n.label.setAttribute("x", n.x + r + 3);
      n.label.setAttribute("y", n.y + 4);
    }
  },

  dragable(c, n) {
    c.addEventListener("pointerdown", (e) => {
      const pt = this.svg.createSVGPoint();
      const move = (ev) => {
        pt.x = ev.clientX; pt.y = ev.clientY;
        const p = pt.matrixTransform(this.svg.getScreenCTM().inverse());
        n.x = p.x; n.y = p.y; n.dragging = true; n.moved = true; this.draw();
      };
      const up = () => { n.dragging = false; window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
      e.preventDefault();
    });
  },
};

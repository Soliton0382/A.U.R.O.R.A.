// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// C754: the WebUI's pages RUN under node with a small DOM and the API answered from a fixture — not only parsed.
// argv: [2] the folder of a copy of webui/js whose api.js answers from globalThis.FIX, [3] the scenario's name.
// Prints JSON: what was drawn (texts and classes, depth-first) and what was sent.
class CL {
  constructor(n) { this.n = n; }
  get list() { return this.n.className.split(" ").filter(Boolean); }
  add(...c) { this.n.className = [...new Set([...this.list, ...c])].join(" "); }
  remove(...c) { this.n.className = this.list.filter((x) => !c.includes(x)).join(" "); }
  contains(c) { return this.list.includes(c); }
  toggle(c, on) { const has = this.contains(c); const want = on === undefined ? !has : !!on; if (want) this.add(c); else this.remove(c); return want; }
}
class N {
  constructor(tag) { this.tag = tag; this.children = []; this.className = ""; this.dataset = {}; this._t = ""; this.ev = {}; this.parentNode = null; this.hidden = false; this.style = {}; }
  get classList() { return new CL(this); }
  set textContent(t) { this._t = String(t); this.children = []; }
  get textContent() { return this._t + this.children.map((c) => c.textContent ?? c.text ?? "").join(""); }
  set innerHTML(h) { this._t = ""; this.children = []; this._html = h; }
  append(...c) { for (const k of c) { if (k == null) continue; const n = typeof k === "string" ? { text: k, textContent: k } : k; n.parentNode = this; this.children.push(n); } }
  prepend(...c) { const before = this.children; this.children = []; this.append(...c); this.children.push(...before); }
  replaceChildren(...c) { this.children = []; this.append(...c); }
  after(...c) { const p = this.parentNode; if (!p) return; const i = p.children.indexOf(this); for (const k of c) if (k) k.parentNode = p; p.children.splice(i + 1, 0, ...c.filter(Boolean)); }
  before(...c) { const p = this.parentNode; if (!p) return; const i = p.children.indexOf(this); for (const k of c) if (k) k.parentNode = p; p.children.splice(i, 0, ...c.filter(Boolean)); }
  remove() { const p = this.parentNode; if (p) p.children = p.children.filter((x) => x !== this); }
  addEventListener(e, f) { (this.ev[e] ||= []).push(f); }
  dispatchEvent(e) { for (const f of this.ev[e.type] || []) f(e); }
  click() { this.dispatchEvent({ type: "click", preventDefault() {} }); }
  setAttribute() {} removeAttribute() {} setCustomValidity() {} reportValidity() {}
  get isConnected() { return true; }
  _all() { const out = []; const walk = (n) => { for (const k of n.children || []) { if (k instanceof N) { out.push(k); walk(k); } } }; walk(this); return out; }
  _match(sel) {
    const m = sel.match(/^([a-z0-9]*)((?:\.[\w-]+)*)$/i); if (!m) return () => false;
    const tag = m[1], cls = m[2].split(".").filter(Boolean);
    return (n) => (!tag || n.tag === tag) && cls.every((c) => n.classList.contains(c));
  }
  querySelectorAll(sel) {
    const parts = sel.trim().split(/\s+/); const last = this._match(parts[parts.length - 1]);
    return this._all().filter(last);
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  get firstChild() { return this.children[0] || null; }
}
globalThis.Node = N;
globalThis.Event = class { constructor(type) { this.type = type; } };
globalThis.document = { createElement: (t) => new N(t), createTextNode: (t) => ({ text: t, textContent: t }), querySelector: () => null,
  querySelectorAll: () => [], getElementById: () => null, head: { append() {} }, body: new N("body"), documentElement: new N("html") };
globalThis.window = globalThis;
globalThis.localStorage = { getItem: () => null, setItem() {} };
Object.defineProperty(globalThis, "navigator", { value: { clipboard: { writeText: async () => {} } }, configurable: true });
globalThis.addEventListener = () => {};
globalThis.dispatchEvent = () => {};
globalThis.matchMedia = () => ({ matches: false, addEventListener() {} });
const sent = [];
globalThis.SENT = sent;
const folder = process.argv[2], scene = process.argv[3];
const tick = () => new Promise((r) => setTimeout(r, 0));
const show = (n, d = 0) => (n instanceof N ? [`${"  ".repeat(d)}${n.tag}${n.className ? "." + n.className.replace(/ +/g, ".") : ""}${n._t ? " «" + n._t + "»" : ""}${n.hidden ? " [hidden]" : ""}`, ...n.children.flatMap((c) => show(c, d + 1))] : [`${"  ".repeat(d)}"${n.text}"`]);
const out = {};
try {
  if (scene === "groups") {
    globalThis.FIX = {
      "GET /v1/aurora/users/groups": { groups: { ricerca: ["anna"] }, users: ["boss", "anna"],
        access: [{ feature: "calendar", all: true, users: [], groups: [], default: true, area: "life", icon: "📅", it: "Calendario", en: "Calendar" },
                 { feature: "plugin:telegram", all: false, users: ["anna"], groups: ["ricerca"], default: false, area: "tools", icon: "🔌", it: "telegram", en: "telegram" }] },
      "PUT /v1/aurora/access/calendar": { access: {} },
    };
    const { renderGroups } = await import(`${folder}/modules/users_groups.js`);
    const box = new N("div"), acc = new N("div");
    await renderGroups(box, acc);
    const card = acc.querySelectorAll("details.card")[0];
    card.querySelectorAll("button.cat-chip")[0].click();                     // «Tutti» off
    card.querySelectorAll("button")[card.querySelectorAll("button").length - 1].click();   // save
    await tick();
    out.groups = show(box); out.access = show(acc); out.sent = sent;
  } else if (scene === "restore") {
    globalThis.FIX = {
      "GET /v1/aurora/backup/snapshots": [{ snapshot: "20261127-230000", files: 10, bytes: 2e9, compat: { verdict: "same", why: "" },
        parts: { config: { files: 3, bytes: 1e6 }, memory: { files: 2, bytes: 5e8 } }, command: "sudo aurora-root restore --apply 20261127-230000" }],
      "GET /v1/aurora/users": { users: [{ name: "boss" }, { name: "anna" }] },
      "GET /v1/aurora/backup/restore": {},
      "GET /v1/aurora/backup/evidentia": { installed: true, snapshots: ["20261127-233000"], command: "sudo aurora-root restore --evidentia <copia>" },
    };
    const { restoreBox } = await import(`${folder}/restore.js`);
    const d = restoreBox(); d.open = true; d.dispatchEvent(new Event("toggle"));
    for (let i = 0; i < 10; i++) await tick();
    out.restore = show(d);
  } else if (scene === "sources") {
    globalThis.FIX = {
      "GET /v1/aurora/evidentia/sources": { roots: [{ id: 0, kind: "originals", path: "/o", reachable: false }, { id: 1, kind: "nas", path: "/n", reachable: true }], ingest: { running: false, lines: [] } },
      "GET /v1/aurora/evidentia/sources/browse": { root: 1, path: "", dirs: ["DOJ", "EFTA"], more_dirs: 0, pdfs: 0, images: 0, other: 1 },
      "POST /v1/aurora/evidentia/sources/ingest": { running: true, path: "EFTA", lines: ["3 documents to read"] },
    };
    const { sourcesCard } = await import(`${folder}/evd/evidentia_sources.js`);
    const c = sourcesCard();
    for (let i = 0; i < 10; i++) await tick();
    const dirs = c.querySelectorAll("button.cat-chip").filter((b) => b.textContent.includes("EFTA"));
    out.before = show(c);
    dirs[0].click();                                                     // into EFTA (the fixture answers the same)
    for (let i = 0; i < 10; i++) await tick();
    out.sent = sent;
    globalThis.FIX["GET /v1/aurora/me"] = { admin: false };                  // N168: a user's own NAS folder
    globalThis.FIX["GET /v1/aurora/evidentia-nas"] = { ok: true, folders: 2 };
    const c2 = sourcesCard();
    for (let i = 0; i < 10; i++) await tick();
    out.user = show(c2);
  } else if (scene === "case_share") {
    globalThis.FIX = {
      "GET /v1/aurora/evidentia/cases/aaaaaaaaaaaa": { id: "aaaaaaaaaaaa", title: "Mio", steps: 2, updated: 1 },
      "GET /v1/aurora/evidentia/leads": { leads: [] },
      "GET /v1/aurora/evidentia/cases/aaaaaaaaaaaa/members": { members: ["bob"] },
      "GET /v1/aurora/evidentia-people": { people: ["bob", "cid"] },
      "GET /v1/aurora/evidentia/cases/bbbbbbbbbbbb": { id: "bbbbbbbbbbbb", title: "Di Ann", steps: 1, updated: 1 },
    };
    const page = (await import(`${folder}/evd/evidentia_cases.js`)).default;
    const a = new N("div");
    await page.drawCase(a, "aaaaaaaaaaaa");
    a.querySelectorAll("button").find((b) => b.textContent.includes("evd.share")).click();
    for (let i = 0; i < 10; i++) await tick();
    out.mine = show(a);
    const b = new N("div");
    await page.drawCase(b, "bbbbbbbbbbbb");                         // its members: refused (shared with me)
    out.theirs = show(b);
  } else if (scene === "line") {
    // C758: a window with notifications and no Web Push (Aurora Desktop): the line's events become Notifications
    const shown = [];
    let stop = false;
    globalThis.localStorage = { getItem: (k) => (k === "aurora.line.off" && stop ? "1" : null), setItem() {}, removeItem() {} };
    globalThis.Notification = class { constructor(title, o) { shown.push([title, o.body, o.tag]); stop = true; } close() {} static permission = "granted"; static requestPermission = async () => "granted"; };
    globalThis.FIX = { "GET /v1/aurora/line": { next: "7", events: [{ id: "8", title: "Aurora", body: "Il backup è finito", tag: "backup", view: "status" },
                                                                    { id: "9", kind: "call", title: "📞 Aurora", body: "squilla" }] } };
    globalThis.PushManager = class {};                 // QtWebEngine has the API, with no push service behind it
    Object.defineProperty(globalThis, "navigator", { value: { userAgent: "Mozilla/5.0 (X11; Linux x86_64) QtWebEngine/6.10.2 Chrome/134.0.0.0" }, configurable: true });
    const P = await import(`${folder}/push.js`);
    out.mode = P.lineMode();
    out.state = await P.pushState();
    await P.startLine();
    out.shown = shown;
  } else if (scene === "chat_tabs") {
    const { setHidden } = await import(`${folder}/access.js`);
    const { chatTabs } = await import(`${folder}/modules/chat_tabs.js`);
    out.all = show(chatTabs("chat"));
    setHidden(["anonchat", "interpret"]);
    out.alone = show(chatTabs("chat"));
  }
} catch (e) { out.error = `${e.name}: ${e.message}\n${(e.stack || "").split("\n").slice(1, 4).join("\n")}`; }
console.log(JSON.stringify(out));

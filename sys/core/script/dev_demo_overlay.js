// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The demo recorder's layer inside the page (dev_demo_video.py): captions, title cards, a cursor, a highlight, a
// terminal and a picture over the WebUI, and the privacy mask: every text shown passes through it before it is painted
// (addresses, the installation's own words, e-mails, MAC), so a recording never shows the machine's real data.
// window.__DEMO_MASK is set by the recorder before this runs: {words: [[from, to], ...], keep: ["203.0.113.", ...]}.
(() => {
  if (window.__demo) return;
  const cfg = window.__DEMO_MASK || { words: [], keep: [] };
  const KEEP = ["127.0.0.1", "0.0.0.0", "255.255.255.", "203.0.113.", "198.51.100.", "192.0.2.", ...(cfg.keep || [])];
  const ipMap = new Map();
  const IPV4 = /\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b/g;
  const IPV6 = /\b(?:[0-9a-f]{1,4}:){2,7}(?::?[0-9a-f]{1,4}){1,7}\b|\b(?:[0-9a-f]{1,4}:){1,7}:(?![\w:])/gi;
  const MAC = /\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b/gi;
  const MAIL = /\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b/g;
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const words = (cfg.words || []).filter((w) => w[0] && w[0].length >= 3)
    .sort((a, b) => b[0].length - a[0].length)
    .map(([from, to]) => [new RegExp(`(?<![\\p{L}\\p{N}_])${esc(from)}(?![\\p{L}\\p{N}_])`, "giu"), to]);   // whole words only
  const ip4 = (ip) => {
    if (KEEP.some((k) => ip.startsWith(k))) return ip;
    // a real address becomes one of 198.51.100.x, never 203.0.113.x: that range is the storyboard's own (C515: a real
    // attacker shown as «203.0.113.7» was taken for the demo's block and lifted), and never two real ones the same
    if (!ipMap.has(ip)) { const n = ipMap.size; ipMap.set(ip, n < 254 ? `198.51.100.${n + 1}` : `192.0.2.${((n - 254) % 254) + 1}`); }
    return ipMap.get(ip);
  };
  function mask(s) {
    if (!s || s.length < 3) return s;
    let t = s;
    for (const [rx, to] of words) t = t.replace(rx, to);
    t = t.replace(MAIL, "someone@example.org").replace(MAC, "02:00:5e:00:00:01").replace(IPV4, ip4);
    t = t.replace(IPV6, (v) => (/^[0-9a-f]{1,4}:[0-9a-f]{1,4}$/i.test(v) || /^\d+:\d+(:\d+)?$/.test(v) ? v : "2001:db8::1"));
    return t;
  }
  const ATTRS = ["title", "placeholder", "aria-label", "alt", "value"];
  const OURS = (n) => n && n.closest && n.closest("#demo-layer") && !n.closest("#demo-term");
  function scrub(root) {
    if (!root) return;
    if (root.nodeType === 3) {                            // a text node
      if (OURS(root.parentElement)) return;
      const v = root.nodeValue, m = mask(v);
      if (m !== v) root.nodeValue = m;
      return;
    }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) {
      if (OURS(root)) return;
      for (const a of ATTRS) if (root.hasAttribute(a)) {
        const v = root.getAttribute(a), m = mask(v);
        if (m !== v) root.setAttribute(a, m);
      }
      if ((root.tagName === "INPUT" || root.tagName === "TEXTAREA") && root.value && root.dataset.demoTyped !== "1") {
        const m = mask(root.value);
        if (m !== root.value) { root.value = m; root.dataset.demoMasked = "1"; }
      }
      if (root.shadowRoot) scrub(root.shadowRoot);
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n = walker.nextNode();
    while (n) { if (n !== root) { if (n.nodeType === 3) scrub(n); else if (n.nodeType === 1) scrubOwn(n); } n = walker.nextNode(); }
  }
  function scrubOwn(el) {                                  // an element's own attributes and value, not its children
    if (OURS(el)) return;
    for (const a of ATTRS) if (el.hasAttribute(a)) {
      const v = el.getAttribute(a), m = mask(v);
      if (m !== v) el.setAttribute(a, m);
    }
    if ((el.tagName === "INPUT" || el.tagName === "TEXTAREA") && el.value && el.dataset.demoTyped !== "1") {
      const m = mask(el.value);
      if (m !== el.value) { el.value = m; el.dataset.demoMasked = "1"; }
    }
    if (el.shadowRoot) scrub(el.shadowRoot);
  }
  const obs = new MutationObserver((list) => {
    for (const r of list) {
      if (r.type === "characterData") scrub(r.target);
      else if (r.type === "attributes") { if (r.target.nodeType === 1) scrubOwn(r.target); }
      else for (const n of r.addedNodes) scrub(n);
    }
  });
  const start = () => {
    scrub(document.documentElement);
    obs.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    document.title = mask(document.title);
  };
  if (document.documentElement) start(); else document.addEventListener("DOMContentLoaded", start);
  setInterval(() => scrub(document.body), 700);           // values set by script without a mutation (input.value)

  // ---- the recorder's own layer ---------------------------------------------------------------------------------
  const css = `
  #demo-layer{position:fixed;inset:0;pointer-events:none;z-index:2147483647;font-family:Inter,"Segoe UI",system-ui,sans-serif}
  #demo-cap{position:absolute;left:50%;bottom:56px;transform:translate(-50%,20px);opacity:0;transition:all .45s ease;
    max-width:1100px;padding:18px 28px;border-radius:18px;background:rgba(12,16,32,.86);backdrop-filter:blur(8px);
    color:#f4f6ff;box-shadow:0 10px 40px rgba(0,0,0,.45);border:1px solid rgba(140,170,255,.35)}
  #demo-cap.on{opacity:1;transform:translate(-50%,0)}
  #demo-cap.top{bottom:auto;top:40px}
  #demo-cap b{display:block;font-size:30px;font-weight:700;letter-spacing:.2px;color:#9fd0ff}
  #demo-cap span{display:block;font-size:22px;line-height:1.35;margin-top:6px;color:#e8ecff}
  #demo-card{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
    background:radial-gradient(ellipse at 50% 40%,#1b2a5a 0%,#070a18 70%);color:#fff;opacity:0;transition:opacity .6s}
  #demo-card.on{opacity:1}
  #demo-card h1{font-size:76px;margin:0;font-weight:800;letter-spacing:2px;background:linear-gradient(90deg,#7fd3ff,#c59bff);
    -webkit-background-clip:text;color:transparent}
  #demo-card p{font-size:30px;margin:22px 0 0;color:#cfd8ff;max-width:1300px;text-align:center;line-height:1.4;white-space:pre-line}
  #demo-cursor{position:absolute;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(255,255,255,.9);
    border:3px solid #5aa9ff;box-shadow:0 0 0 6px rgba(90,169,255,.25);left:-40px;top:-40px;transition:left .5s ease,top .5s ease,opacity .4s ease}
  #demo-cursor.click{animation:demoClick .35s}
  @keyframes demoClick{0%{box-shadow:0 0 0 6px rgba(90,169,255,.25)}50%{box-shadow:0 0 0 22px rgba(90,169,255,.0)}100%{box-shadow:0 0 0 6px rgba(90,169,255,.25)}}
  .demo-hl{position:absolute;border:3px solid #ffcf5a;border-radius:12px;box-shadow:0 0 0 9999px rgba(0,0,0,.35),0 0 24px #ffcf5a;transition:all .4s}
  #demo-term{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:1280px;max-height:760px;overflow:hidden;
    background:#0b0e14;border-radius:14px;box-shadow:0 20px 70px rgba(0,0,0,.6);border:1px solid #2a3350;opacity:0;transition:opacity .4s}
  #demo-term.on{opacity:1}
  #demo-term header{background:#1a2033;padding:10px 16px;color:#aab4d4;font:15px/1 Inter,system-ui,sans-serif}
  #demo-term pre{margin:0;padding:18px 22px;color:#d7f7d0;font:19px/1.45 "JetBrains Mono","DejaVu Sans Mono",monospace;white-space:pre-wrap}
  #demo-term mark{background:#ffcf5a;color:#111;border-radius:4px;padding:0 3px}
  #demo-pic{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(5,8,18,.88);opacity:0;transition:opacity .5s}
  #demo-pic.on{opacity:1}
  #view-https img,#view-https canvas,#view-https svg,img[alt*="QR" i],canvas.qr,.qr img,.qr canvas{filter:blur(16px)!important}
  #demo-feat{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 35%,#1b2a5a 0%,#070a18 75%);opacity:0;transition:opacity .5s;
    display:flex;flex-direction:column;align-items:center;justify-content:center}
  #demo-feat.on{opacity:1}
  #demo-feat h2{font-size:54px;margin:0 0 34px;font-weight:800;background:linear-gradient(90deg,#7fd3ff,#c59bff);-webkit-background-clip:text;color:transparent}
  #demo-feat .grid{display:grid;grid-template-columns:repeat(4,370px);gap:16px}
  #demo-feat .f{padding:16px 20px;border-radius:16px;background:rgba(30,45,95,.85);border:1px solid rgba(150,180,255,.35);color:#eef2ff;
    font-size:22px;opacity:0;transform:translateY(18px) scale(.96);transition:all .45s cubic-bezier(.2,.8,.2,1)}
  #demo-feat .f.on{opacity:1;transform:none}
  #demo-feat .f small{display:block;color:#aab8e8;font-size:16px;margin-top:4px}
  #demo-chap{position:absolute;transition:all .7s cubic-bezier(.2,.8,.2,1);background:linear-gradient(135deg,rgba(40,70,160,.92),rgba(110,60,170,.92));
    color:#fff;border-radius:22px;box-shadow:0 12px 40px rgba(0,0,0,.45);border:1px solid rgba(180,200,255,.4)}
  #demo-chap b{display:block;font-weight:800}
  #demo-chap span{display:block;opacity:.9}
  #demo-chap.big{left:50%;top:42%;transform:translate(-50%,-50%);padding:28px 44px;text-align:center}
  #demo-chap.big b{font-size:52px}
  #demo-chap.big span{font-size:26px;margin-top:8px}
  #demo-chap.small{left:84px;top:84px;transform:none;padding:8px 16px;border-radius:14px}
  #demo-chap.small b{font-size:20px}
  #demo-chap.small span{display:none}
  #demo-ff{position:absolute;right:36px;top:96px;padding:10px 18px;border-radius:12px;background:rgba(12,16,32,.86);
    color:#9fd0ff;font:700 26px/1 Inter,system-ui,sans-serif;border:1px solid rgba(140,170,255,.35);opacity:0;transition:opacity .3s}
  #demo-pic img{max-width:88%;max-height:86%;border-radius:10px;box-shadow:0 20px 70px rgba(0,0,0,.7)}`;
  function layer() {
    let l = document.getElementById("demo-layer");
    if (l) return l;
    const st = document.createElement("style");
    st.textContent = css;
    document.head.appendChild(st);
    l = document.createElement("div");
    l.id = "demo-layer";
    l.innerHTML = '<div id="demo-card"><h1></h1><p></p></div><div id="demo-pic"><img></div>' +
      '<div id="demo-term"><header></header><pre></pre></div><div id="demo-cap"><b></b><span></span></div><div id="demo-cursor"></div>';
    document.body.appendChild(l);
    return l;
  }
  const q = (s) => layer().querySelector(s);
  window.__demo = {
    mask,
    caption(title, sub, top) {
      const c = q("#demo-cap");
      c.querySelector("b").textContent = title || "";
      c.querySelector("span").textContent = sub || "";
      c.classList.toggle("top", !!top);
      c.classList.add("on");
    },
    uncaption() { q("#demo-cap").classList.remove("on"); },
    card(title, sub) {
      const c = q("#demo-card");
      c.querySelector("h1").textContent = title || "";
      c.querySelector("p").textContent = sub || "";
      c.classList.add("on");
    },
    uncard() { q("#demo-card").classList.remove("on"); },
    cursor(x, y, click) {                              // seen while it moves and clicks, then gone: never over a caption
      const c = q("#demo-cursor");
      const cap = q("#demo-cap").getBoundingClientRect(), pad = 40;   // over a caption: moved, never seen on the words
      const onCap = q("#demo-cap").classList.contains("on") && x > cap.left - pad && x < cap.right + pad
        && y > cap.top - pad && y < cap.bottom + pad;
      c.style.opacity = onCap ? "0" : "1";
      c.style.left = `${x}px`;
      c.style.top = `${y}px`;
      if (click) { c.classList.remove("click"); void c.offsetWidth; c.classList.add("click"); }
      clearTimeout(window.__demoCur);
      window.__demoCur = setTimeout(() => { c.style.opacity = "0"; }, click ? 900 : 2500);
    },
    highlight(box) {
      const h = document.createElement("div");
      h.className = "demo-hl";
      Object.assign(h.style, { left: `${box.x - 8}px`, top: `${box.y - 8}px`, width: `${box.width + 16}px`, height: `${box.height + 16}px` });
      layer().appendChild(h);
    },
    unhighlight() { layer().querySelectorAll(".demo-hl").forEach((h) => h.remove()); },
    term(title) {
      const t = q("#demo-term");
      t.querySelector("header").textContent = mask(title || "terminal");
      t.querySelector("pre").textContent = "";
      t.classList.add("on");
    },
    termLine(line, marks) {                              // a line of real output, some words marked
      const pre = q("#demo-term pre");
      const div = document.createElement("div");
      let html = mask(line).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
      for (const m of marks || []) html = html.split(m).join(`<mark>${m}</mark>`);
      div.innerHTML = html || "&nbsp;";
      pre.appendChild(div);
      while (pre.scrollHeight > 700 && pre.firstChild) pre.firstChild.remove();
    },
    unterm() { q("#demo-term").classList.remove("on"); },
    picture(src) { const p = q("#demo-pic"); p.querySelector("video")?.remove(); const i = p.querySelector("img"); i.style.display = ""; i.src = src; p.classList.add("on"); },
    clip(src) {                                         // a real clip of hers, played over the page
      const p = q("#demo-pic"); p.querySelector("img").style.display = "none"; p.querySelector("video")?.remove();
      const v = document.createElement("video"); v.src = src; v.muted = true; v.loop = true; v.autoplay = true; v.playsInline = true;
      v.style.cssText = "max-width:80%;max-height:80%;border-radius:12px;box-shadow:0 20px 70px rgba(0,0,0,.7)";
      p.appendChild(v); p.classList.add("on"); v.play().catch(() => {});
    },
    unpicture() { q("#demo-pic").classList.remove("on"); },
    ff(label) {                                         // the badge of a wait shown faster, with the real time running
      let b = layer().querySelector("#demo-ff");
      if (!b) { b = document.createElement("div"); b.id = "demo-ff"; layer().appendChild(b); }
      clearInterval(window.__demoFF);
      const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
      if (label) {
        const t0 = Date.now();
        const draw = () => { b.textContent = `${label} · real time ${mmss((Date.now() - t0) / 1000)}`; };
        draw();
        window.__demoFF = setInterval(draw, 250);
        window.__demoFF0 = t0;
        b.style.opacity = "1";
      } else {
        const s = window.__demoFF0 ? (Date.now() - window.__demoFF0) / 1000 : 0;
        b.textContent = `⏱ real time ${mmss(s)}`;
        setTimeout(() => { b.style.opacity = "0"; }, 2200);
      }
    },
    features(title, items, each) {                     // «and much more»: tiles one after the other
      let f = layer().querySelector("#demo-feat");
      if (!f) { f = document.createElement("div"); f.id = "demo-feat"; layer().appendChild(f); }
      f.innerHTML = "";
      const h = document.createElement("h2"); h.textContent = title;
      const g = document.createElement("div"); g.className = "grid";
      f.append(h, g);
      f.classList.add("on");
      items.forEach(([name, note], i) => {
        const d = document.createElement("div"); d.className = "f"; d.textContent = name;
        if (note) { const s = document.createElement("small"); s.textContent = note; d.appendChild(s); }
        g.appendChild(d);
        setTimeout(() => d.classList.add("on"), 300 + i * (each || 280));
      });
    },
    unfeatures() { layer().querySelector("#demo-feat")?.classList.remove("on"); },
    chapter(title, sub) {                               // the chapter's label: big first, then small in a corner
      let c = layer().querySelector("#demo-chap");
      if (!c) { c = document.createElement("div"); c.id = "demo-chap"; layer().appendChild(c); }
      c.innerHTML = "";
      const b = document.createElement("b"); b.textContent = title || "";
      const s = document.createElement("span"); s.textContent = sub || "";
      c.append(b, s);
      c.className = "big";
      setTimeout(() => { c.className = "small"; }, 2600);
    },
  };
  // the recorder's styles from the start (the QR blur), not at its first caption: a QR was sharp in frame 0
  if (document.body) layer(); else document.addEventListener("DOMContentLoaded", () => layer());
})();

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// How a run's events become words and a collapsible path inside Aurora's message.
// Used by the chat module; knows nothing about the page around it.
import { call, stream } from "../api.js";
import { bus, runEnded, runStarted } from "../bus.js";
import { clock, el, scrollEnd } from "../dom.js";
import { t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { artifactCard } from "../artifact.js";
import { view, viewLink } from "../viewer.js";

export const ICONS = {
  "run.start": "▶️", route: "🧭", "attach.image": "🖼️", "attach.video": "🎬", "image.plan": "🛠️", "image.edited": "🎨", "video.frames": "🎞️", "video.plan": "🎬", "attach.document": "📄", "self.state": "🩺", translate: "🌐",
  "question.standalone": "🧷", "retrieval.focus": "🎯", "answer.suggestions": "🧭",
  "retrieval.filter": "🧹", "retrieval.hits": "🔎", "memory.recent": "🧠", gate: "🚪", "synthesis.domain": "🧩",
  "verify.keep": "✅", "verify.drop": "✂️", "memory.write": "💾", "answer.final": "📝", "run.end": "🏁", error: "⛔",
  "acquire.confirmed": "🛰️", "acquire.round": "🛰️", "acquire.candidates": "📚", "acquire.paper": "📥", "acquire.error": "⚠️", "acquire.done": "🏁",
  "rem.start": "🌙", "rem.session_memory": "🗂️", "rem.thought": "💭", "rem.dream": "🌌", "rem.self_review": "🔍", "rem.repair": "🛠️",
  "rem.end": "🏁",
  "agent.start": "🤖", "agent.thought": "💭", "agent.say": "💬", "tool.call": "🔧", "tool.result": "📎", "tool.cached": "🌗",
  "approval.request": "🛎️", "approval.execute": "▶️", "approval.done": "🏁", "agent.finish": "🏁", "agent.file": "📄",
  "change.check": "🧬", "change.tests.sandbox": "🧪", "change.applied": "📦", "change.tests.live": "🧪",
  "change.rollback": "↩️", "change.restart": "🔄",
};

export function describe(name, p) {
  switch (name) {
    case "route": return t(`ev.route.${p.mode}`);
    case "attach.image": return t("ev.attach.image", { name: p.name });
    case "image.plan": return t("ev.image.plan", { name: p.name, n: p.ops.length });
    case "image.edited": return t("ev.image.edited", { name: p.name, w: p.width, h: p.height });
    case "video.plan": return t("ev.video.plan", { title: p.title, m: p.minutes, src: p.from_picture ? "📷" : "✍️" });
    case "video.frames": return t("ev.video.frames", { name: p.name, n: p.frames.length, s: p.scenes });
    case "attach.video": return t("ev.attach.video", { name: p.name, w: Math.round(p.watched), f: p.frames, n: p.speech, s: p.seconds });
    case "attach.document": return t("ev.attach.document", { name: p.name, domain: p.domain, n: p.chunks, w: p.written });
    case "translate": return t("ev.translate", { text: p.translation });
    case "retrieval.filter": return t("ev.retrieval.filter", { n: p.dropped_own_answers });
    case "question.standalone": return t("ev.question.standalone", { q: p.question });
    case "retrieval.focus": return t("ev.retrieval.focus", { k: p.kept, n: p.sources });
    case "answer.suggestions": return t("ev.answer.suggestions", { n: p.items.length });
    case "tool.cached": return t("ev.tool.cached", { plugin: p.plugin, tool: p.tool });
    case "retrieval.hits": return t("ev.retrieval.hits", { n: p.hits.length });
    case "memory.recent": return t("ev.memory.recent", { n: p.turns });
    case "gate": return p.open ? t("ev.gate.open", { ids: p.passages.join(", ") }) : t("ev.gate.closed");
    case "synthesis.domain": return t(p.kept ? "ev.synthesis.domain.kept" : "ev.synthesis.domain.empty", { domain: p.domain });
    case "verify.keep": return t("ev.verify.keep", { s: p.sentence });
    case "verify.drop": return t("ev.verify.drop", { s: p.sentence, r: p.reason });
    case "run.end": return t("ev.run.end", { s: p.seconds });
    case "error": return t("ev.error", { m: p.message });
    case "acquire.confirmed": return t("ev.acquire.confirmed", { q: p.question });
    case "acquire.round": return t("ev.acquire.round", { r: p.round, q: p.queries.join(" · ") });
    case "acquire.original": return t(p.found ? "ev.acquire.original" : "ev.acquire.original_none", { title: p.title, id: p.found });
    case "acquire.candidates": return t("ev.acquire.candidates", { n: p.count });
    case "acquire.paper": return t("ev.acquire.paper", { title: p.title, domain: p.domain, n: p.written });
    case "acquire.error": return t("ev.acquire.error", { m: p.message });
    case "acquire.done": return t(p.found ? "ev.acquire.found" : "ev.acquire.notfound", { r: p.round, n: p.papers });
    case "rem.start": return t(`ev.rem.${p.task}`);
    case "rem.dream": return t("ev.rem.dream_done");
    case "rem.repair": return t("ev.rem.repair_done");
    case "agent.start": return t("ev.agent.start", { goal: p.goal.slice(0, 160), n: p.tools });
    case "agent.thought": return t("ev.agent.thought");
    case "agent.say": return p.text.slice(0, 300);
    case "tool.call": return t("ev.tool.call", { name: p.name.replace("__", "."), effect: p.effect });
    case "tool.result": return t(p.ok ? "ev.tool.ok" : "ev.tool.fail", { name: p.name.replace("__", ".") });
    case "approval.request": return t("ev.approval.request", { title: p.title });
    case "approval.execute": return t("ev.approval.execute", { title: p.title });
    case "approval.done": return t(p.ok ? "ev.approval.ok" : "ev.approval.fail");
    case "agent.file": return t("ev.agent.file", { name: p.name });
    case "agent.finish": return t("ev.agent.finish", { n: p.steps, s: p.seconds });
    case "change.check": return t("ev.change.check", { files: p.files.join(", ") });
    case "change.tests.sandbox": return t("ev.change.tests.sandbox", { r: p.summary });
    case "change.applied": return t("ev.change.applied", { files: p.files.join(", ") });
    case "change.tests.live": return t("ev.change.tests.live", { r: p.summary });
    case "change.rollback": return t("ev.change.rollback", { r: p.reason });
    case "change.restart": return t("ev.change.restart", { s: p.services.join(", ") });
    default: return t(`ev.${name}`);
  }
}

function details(summary, body, cls = "muted") {
  const d = el("details");
  d.append(el("summary", "", summary));
  if (body instanceof Node) d.append(body); else d.append(el("div", cls, body));
  return d;
}

function traceLine(steps, name, p) {
  const row = el("div", `ev${name === "verify.drop" ? " drop" : ""}${name === "error" ? " err" : ""}`);
  row.append(el("span", "ic", ICONS[name] || "•"), el("span", "", describe(name, p)));
  const extra = row.lastChild;
  if (name === "retrieval.hits" && p.hits.length) {
    const list = el("div");
    for (const h of p.hits) list.append(el("div", "muted", `[${h.n}] ${h.title || h.source} · ${h.domain} · ${h.rerank}`));
    extra.append(details([...new Set(p.hits.map((h) => h.domain))].join(", "), list));
  }
  if (name === "acquire.candidates" && p.top.length) {
    const list = el("div");
    for (const c of p.top) list.append(el("div", "muted", `${c.score} · ${c.category} · ${c.title}`));
    extra.append(details("top", list));
  }
  if (name === "attach.image" || name === "attach.video") extra.append(details(t("chat.seen"), p.description));
  if (name === "self.state") extra.append(details(t("chat.facts"), el("pre", "facts", JSON.stringify(p, null, 1))));
  if (name.startsWith("rem.") && p.text) extra.append(details(t("chat.read"), p.text));
  if (name === "agent.thought") extra.append(details(t("chat.read"), p.text));
  if (name === "tool.call") extra.append(details(t("chat.args"), p.arguments));
  if (name === "tool.result" || name === "approval.done") extra.append(details(t("chat.read"), p.text || p.result || ""));
  steps.append(row);
}

// One Aurora message: the path it took (open while it works, folded when done) and the answer.
export function auroraBubble(container) {
  const root = el("div", "msg aurora");
  const iter = el("details", "iter");
  iter.open = true;
  const head = el("summary", "iter-head");
  head.append(el("span", "spin"), el("span", "iter-text", t("chat.working")));
  const steps = el("div", "steps");
  iter.append(head, steps);
  const body = el("div", "body");
  root.append(iter, body);
  container.append(root);
  return { root, iter, head, steps, body, count: 0, t0: Date.now() };
}

// how the answer was checked (owner, 2026-10-05, from what people ask of an AI: accuracy first): counted from the run's
// own verification events — the sentences kept against the passages and those dropped — never an invented "confidence"
export function checks(trace) {
  let kept = 0, dropped = 0;
  for (const [name] of trace || []) { if (name === "verify.keep") kept += 1; else if (name === "verify.drop") dropped += 1; }
  return { kept, dropped };
}

export function renderAnswer(b, p, when) {
  const box = b.body;
  box.replaceChildren();
  b.root.classList.toggle("abstained", !!p.abstained);
  box.append(renderMarkdown(p.text));
  if (p.shadow) {                                // from the shadow of an earlier answer (kno_shadow): said, and rechecked
    box.append(el("div", "meta checked", t("chat.shadow", { q: p.shadow.question, d: new Date(p.shadow.made * 1000).toLocaleDateString(),
      c: Number(p.shadow.cos).toFixed(2) })));
  }
  if (p.checked && p.checked.kept + p.checked.dropped > 0 && !p.abstained) {
    box.append(el("div", "meta checked", t("chat.checked", { k: p.checked.kept, d: p.checked.dropped, s: p.sources?.length || 0 })));
  }
  if (p.images?.length) {                        // pictures Aurora made (edits): shown, kept in the conversation
    const row = el("div", "chips");
    for (const f of p.images) {
      if (!f.url) continue;
      const a = viewLink(el("a", "chip"), f.url, f.name, f.mime || "image/png");
      const img = el("img"); img.src = f.url; img.alt = f.name; img.loading = "lazy";
      a.append(img, el("span", "", f.name));
      row.append(a);
    }
    box.append(row);
  }
  if (p.videos?.length) {                        // videos Aurora made: played in place
    for (const f of p.videos) {
      if (!f.url) continue;
      const v = el("video", "made-video"); v.src = f.url; v.controls = true; v.playsInline = true; v.preload = "metadata";
      const a = el("a", "chip"); a.href = f.url; a.setAttribute("download", f.name); a.append(el("span", "", "🎬"), el("span", "", f.name));
      box.append(v, a);
    }
  }
  if (p.files?.length) {                         // documents Aurora wrote (a PDF...): one tap downloads them
    const row = el("div", "chips");
    for (const f of p.files) {
      if (f.mime === "text/html" && f.url?.startsWith("/v1/aurora/uploads/")) { box.append(artifactCard(f)); continue; }
      const a = viewLink(el("a", "chip"), f.url, f.name, f.mime);       // a PDF opens in place; it can be saved there
      a.append(el("span", "", "📄"), el("span", "", f.name));
      row.append(a);
    }
    box.append(row);
  }
  if (p.sources?.length) {
    box.append(el("div", "meta", t("chat.sources")));
    const ol = el("ol", "sources");
    for (const s of p.sources) {
      const li = el("li", "", `${s.title || s.source} (${s.domain})`);
      li.value = s.n;
      ol.append(li);
    }
    box.append(ol);
  }
  const meta = [clock(when || new Date().toISOString())];
  if (p.seconds !== undefined) meta.push(t("chat.seconds", { s: p.seconds }));
  if (p.speed?.per_second) meta.push(t("chat.speed", { r: p.speed.per_second, n: p.speed.tokens }));
  if (p.dropped?.length) meta.push(t("chat.dropped", { n: p.dropped.length }));
  if (p.abstained) meta.push(t("chat.abstained"));
  const foot = el("div", "meta");
  foot.append(el("span", "", meta.join(" · ")));
  if (!p.abstained && p.text) {                     // share a real answer as a post (the owner reviews it first)
    const share = el("button", "share", `↗ ${t("chat.share")}`);
    share.type = "button";
    share.addEventListener("click", () => bus.emit("share", { text: p.text }));
    const pdf = el("button", "share", "⬇ PDF");
    pdf.type = "button";
    pdf.addEventListener("click", async () => {         // the answer as a PDF, opened in the viewer (Download there)
      pdf.disabled = true;
      try {
        const title = p.text.split("\n").find((l) => l.trim())?.replace(/[#*`]/g, "").trim().slice(0, 80) || "Aurora";
        const doc = await call("/v1/aurora/documents/pdf", { method: "POST", body: JSON.stringify({ title, text: p.text }) });
        view(doc.url, doc.name, "application/pdf");
      } catch (e) { pdf.textContent = `⛔ ${e.message}`; }
      pdf.disabled = false;
    });
    foot.append(share, pdf);
  }
  box.append(foot);
}

// A past answer from memory: its saved path (steps and reasoning), folded, then the answer.
export function renderPast(b, turn) {
  b.head.querySelector(".spin")?.remove();
  for (const [name, p] of turn.trace || []) traceLine(b.steps, name, p);
  if (turn.thought) {
    const th = el("details", "thought");
    th.append(el("summary", "", `💭 ${t("chat.thinking")}`), el("pre", "", turn.thought));
    b.steps.append(th);
  }
  const n = (turn.trace || []).length;
  b.head.querySelector(".iter-text").textContent = n
    ? `🧭 ${t("chat.iter", { n, s: turn.seconds ?? "–" })}` : `🧭 ${t("chat.nopath")}`;
  b.iter.open = false;
  renderAnswer(b, { text: turn.text, abstained: turn.abstained, sources: turn.sources, seconds: turn.seconds, speed: turn.speed,
    checked: checks(turn.trace),
    images: (turn.attachments || []).filter((f) => f.inline && f.mime.startsWith("image/")),
    videos: (turn.attachments || []).filter((f) => f.inline && f.mime.startsWith("video/")),
    files: (turn.attachments || []).filter((f) => !(f.inline && /^(image|video)\//.test(f.mime))) },
    turn.created_at);
}

// Follow a run's events into a bubble. Returns the final answer payload (or null).
export async function follow(runId, b, scroller) {
  let thought = null, draft = null, final = null;
  const seen = [];                                  // the run's events, for the answer's check line
  b.iter.open = true;
  b.head.classList.add("running");
  const status = (text) => { b.head.querySelector(".iter-text").textContent = text; };
  const nearEnd = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
  runStarted();
  try {
    await stream(`/v1/aurora/runs/${runId}/events`, ({ event: name, payload: p }) => {
      const stick = nearEnd();
      if (name === "synthesis.delta") {
        if (p.kind === "thought") {
          if (!thought) {
            thought = el("details", "thought");
            thought.open = true;
            thought.append(el("summary", "", `💭 ${t("chat.thinking")}`), el("pre"));
            b.steps.append(thought);
            status(`💭 ${t("chat.thinking")}…`);
          }
          thought.lastChild.textContent += p.text;
          scrollEnd(thought.lastChild);
        } else {
          if (!draft) {
            if (thought) thought.open = false;
            b.body.replaceChildren(el("div", "meta", t("chat.draft")));
            draft = el("div", "draft");
            b.body.append(draft);
          }
          draft.textContent += p.text;
        }
        if (stick) scrollEnd(scroller);
        return;
      }
      if (name === "run.start") { thought = null; draft = null; }
      seen.push([name]);
      if (name === "answer.final") { final = p; renderAnswer(b, { ...p, checked: checks(seen) }); }
      else if (name === "answer.suggestions" && final) final.suggestions = p.items;
      else if (name === "error") b.body.replaceChildren(el("p", "error", describe(name, p)));
      else if (name.startsWith("rem.") && p.text) { b.body.replaceChildren(el("p", "", p.text)); }
      else if (name === "agent.finish") { final = { text: p.summary, seconds: p.seconds, files: p.files || [], images: p.images || [] }; renderAnswer(b, final); }
      traceLine(b.steps, name, p);
      b.count += 1;
      status(`${ICONS[name] || "•"} ${describe(name, p)}`);
      if (stick) scrollEnd(scroller);
    });
  } finally {
    runEnded();
    b.head.classList.remove("running");
    status(`🧭 ${t("chat.iter", { n: b.count, s: ((Date.now() - b.t0) / 1000).toFixed(1) })}`);
    b.iter.open = false;
  }
  return final;
}

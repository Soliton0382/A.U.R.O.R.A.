// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💬 Talking with a project's conductor (ROADMAP N39 step 2, prj_talk), as a console (owner, 23 Oct: «la chat con il
// conduttore la vorrei proprio come te stile console»): a dark terminal, the owner's lines after «❯», the answers in
// monospace with a dim «⎿» line under each (who answered, how long, what it cost when the CLI says it), «✻» while it
// thinks; Enter sends, Shift+Enter starts a new line; slash commands: /nuova, /fase, /pulisci, /aiuto. Kept per
// project and per user — on the Claude CLI one session resumed turn after turn, else the local model or an API with
// the turns sent again. The conductor talks, it does not act: /fase (or «↳ fanne una fase» under an answer) turns an
// answer into a phase's goal (the phases below).
import { call } from "../api.js";
import { clock, el, useCss } from "../dom.js";
import { t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

const WHO = { cli: "prj.talk_cli", cloud: "prj.talk_cloud", local: "prj.talk_local" };
const SPIN = ["✻", "✶", "✷", "✸", "✹", "✺"];

function meta(e) {
  const parts = [clock(e.t)];
  if (e.backend) parts.push(t(WHO[e.backend] || "prj.talk_local"));
  if (e.seconds != null) parts.push(`${e.seconds} s`);
  if (e.backend && e.backend !== "local") {
    parts.push(e.cost_usd != null ? t("prj.talk_cost", { usd: Number(e.cost_usd).toFixed(4) }) : t("prj.talk_cost_none"));
  }
  if (e.new_session) parts.push(t("prj.talk_new_session"));
  return `⎿ ${parts.join(" · ")}`;
}

export function talkView(name, onPhase) {
  useCss("/static/css/projects.css");
  const box = el("div", "prj-talk term");
  const bar = el("div", "term-bar");
  const who = el("span", "term-who", "");
  bar.append(el("span", "term-dots", "● ● ●"), el("span", "term-title", `${t("prj.talk_title")} — ${name}`), who);
  const log = el("div", "term-log");
  const form = el("form", "term-input");
  const input = el("textarea");
  input.rows = 1;
  input.placeholder = t("prj.talk_ph");
  input.setAttribute("autocapitalize", "off");
  input.spellcheck = false;
  const go = el("button", "term-go", "⏎");
  go.type = "submit";
  go.title = t("chat.send");
  form.append(el("span", "term-prompt", "❯"), input, go);
  const hint = el("div", "term-hint", t("prj.talk_keys"));
  const base = `/v1/aurora/projects/${name}/talk`;
  let lastAnswer = null;

  const line = (cls, text) => el("div", `term-line ${cls}`, text);
  const you = (text) => { const l = el("div", "term-line term-you"); l.append(el("span", "term-prompt", "❯ "), text); return l; };
  const toPhase = async (text, b) => {
    try { await onPhase(text); log.append(line("term-sys", `✓ ${t("prj.talk_phase_done")}`)); }
    catch (err) { log.append(line("term-err", `⚠ ${err.message}`)); if (b) b.disabled = false; }
    end();
  };
  const turn = (e) => {
    if (e.role === "owner") return you(e.text);
    if (e.role === "judge") {                                     // a phase's verdict, said here too (owner, 23 Oct)
      const out = el("div", "term-out");
      out.append(renderMarkdown(e.text), el("div", "term-meta", `⎿ ${clock(e.t)} · ${t("prj.talk_judge")}`));
      return out;
    }
    const out = el("div", `term-out${e.error ? " term-err" : ""}`);
    out.append(e.error ? el("div", "", `⚠ ${e.text}`) : renderMarkdown(e.text));
    const m = el("div", "term-meta", meta(e));
    if (!e.error && onPhase) {
      lastAnswer = e.text;
      const b = el("button", "term-act", `↳ ${t("prj.talk_phase")}`);
      b.type = "button";
      b.addEventListener("click", () => { b.disabled = true; toPhase(e.text, b); });
      m.append(b);
    }
    out.append(m);
    return out;
  };
  const end = () => { log.scrollTop = log.scrollHeight; };
  const welcome = () => line("term-sys", `✻ ${t("prj.talk_welcome", { name })}`);
  let count = -1, judging = null;
  // the conversation's turns and the phases' verdicts in time order; while a phase is judged, «✻» as for a turn
  const show = (turns, conduct) => {
    lastAnswer = null;
    const verdicts = conduct.filter((e) => e.kind === "reply").map((e) => ({ role: "judge", text: e.text, t: e.t }));
    const items = [...turns, ...verdicts].sort((a, b) => (a.t || 0) - (b.t || 0));
    count = items.length;
    judging = conduct.some((e) => e.kind === "goal" && e.status === "judging");
    log.replaceChildren(welcome(), ...items.map(turn));
    if (judging) log.append(line("term-wait", `✻ ${t("prj.talk_judging")}`));
    end();
  };
  const both = async () => {
    const [d, c] = await Promise.all([call(base), call(`/v1/aurora/projects/${name}/conduct`)]);
    return [d, c.items];
  };
  const load = async () => {
    try {
      const [d, items] = await both();
      who.textContent = t(WHO[d.backend] || "prj.talk_local");
      show(d.turns, items);
    } catch (e) { log.replaceChildren(line("term-err", `⚠ ${t("ev.error", { m: e.message })}`)); }
  };
  // the slash commands: answered here, nothing sent
  const command = async (cmd) => {
    log.append(you(cmd));
    const c = cmd.split(/\s+/)[0].toLowerCase();
    if (["/aiuto", "/help"].includes(c)) {
      for (const h of t("prj.talk_help").split("\n")) log.append(line("term-sys", h));
    } else if (["/nuova", "/new"].includes(c)) {
      try { await call(`${base}/new`, { method: "POST", body: "{}" }); await load(); log.append(line("term-sys", `✓ ${t("prj.talk_new")}`)); }
      catch (e) { log.append(line("term-err", `⚠ ${e.message}`)); }
    } else if (["/fase", "/phase"].includes(c)) {
      if (!lastAnswer || !onPhase) log.append(line("term-err", `⚠ ${t("prj.talk_no_answer")}`));
      else await toPhase(lastAnswer);
    } else if (["/pulisci", "/clear"].includes(c)) {
      log.replaceChildren(welcome());
    } else log.append(line("term-err", `⚠ ${t("prj.talk_unknown", { c })}`));
    end();
  };
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text || input.disabled) return;
    input.value = "";
    grow();
    if (text.startsWith("/")) { await command(text); return; }
    input.disabled = go.disabled = true;
    log.append(turn({ role: "owner", text }));
    const wait = line("term-wait", "");
    const t0 = Date.now();
    let k = 0;
    const tick = () => { wait.textContent = `${SPIN[k++ % SPIN.length]} ${t("prj.talk_thinking", { s: Math.round((Date.now() - t0) / 1000) })}`; };
    tick();
    const timer = setInterval(tick, 400);
    log.append(wait);
    end();
    try { await call(base, { method: "POST", body: JSON.stringify({ text }) }); await load(); }
    catch (e) { wait.remove(); log.append(line("term-err", `⚠ ${t("ev.error", { m: e.message })}`)); }
    finally { clearInterval(timer); input.disabled = go.disabled = false; input.focus(); end(); }
  });
  // the line grows with what is written, up to a few lines
  const grow = () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 160)}px`; };
  input.addEventListener("input", grow);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  box.append(bar, log, form, hint);
  load();
  // alive (owner, 23 Oct: «entità vive»): a turn said elsewhere (another page, the API) comes in by itself
  let shown = false;
  const timer = setInterval(async () => {
    if (box.isConnected) shown = true;
    else if (shown) { clearInterval(timer); return; }
    if (input.disabled || !box.isConnected) return;               // a turn of this page is on its way: it reloads itself
    try {
      const [d, items] = await both();
      const n = d.turns.length + items.filter((e) => e.kind === "reply").length;
      const busy = items.some((e) => e.kind === "goal" && e.status === "judging");
      if (n !== count || busy !== judging) show(d.turns, items);
    } catch { /* the next look */ }
  }, 5000);
  return box;
}

// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💬 Talking with a project's conductor (ROADMAP N39 step 2, prj_talk): a conversation in the chat's look, kept per
// project and per user — on the Claude CLI one session resumed turn after turn, else the local model or an API with the
// turns sent again; who answers and what each turn cost (when the CLI says it) under each answer. The conductor talks,
// it does not act: under an answer, «🏗️ Fanne una fase» turns it into a phase's goal (the phases below).
import { call } from "../api.js";
import { clock, el, useCss } from "../dom.js";
import { t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

const WHO = { cli: "prj.talk_cli", cloud: "prj.talk_cloud", local: "prj.talk_local" };

function meta(e) {
  const parts = [clock(e.t)];
  if (e.role === "conductor") {
    if (e.backend) parts.push(t(WHO[e.backend] || "prj.talk_local"));
    if (e.backend !== "local") {
      parts.push(e.cost_usd != null ? t("prj.talk_cost", { usd: Number(e.cost_usd).toFixed(4) }) : t("prj.talk_cost_none"));
    }
    if (e.seconds != null) parts.push(`${e.seconds} s`);
    if (e.new_session) parts.push(t("prj.talk_new_session"));
  }
  return parts.join(" · ");
}

export function talkView(name, onPhase) {
  useCss("/static/css/chat.css");                          // the chat's messages and composer
  const box = el("div", "prj-talk");
  const head = el("div", "prj-talk-head");
  const who = el("span", "muted", "");
  const fresh = el("button", "", t("prj.talk_new"));
  head.append(el("strong", "", t("prj.talk_title")), who, fresh);
  const log = el("div", "prj-talk-log");
  const form = el("form", "ask prj-talk-ask");
  const input = el("textarea");
  input.rows = 2;
  input.placeholder = t("prj.talk_ph");
  const send = el("button", "send", t("chat.send"));
  send.type = "submit";
  form.append(input, send);
  const base = `/v1/aurora/projects/${name}/talk`;

  const turn = (e) => {
    const m = el("div", `msg ${e.role === "owner" ? "user" : "aurora"}${e.error ? " abstained" : ""}`);
    m.append(e.role === "owner" ? el("p", "", e.text) : renderMarkdown(e.text), el("div", "meta", meta(e)));
    if (e.role === "conductor" && !e.error && onPhase) {
      const b = el("button", "", t("prj.talk_phase"));
      b.addEventListener("click", async () => {
        b.disabled = true;
        try { await onPhase(e.text); b.textContent = t("prj.talk_phase_done"); } catch (err) { b.title = err.message; b.disabled = false; }
      });
      m.append(b);
    }
    return m;
  };
  const show = (turns) => {
    log.replaceChildren(...(turns.length ? turns.map(turn) : [el("p", "muted", t("prj.talk_none"))]));
    log.scrollTop = log.scrollHeight;
  };
  const load = async () => {
    try {
      const d = await call(base);
      who.textContent = t(WHO[d.backend] || "prj.talk_local");
      show(d.turns);
    } catch (e) { log.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); }
  };
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    send.disabled = true;
    input.value = "";
    log.querySelector("p.muted")?.remove();
    log.append(turn({ role: "owner", text, t: Date.now() / 1000 }), el("p", "muted prj-talk-wait", t("prj.talk_wait")));
    log.scrollTop = log.scrollHeight;
    try { await call(base, { method: "POST", body: JSON.stringify({ text }) }); }
    catch (e) { log.append(el("p", "error", t("ev.error", { m: e.message }))); }
    send.disabled = false;
    load();
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  fresh.addEventListener("click", async () => {
    if (!confirm(t("prj.talk_new_q"))) return;
    try { await call(`${base}/new`, { method: "POST", body: "{}" }); load(); } catch (e) { log.append(el("p", "error", e.message)); }
  });
  box.append(head, el("p", "muted", t("prj.talk_hint")), log, form);
  load();
  return box;
}

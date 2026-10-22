// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧑‍🔬 The conductor of a project (ROADMAP N39, prj_conduct): the owner writes in plain words, the conductor drafts the
// phase's goal, the owner reads it, changes it and starts it with one click; when the agent ends, the conductor's
// reply (done, what does not hold, the choices a/b/c) comes into the same conversation. Above the phases, the
// conversation with the conductor (project_talk.js).
import { call, followRun } from "../api.js";
import { clock, el } from "../dom.js";
import { t } from "../i18n.js";
import { talkView } from "./project_talk.js";

const WHO = { ask: "🙂", goal: "🎯", reply: "🧑‍🔬" };
const STATUS = { draft: "conduct.st_draft", running: "conduct.st_running", done: "conduct.st_done", failed: "conduct.st_failed" };
const cut = (v, n) => { const s = typeof v === "string" ? v : JSON.stringify(v ?? ""); return s.length > n ? `${s.slice(0, n)}…` : s; };

// 🖥️ one line of the live console for a run's event: what the agent does, as it does it
function line(ev) {
  const p = ev.payload || {};
  switch (ev.event) {
    case "agent.start": return `🚀 ${t("conduct.started")}`;
    case "tool.call": return `▶ ${p.name} ${cut(p.arguments, 160)}`;
    case "tool.result": return `  ${p.ok ? "✓" : "✗"} ${cut(p.text, 220)}`;
    case "project.run": return `  ⚙️ ${cut(p.command, 120)} → exit ${p.exit} · ${p.seconds} s`;
    case "vault.search": return `📚 vault: «${p.query}» → ${p.hits}`;
    case "agent.local": return `🖥️ ${t("conduct.local")}`;
    case "agent.finish": return `🏁 ${t("conduct.finished")}`;
    case "agent.error": return `⚠️ ${cut(p.message || p, 300)}`;
    default: return null;
  }
}

function liveConsole(runId, onEnd) {
  const box = el("pre", "prj-code prj-console");
  const head = el("p", "muted", "");
  const t0 = Date.now();
  let steps = 0;
  const tick = setInterval(() => { head.textContent = t("conduct.live", { s: Math.round((Date.now() - t0) / 1000), n: steps }); }, 1000);
  followRun(runId, (ev) => {
    const l = line(ev);
    if (ev.event === "tool.call") steps += 1;
    if (!l) return;
    const near = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    box.textContent += `${l}\n`;
    if (near) box.scrollTop = box.scrollHeight;                 // follows the end unless the owner scrolled up
  }, () => {}).finally(() => { clearInterval(tick); onEnd(); });
  return [head, box];
}

export function conductView(name) {
  const box = el("div", "prj-conduct");
  const log = el("div", "prj-conduct-log");
  const fail = (e) => log.append(el("p", "error", t("ev.error", { m: e.message })));
  const base = `/v1/aurora/projects/${name}/conduct`;

  const entry = (e) => {
    const row = el("div", `conduct-row conduct-${e.kind}`);
    row.append(el("p", "muted", `${WHO[e.kind] || "•"} ${clock(e.t)}${STATUS[e.status] ? ` · ${t(STATUS[e.status])}` : ""}`));
    if (e.kind === "goal" && e.status === "draft") {
      const text = el("textarea");
      text.rows = 12;
      text.value = e.text;
      const go = el("button", "approve", t("conduct.start"));
      const drop = el("button", "", t("conduct.drop"));
      go.addEventListener("click", async () => {
        go.disabled = drop.disabled = true;
        try { await call(`${base}/${e.id}/start`, { method: "POST", body: JSON.stringify({ text: text.value }) }); load(); }
        catch (err) { fail(err); go.disabled = drop.disabled = false; }
      });
      drop.addEventListener("click", async () => {
        try { await call(`${base}/${e.id}/drop`, { method: "POST", body: "{}" }); load(); } catch (err) { fail(err); }
      });
      row.append(text, el("div", "", ""), go, drop);
    } else {
      if (e.kind === "goal") {                    // a started goal folded: the room goes to the console and the reply
        const fold = el("details", "conduct-goal");
        fold.append(el("summary", "", e.text.split("\n").find((l) => l.trim()) || "🎯"), el("pre", "prj-code conduct-text", e.text));
        row.append(fold);
      } else {
        row.append(el("pre", "prj-code conduct-text", e.text));
      }
      if (e.kind === "goal" && e.status === "running" && e.run_id) {
        row.append(...liveConsole(e.run_id, () => setTimeout(load, 3000)));      // the judge's reply follows the end
      }
      if (e.kind === "goal" && e.status === "failed") {
        const again = el("button", "approve", t("conduct.again"));
        again.addEventListener("click", async () => {
          again.disabled = true;
          try { await call(`${base}/${e.id}/start`, { method: "POST", body: "{}" }); load(); }
          catch (err) { fail(err); again.disabled = false; }
        });
        row.append(again);
      }
    }
    return row;
  };

  const load = async () => {
    try {
      const d = await call(base);
      log.replaceChildren(...d.items.filter((e) => e.status !== "dropped").map(entry));
      if (!d.items.length) log.append(el("p", "muted", t("conduct.none")));
      log.scrollTop = log.scrollHeight;
    } catch (e) { fail(e); }
  };

  const words = el("textarea");
  words.rows = 3;
  words.placeholder = t("conduct.ph");
  const send = el("button", "approve", t("conduct.send"));
  send.addEventListener("click", async () => {
    if (!words.value.trim()) return;
    send.disabled = true;
    send.textContent = t("conduct.drafting");
    try {
      await call(base, { method: "POST", body: JSON.stringify({ text: words.value }) });
      words.value = "";
      load();
    } catch (e) { fail(e); }
    send.disabled = false;
    send.textContent = t("conduct.send");
  });
  // 💬 the conversation first (N39 step 2), the phases below it: an answer becomes a phase's draft with one click
  const phases = el("details", "prj-phases");
  phases.open = true;
  phases.append(el("summary", "", t("conduct.title")), el("p", "muted", t("conduct.hint")), log, words, send);
  const toPhase = async (text) => {
    await call(base, { method: "POST", body: JSON.stringify({ text }) });
    phases.open = true;
    load();
  };
  box.append(talkView(name, toPhase), phases);
  load();
  return box;
}

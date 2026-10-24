// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧑‍🔬 The conductor of a project (ROADMAP N39, prj_conduct): the owner writes in plain words, the conductor drafts the
// phase's goal, the owner reads it, changes it and starts it with one click; when the agent ends, the conductor's
// reply (done, what does not hold, the choices a/b/c) comes into the same conversation. Above the phases, the
// conversation with the conductor (project_talk.js), and under it the activity: the running phase line by line.
import { call, followRun } from "../api.js";
import { clock, el } from "../dom.js";
import { t } from "../i18n.js";
import { talkView } from "./project_talk.js";

const WHO = { ask: "🙂", goal: "🎯", reply: "🧑‍🔬" };
const STATUS = { draft: "conduct.st_draft", running: "conduct.st_running", judging: "conduct.st_judging", done: "conduct.st_done",
  failed: "conduct.st_failed" };
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
    case "agent.say": return p.text ? `💬 ${cut(p.text, 300)}` : null;
    case "agent.nudge": return `↻ ${p.reason || ""}`;
    case "agent.finish": return `🏁 ${t("conduct.finished")}`;
    case "agent.error": return `⚠️ ${cut(p.message || p, 300)}`;
    default: return null;
  }
}

// 🖥️ the project's activity (owner, 23 Oct: «sotto tutto quello che succede e sopra il conduttore… i terminali li
// reputo entità vive su ciò che sta succedendo dentro il progetto anche se io sto solo guardando»): every 3 s one look
// at the project (prj_live: the conductor's entries, the conversation, the saves, the files written) compared with the
// last one, each change a line; the steps of a phase that runs come line by line from its run's events.
const PHASE = { draft: "conduct.act_draft", running: "conduct.act_running", judging: "conduct.act_judging", done: "conduct.act_done",
  failed: "conduct.act_failed" };

function activityView(name, onEnd) {
  const box = el("div", "prj-talk term prj-activity");
  const bar = el("div", "term-bar");
  const state = el("span", "term-who", "");
  bar.append(el("span", "term-dots", "● ● ●"), el("span", "term-title", `${t("conduct.activity")} — ${name}`), state);
  const log = el("div", "term-log");
  box.append(bar, log);
  const seen = { conduct: new Map(), talk: -1, commits: new Set(), files: new Map() };
  let following = null, steps = 0, t0 = 0, first = true, shown = false;
  const add = (text, cls, when) => {
    const near = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
    log.append(el("div", `term-line ${cls || ""}`, `${clock(when || Date.now() / 1000)}  ${text}`));
    while (log.childElementCount > 600) log.firstChild.remove();
    if (near) log.scrollTop = log.scrollHeight;                 // follows the end unless the owner scrolled up
  };
  const tick = () => {
    state.textContent = following ? t("conduct.live", { s: Math.round((Date.now() - t0) / 1000), n: steps }) : t("conduct.listening");
  };
  const follow = (run) => {
    following = run; steps = 0; t0 = Date.now();
    followRun(run, (ev) => {
      if (following !== run) return;
      if (ev.seq === 1 && ev.ts) t0 = ev.ts * 1000;              // the run's own start, not when the page came
      if (ev.event === "tool.call") steps += 1;
      const l = line(ev);
      if (l) add(`│ ${l}`, ev.event === "tool.result" && !(ev.payload || {}).ok ? "term-err" : "", ev.ts);
    }, () => {}).catch((e) => add(`⚠ ${e.message}`, "term-err")).finally(() => {
      if (following === run) { following = null; tick(); onEnd(); }
    });
  };
  const look = async () => {
    const d = await call(`/v1/aurora/projects/${name}/live`);
    const lines = [];                                            // [when, text, cls]
    for (const e of d.conduct) {
      const was = seen.conduct.get(e.id);
      if (was === e.status && seen.conduct.has(e.id)) continue;
      seen.conduct.set(e.id, e.status);
      if (e.kind === "ask") lines.push([e.t, `🙂 ${t("conduct.act_ask")}: ${e.head}`]);
      else if (e.kind === "reply") lines.push([e.t, `🧑‍🔬 ${t("conduct.act_reply")}: ${e.head}`, "term-sys"]);
      else if (e.kind === "goal" && PHASE[e.status]) lines.push([first ? e.t : Date.now() / 1000, `🎯 ${t(PHASE[e.status])}: ${e.head}`, e.status === "failed" ? "term-err" : ""]);
    }
    if (d.talk.n !== seen.talk) {
      const fresh = seen.talk < 0 ? d.talk.last.slice(-2) : d.talk.last.slice(-(d.talk.n - seen.talk));
      for (const x of fresh) lines.push([x.t, `💬 ${x.role === "owner" ? t("conduct.act_you") : t("conduct.act_conductor")}: ${x.head}`]);
      seen.talk = d.talk.n;
    }
    for (const c of [...d.commits].reverse()) {
      if (seen.commits.has(c.hash)) continue;
      seen.commits.add(c.hash);
      if (!first || c === d.commits[0]) lines.push([c.t, `💾 ${t("conduct.act_saved")}: ${c.msg}`]);
    }
    for (const f of d.files) {
      const was = seen.files.get(f.path);
      seen.files.set(f.path, f.t);
      if (!first && was !== f.t) lines.push([f.t, `📝 ${f.path} (${f.size} B)`]);
    }
    lines.sort((a, b) => a[0] - b[0]);
    for (const [when, text, cls] of (first ? lines.slice(-12) : lines)) add(text, cls, when);
    if (first && !lines.length) add(t("conduct.no_run"), "term-sys");
    first = false;
    if (d.running && d.running !== following) follow(d.running);
  };
  const timer = setInterval(() => {
    if (box.isConnected) shown = true;
    else if (shown) { clearInterval(timer); return; }            // the page left: stop looking
    tick();
    if (Math.round(Date.now() / 1000) % 3 === 0) look().catch(() => {});
  }, 1000);
  look().catch((e) => add(`⚠ ${e.message}`, "term-err"));
  tick();
  return box;
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
  box.append(talkView(name, toPhase), activityView(name, () => setTimeout(load, 3000)), phases);
  load();
  return box;
}

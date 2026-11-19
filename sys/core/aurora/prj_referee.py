# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧑‍⚖️ The severe referee of a project's phase (ROADMAP N142; owner: «dare ad Aurora, negli agenti dei progetti, le
previsioni congelate e il revisore severo»; decided: automatic at the end of each phase).

When a phase ends, before the conductor's reply, an adversarial AI reviewer on the Claude CLI — another model than
the conductor's (AURORA_REFEREE_MODEL) — reads what the phase left: its goal, the files it changed (git and the
files' times), the documents it wrote, the predictions it froze (prj_prereg). Never the agent's report, the
conductor's reply or the talk: it judges the work, not what was said of it. Its tools are Aurora's, through the same
relay as the conductor's (prj_act.cli: the masking, SSCC on the vault and long outputs): list_files, read_file,
search_vault, and run in a READ-ONLY cage (prj_run readonly: the project bound read only, scratch in a private
tmpfs). No write tool: Aurora writes its review to `reviews/REV_NNN.md`, with the cost and the seconds, and the
conductor's reply starts with its verdict. Past AURORA_REFEREE_MAX_USD or AURORA_REFEREE_TIMEOUT_S it stops, said.
A «local» project gets no cloud referee: «revisione severa non eseguita: progetto locale». The referee needs the
agent role on the Claude CLI (the conductor's condition to act): on an API or the local model it is skipped, said.
The documents are given to it whole (up to DOC_CHARS each), never compressed by SSCC: they are what is judged.
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import time
from pathlib import Path

from . import prj_act, prj_conduct, prj_prereg, prj_run, sys_config, sys_log

DIR = "reviews"
DOC_SUFFIX = (".md", ".tex", ".txt", ".rst")
DOC_CHARS = 12000               # each document's text given at once (the rest: read_file)
DOCS_CHARS = 48000              # all the documents together
FILES_MAX = 300                 # changed files listed
VERDICT = re.compile(r"VERDICT:\s*(ACCEPT|MINOR REVISION|MAJOR REVISION|REJECT)[^\n]*", re.I)
HEAD = re.compile(r"^<!-- aurora-review (\{.*\}) -->", re.M)

TOOLS = [({**t, "description": "Run a shell command in a READ-ONLY cage of the project (no network; nothing can be "
           "written in the project; scratch in /tmp): re-run its code, its tests, recompute a number."}
          if t["name"] == "run" else t) for t in prj_act.TOOLS
         if t["name"] in ("list_files", "read_file", "search_vault", "run", "proof_check")]   # proof_check: N143

PROMPT = """You are a severe, adversarial referee of the project «{name}». You are an AI reviewer: say so in your
second line. You did not do the work and you do not trust it. Below are the phase's goal, the files it changed, the
documents it wrote and the predictions it froze before its experiments. With the tools of the «aurora» server you can
list and read the project's files, search Aurora's vault of verified papers, run commands in a READ-ONLY cage (no
network; nothing you run changes the project; scratch in /tmp) and re-check a Lean proof with proof_check (a theorem
counts as proved only when it says PROVED). You have no write tool.
1. For EACH claim in the phase's documents (a result, a number, a derivation, «verified», a citation) give a verdict
   FATAL / MAJOR / MINOR / OK, its location (file and section or line) and its quantitative impact when you measured
   it (re-run the code, recompute); otherwise write «not measured». Never invent a measurement.
2. Check each frozen prediction against the results: frozen before the result? does the outcome match what the code
   gives when you run it? Entries «changed after freeze» do not support any claim.
3. Look for what a hostile referee looks for: numbers with no source, thresholds with no computed ceiling, tests that
   cannot fail, circular checks, cherry-picked cases, claims beyond the evidence, citations the vault does not hold.
4. End with **Must fix**: a numbered list, the most serious first.
Your answer's FIRST line must be exactly:
VERDICT: <ACCEPT | MINOR REVISION | MAJOR REVISION | REJECT> — FATAL <n>, MAJOR <n>, MINOR <n>, OK <n>
then a table | # | claim | location | verdict | impact |, then the predictions' check, then Must fix. Write in
{lang}. Placeholders like [PERSON_1] are private values masked by Aurora: use them as they are."""

SAY = {"it": {"local": "🧑‍⚖️ Revisione severa non eseguita: progetto locale.",
              "nocli": "🧑‍⚖️ Revisione severa non eseguita: serve la CLI di Claude per il ruolo agente (ora: {kind}).",
              "done": "🧑‍⚖️ **Revisione severa** (revisore IA, {model}): {verdict} · {cost} · {s} s · `{file}`",
              "budget": "🧑‍⚖️ Revisione severa interrotta: superato il tetto di spesa (AURORA_REFEREE_MAX_USD = {max} USD) · `{file}`",
              "time": "🧑‍⚖️ Revisione severa interrotta: superato il tempo massimo (AURORA_REFEREE_TIMEOUT_S = {max} s) · `{file}`",
              "failed": "🧑‍⚖️ Revisione severa non riuscita: {why}",
              "nocost": "costo non misurato", "noverdict": "verdetto non dichiarato"},
       "en": {"local": "🧑‍⚖️ Severe review not run: local project.",
              "nocli": "🧑‍⚖️ Severe review not run: it needs the Claude CLI for the agent role (now: {kind}).",
              "done": "🧑‍⚖️ **Severe review** (AI reviewer, {model}): {verdict} · {cost} · {s} s · `{file}`",
              "budget": "🧑‍⚖️ Severe review stopped: spending ceiling exceeded (AURORA_REFEREE_MAX_USD = {max} USD) · `{file}`",
              "time": "🧑‍⚖️ Severe review stopped: time limit exceeded (AURORA_REFEREE_TIMEOUT_S = {max} s) · `{file}`",
              "failed": "🧑‍⚖️ Severe review failed: {why}",
              "nocost": "cost not measured", "noverdict": "no verdict stated"}}


def _say(lang: str) -> dict:
    return SAY["en" if str(lang).startswith("en") else "it"]


def model_for(cfg: sys_config.Config, conductor: str) -> str:
    """The referee's model, never the conductor's: the same one set → sonnet, or opus when the conductor is on sonnet."""
    m = str(cfg["AURORA_REFEREE_MODEL"] or "sonnet").strip()
    return ("opus" if conductor == "sonnet" else "sonnet") if m == conductor else m


def _git(root: Path, *a: str) -> str:
    try:
        r = subprocess.run(["git", *prj_run.GIT_SAFE, "-c", f"safe.directory={root}", "-C", str(root), *a],
                           capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def changed_files(cfg: sys_config.Config, project: str, since: float | None) -> list[str]:
    """The files the phase changed: written since it began (their times) and committed since (git), never prereg/ nor
    reviews/ (given apart, or Aurora's). No `since`: the whole project."""
    root = prj_run.project_dir(cfg, project)
    snap = prj_run.snapshot(root)
    out = {k for k, (mt, _) in snap.items() if since is None or mt / 1e9 >= since}
    if since is not None and (root / ".git").is_dir():
        when = datetime.datetime.fromtimestamp(since, datetime.timezone.utc).isoformat()
        out |= {x.strip() for x in _git(root, "log", f"--since={when}", "--name-only", "--format=").splitlines() if x.strip()}
    return sorted(f for f in out if not prj_prereg.locked(f))[:FILES_MAX]


def inputs(cfg: sys_config.Config, project: str, goal: str, since: float | None) -> str:
    """What the referee reads: the goal, the changed files, the documents, the phase's frozen predictions. Never the
    agent's report nor the conductor's words (none is even taken here)."""
    root = prj_run.project_dir(cfg, project)
    files = changed_files(cfg, project, since)
    parts = [f"## The phase's goal\n{goal.strip() or '(no goal given: review the project as it is)'}",
             "## Files changed in the phase\n" + ("\n".join(f"- {f}" + ("" if (root / f).exists() else " (removed)")
                                                         for f in files) or "(none)")]
    room = DOCS_CHARS
    for f in files:
        p = root / f
        if p.suffix.lower() not in DOC_SUFFIX or not p.is_file() or room <= 0:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        cut = text[:min(DOC_CHARS, room)]
        room -= len(cut)
        more = f"\n… {len(text)} characters in all: read_file for the rest" if len(cut) < len(text) else ""
        parts.append(f"## Document {f}\n{cut}{more}")
    rows = prj_prereg.entries(cfg, project, since)
    pre = []
    for e in rows:
        try:
            body = (root / e["file"]).read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            body = "(the predictions' file is missing)"
        pre.append(json.dumps({k: e.get(k) for k in ("id", "title", "created", "status", "outcomes", "evidence",
                                                      "closed", "integrity", "changed", "counted")}, ensure_ascii=False)
                   + "\n" + body)
    parts.append("## Frozen predictions of the phase (prereg/LEDGER.jsonl, kept by Aurora)\n"
                 + ("\n\n".join(pre) if pre else "(none frozen in this phase)"))
    return "\n\n".join(parts)


def _next(root: Path) -> int:
    nums = [int(m.group(1)) for p in (root / DIR).glob("REV_*.md") if (m := re.fullmatch(r"REV_(\d+)\.md", p.name))]
    return max(nums, default=0) + 1


def _write(root: Path, head: dict, body: str) -> str:
    n = _next(root)
    rel = f"{DIR}/REV_{n:03d}.md"
    head = {**head, "n": n, "file": rel}
    cost = f"{head['cost_usd']:.2f} USD" if isinstance(head.get("cost_usd"), (int, float)) else "not measured"
    text = [f"<!-- aurora-review {json.dumps(head, ensure_ascii=False)} -->",
            f"# Severe review REV_{n:03d} — an AI reviewer", "",
            f"- Date (UTC): {head['created']}",
            f"- Referee: Claude CLI, model {head['model']} (the conductor's: {head['conductor']}) — an AI, not a person",
            f"- Status: {head['status']} · cost {cost} · {head['seconds']} s",
            f"- Read: {head['changed']} changed files, {head['frozen']} frozen entries (never the agent's report)",
            f"- Phase goal: {head['goal']}", "", "---", "", body.strip() or "(no text)", ""]
    (root / DIR).mkdir(exist_ok=True)
    (root / rel).write_text("\n".join(text), encoding="utf-8")
    return rel


def review(cfg: sys_config.Config, project: str, goal: str, since: float | None, cc, lang: str = "it") -> dict:
    """One review on the Claude CLI → {status done|stopped|failed, verdict, summary, text, file, cost_usd, seconds}."""
    from .sec_mask import KEEP, Pseudonymizer
    run = prj_act.Run(cfg, project, Pseudonymizer(cfg), goal)
    cfg = run.cfg                                         # the user's own config, fixed (C517)
    run.tools, run.readonly, run.notes = TOOLS, True, False
    say, root = _say(lang), prj_run.project_dir(cfg, project)
    model, max_usd, limit = model_for(cfg, cc.model), float(cfg["AURORA_REFEREE_MAX_USD"]), int(cfg["AURORA_REFEREE_TIMEOUT_S"])
    system = PROMPT.format(name=project, lang="English" if str(lang).startswith("en") else "Italian")
    user = inputs(cfg, project, goal, since)
    p = run.mask
    ms, mu = p.mask(sys_config.personal(system, cfg)), p.mask(user)
    if p.to_val:
        ms += KEEP
    folder = cfg.path("AURORA_STATUS_DIR") / "claude_code" / "referee" / str(run.user or "_") / project
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)     # empty: no project instructions
    with prj_act._lock:
        prj_act._RUNS[run.token] = run
    t0 = time.time()
    try:
        result, _, _, err = prj_act.cli(run, cc, ms, mu, folder, "", True, model=model, max_usd=max_usd,
                                        timeout_s=limit, persist=False)
    finally:
        with prj_act._lock:
            prj_act._RUNS.pop(run.token, None)
    seconds = round(time.time() - t0, 1)
    if result is not None:
        cc._account(result, seconds)
    r = result or {}
    cost = r.get("total_cost_usd")
    text = p.unmask(str(r.get("result") or "")).strip()
    sub = str(r.get("subtype") or "")
    if r and not r.get("is_error") and text:
        status, why = "done", ""
    elif "budget" in sub or (isinstance(cost, (int, float)) and cost > max_usd):
        status, why = "stopped", "budget"
    elif seconds >= limit:
        status, why = "stopped", "time"
    else:
        status, why = "failed", (text or sub or err[-300:] or "no answer")[:300]
    m = VERDICT.search(text)
    verdict = m.group(0).strip() if m else ""
    head = {"status": status, "why": why, "verdict": verdict, "model": model, "conductor": cc.model,
            "cost_usd": cost, "seconds": seconds, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "since": since, "goal": " ".join(goal.split())[:200].replace("--", "—"), "changed": len(changed_files(cfg, project, since)),
            "frozen": len(prj_prereg.entries(cfg, project, since))}
    rel = _write(root, head, text or f"({status}: {why})")
    if status == "done":
        summary = say["done"].format(model=model, verdict=verdict or say["noverdict"], s=seconds, file=rel,
                                     cost=f"{cost:.2f} USD" if isinstance(cost, (int, float)) else say["nocost"])
    elif why in ("budget", "time"):
        summary = say[why].format(max=max_usd if why == "budget" else limit, file=rel)
    else:
        summary = say["failed"].format(why=why)
    sys_log.get_logger("projects").info("audit: referee of %s for %s: %s, %s s, cost %s", project, run.user, status,
                                        seconds, cost)
    return {"status": status, "verdict": verdict, "summary": summary, "text": text if status == "done" else "",
            "file": rel, "cost_usd": cost, "seconds": seconds}


def phase(cfg: sys_config.Config, project: str, goal: str, since: float | None, pipeline, lang: str = "it") -> dict | None:
    """At a phase's end (api/projects_conduct) or by hand: the review, or why there is none (said); None when the
    referee is off."""
    if not cfg["AURORA_REFEREE_ENABLED"]:
        return None
    say = _say(lang)
    if prj_conduct.local(cfg, project):
        return {"status": "skipped", "summary": say["local"]}
    from . import prj_talk
    try:
        kind, llm = prj_talk.backend(cfg, project, pipeline)
        if kind != "cli":
            return {"status": "skipped", "summary": say["nocli"].format(kind=kind)}
        return review(cfg, project, goal, since, llm.inner, lang)
    except Exception as e:                                # noqa: BLE001 — never the phase's reply lost for it: said
        sys_log.get_logger("projects").warning("referee of %s failed: %s", project, e)
        return {"status": "failed", "summary": say["failed"].format(why=f"{type(e).__name__}: {str(e)[:200]}")}


def reviews(cfg: sys_config.Config, project: str) -> list[dict]:
    """The project's reviews, newest first: each one's header (verdict, status, cost, seconds) and its text."""
    root = prj_run.project_dir(cfg, project)
    out = []
    for f in sorted((root / DIR).glob("REV_*.md"), reverse=True)[:50]:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            head = json.loads(m.group(1)) if (m := HEAD.search(text)) else {"file": f"{DIR}/{f.name}"}
        except (OSError, ValueError):
            continue
        out.append({**head, "text": text[:20000]})
    return out

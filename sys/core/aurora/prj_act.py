# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧑‍🔬 The conductor acts (ROADMAP N39, step 3; owner, 28 Oct: «il conduttore deve diventare indipendente come tu lo
sei stato in ogni conduttura di ogni progetto e dare i medesimi feedback… ovviamente sscc attivo e anche mascheramento
privacy di default»).

On the Claude CLI a conductor's turn is no longer only words: the CLI works in the project — reads, writes, edits,
runs the tests, looks in the vault — and answers with what it did. It never touches the project itself: its own tools
are off (--tools ""), no settings, no MCP but one, Aurora's (--strict-mcp-config): a relay (script/mcp_relay.py)
that hands every call to the API with this run's token. Here, in the API, each call is checked and done:
  - a path stays inside the project's folder (resolved: no «..», no link out), .git is read only;
  - a command runs in the project's cage (prj_run: no network, no home, only the project writable);
  - an edit needs its anchor exactly once (the owner's law 3), else it is refused and said;
  - what goes back to the cloud is masked with the session's own map (sec_mask: the same placeholder in every turn
    the CLI keeps) and, for prose (the vault's passages, a long output), compressed by SSCC (txt_compress) when
    AURORA_CLOUD_COMPRESSION is on; what comes from the cloud is unmasked before it is written or run.
A «local» project never comes here (prj_talk.backend). The turn runs in the background; its steps are kept in the
user's state (act.json) for the page's console, and the answer is the conversation's next turn.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from . import prj_conduct, prj_run, sys_config, sys_context, sys_log, sys_seal

READ_LINES = 400                # lines of a file returned at once
LIST_MAX = 400                  # entries of a listing
SSCC_FROM = 4000                # characters of prose over which SSCC compresses what goes back
STEPS_KEEP = 200

ACT = """You are the conductor of the project «{name}» for its owner: a lead engineer who does the work, in their
language ({lang}). You work ONLY through the tools of the «aurora» server: list_files, read_file, write_file,
edit_file, run (a shell command in the project's cage: no network), search_vault (Aurora's vault: verified papers,
often newer than you — look there BEFORE choosing a method), project_notes (the open items and the phases so far).
How you work, every time:
1. read the project's notes and the files that matter before changing anything;
2. do the work in small verified steps: after a change, run the tests or the program and read what came back;
3. edit_file needs its «old» text exactly once in the file: copy it from read_file, never from memory;
4. never write a number you did not measure or read in a source; a threshold only after its ceiling is computed;
5. keep the open items file up to date (what is done, what is left) when you finish a step.
Then answer the owner, short, with these parts (bold titles, a table when it helps):
**Fatto** — what you changed and how you checked it (the command and its result);
**Non regge** — what does not hold or failed, said plainly, your own mistakes first;
**Da decidere** — only what the owner must choose, as a / b / c with your recommendation first;
**Non ho misurato** — the honest list of what you did not check.
Placeholders like [PERSON_1] are private values masked by Aurora: use them as they are. The project's policy:
{policy}.

{context}"""

TOOLS = [
    {"name": "list_files", "description": "The project's files under a folder (relative to the project), with sizes.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}}},
    {"name": "read_file", "description": f"A text file of the project with line numbers, {READ_LINES} lines from «offset».",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "default": 1}},
                     "required": ["path"]}},
    {"name": "write_file", "description": "Create or replace a file of the project with «content».",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                     "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace «old» with «new» in a file; «old» must be there exactly once.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                                      "new": {"type": "string"}}, "required": ["path", "old", "new"]}},
    {"name": "run", "description": "Run a shell command in the project's folder, in a cage with no network (tests, the "
     "program). Returns the exit code, the seconds, the output's end and the files it changed.",
     "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "search_vault", "description": "Search Aurora's vault of verified documents; cite the titles you use.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
                     "required": ["query"]}},
    {"name": "project_notes", "description": "The project's open items, its documents and the phases so far.",
     "inputSchema": {"type": "object", "properties": {}}},
]


class Run:
    def __init__(self, cfg, project: str, mask, goal: str):
        self.cfg, self.project, self.mask, self.goal = cfg, project, mask, goal
        self.user = cfg.user
        self.token = secrets.token_urlsafe(32)
        self.proc: subprocess.Popen | None = None
        self.stopped = False


_RUNS: dict[str, Run] = {}
_lock = threading.Lock()


def lookup(token: str) -> Run | None:
    """The run a relay's token belongs to, compared in constant time; None when no run of that token is going."""
    with _lock:
        for t, r in _RUNS.items():
            if hmac.compare_digest(t.encode(), str(token or "").encode()):
                return r
    return None


def _state(cfg, project: str) -> Path:
    from . import prj_talk
    return prj_talk._dir(cfg, project) / "act.json"


def working(cfg, project: str) -> dict | None:
    """The turn on its way ({since, steps}) or None."""
    try:
        d = json.loads(sys_seal.read_any(cfg, _state(cfg, project), cfg.user))
    except (OSError, ValueError):
        return None
    return d if d.get("working") else None


def _note(cfg, project: str, **changes) -> None:
    f = _state(cfg, project)
    try:
        d = json.loads(sys_seal.read_any(cfg, f, cfg.user))
    except (OSError, ValueError):
        d = {}
    steps = d.get("steps", [])
    if "step" in changes:
        steps = (steps + [{"t": time.time(), "text": changes.pop("step")[:300]}])[-STEPS_KEEP:]
    d.update(changes, steps=steps)
    sys_seal.write(cfg, f, json.dumps(d, ensure_ascii=False).encode("utf-8"), cfg.user, "state")   # the steps quote the turn (N64)


# ---- the tools, done here for the relay ------------------------------------------------------------------------
def _inside(run: Run, rel: str, write: bool = False) -> Path:
    root = prj_run.project_dir(run.cfg, run.project).resolve()
    p = (root / str(rel or ".")).resolve()
    if p != root and root not in p.parents:
        raise ValueError(f"{rel}: outside the project")
    if write and (p == root or ".git" in p.relative_to(root).parts):
        raise ValueError(f"{rel}: not writable (the project's folder itself or its .git)")
    return p


def _prose(run: Run, text: str) -> str:
    """SSCC on what goes back to the cloud (prose only: never a file to edit), when the switch is on."""
    if len(text) <= SSCC_FROM or not run.cfg["AURORA_CLOUD_COMPRESSION"]:
        return text
    from . import txt_compress
    out, stats = txt_compress.compress(run.goal, text, int(run.cfg["AURORA_CLOUD_KEEP_PCT"]))
    sys_log.trace("projects", "conductor.sscc", {"in": stats["chars_in"], "out": stats["chars_out"]})
    return out


def _do(run: Run, name: str, a: dict) -> str:
    u = run.mask.unmask                                   # what the cloud wrote: the real values back
    if name == "list_files":
        base = _inside(run, u(str(a.get("path", "."))))
        root = prj_run.project_dir(run.cfg, run.project).resolve()
        rows = []
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(root)
            if {".git", ".venv", "__pycache__", "node_modules"} & set(rel.parts):
                continue
            rows.append(f"{rel}{'/' if p.is_dir() else ''}\t{p.stat().st_size if p.is_file() else ''}")
            if len(rows) >= LIST_MAX:
                rows.append(f"… more than {LIST_MAX}: list a sub-folder")
                break
        return "\n".join(rows) or "(empty)"
    if name == "read_file":
        p = _inside(run, u(str(a.get("path", ""))))
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(a.get("offset") or 1))
        part = lines[start - 1:start - 1 + READ_LINES]
        more = f"\n… {len(lines)} lines in all: read on from offset {start + READ_LINES}" if len(lines) >= start + READ_LINES else ""
        return "\n".join(f"{i}\t{x}" for i, x in enumerate(part, start)) + more
    if name == "write_file":
        p = _inside(run, u(str(a.get("path", ""))), write=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(u(str(a.get("content", ""))), encoding="utf-8")
        return f"written {p.relative_to(prj_run.project_dir(run.cfg, run.project).resolve())}"
    if name == "edit_file":
        p = _inside(run, u(str(a.get("path", ""))), write=True)
        text, old = p.read_text(encoding="utf-8"), u(str(a.get("old", "")))
        n = text.count(old) if old else 0
        if n != 1:                                       # law 3: a unique anchor, else nothing changes
            return f"REFUSED: «old» found {n} times in {a.get('path')}; read the file again and give a unique piece"
        p.write_text(text.replace(old, u(str(a.get("new", ""))), 1), encoding="utf-8")
        return f"edited {a.get('path')}"
    if name == "run":
        r = prj_run.run(run.cfg, run.project, u(str(a.get("command", ""))))
        return _prose(run, f"exit {r['exit']} in {r['seconds']} s; changed: {', '.join(r['changed']) or 'nothing'}\n{r['output']}")
    if name == "search_vault":
        from . import agt_vault
        from .api.core import pipeline
        return _prose(run, agt_vault.run(pipeline(run.user), {"query": u(str(a.get("query", ""))),
                                                              "top_k": a.get("top_k")}, lambda *x: None))
    if name == "project_notes":
        return prj_conduct.context(run.cfg, run.project)
    raise ValueError(f"no tool {name}")


def call(run: Run, name: str, args: dict) -> dict:
    """A relay's tools/call: {"text", "error"}, the text masked for the cloud."""
    with sys_context.acting_as(run.user):
        try:
            text, error = _do(run, name, args if isinstance(args, dict) else {}), False
        except (OSError, ValueError, RuntimeError) as e:
            text, error = f"ERROR: {e}", True
    shown = ", ".join(f"{k}={str(run.mask.unmask(str(v)))[:60]!r}" for k, v in (args or {}).items() if k != "content")
    _note(run.cfg, run.project, step=f"{'✗' if error else '⏺'} {name}({shown})")
    sys_log.get_logger("projects").info("audit: conductor of %s for %s: %s %s", run.project, run.user, name, "failed" if error else "ok")
    return {"text": run.mask.mask(str(text)), "error": error}


# ---- the turn ------------------------------------------------------------------------------------------------
def start(cfg, project: str, cc, text: str, system: str, s: dict, lang: str) -> dict:
    """The owner's words → a CLI run with Aurora's tools, in the background; the answer comes as a turn."""
    from . import prj_talk
    from .sec_mask import Pseudonymizer
    if working(cfg, project):
        raise RuntimeError("the conductor is already working on this project: wait, or /stop")
    p = Pseudonymizer(cfg)
    p.to_val.update(s.get("mask", {}))
    p.to_ph.update({v: k for k, v in p.to_val.items()})
    run = Run(cfg, project, p, text)
    with _lock:
        _RUNS[run.token] = run
    prj_talk._add(cfg, project, "owner", text)
    _state(cfg, project).unlink(missing_ok=True)
    _note(cfg, project, working=True, since=time.time())
    sys_context.start(_work, run, cc, system, s, name=f"conductor-{project}")
    return {"working": True}


def stop(cfg, project: str) -> dict:
    with _lock:
        runs = [r for r in _RUNS.values() if r.project == project and r.user == cfg.user]
    for r in runs:
        r.stopped = True
        if r.proc and r.proc.poll() is None:
            r.proc.terminate()
    return {"stopped": len(runs)}


def _command(run: Run, cc, system_file: str, mcp_file: str, sid: str, resume: bool) -> list[str]:
    allowed = ",".join(f"mcp__aurora__{t['name']}" for t in TOOLS)
    cmd = [cc.bin, "-p", "--model", cc.model, "--tools", "", "--setting-sources", "", "--strict-mcp-config",
           "--mcp-config", mcp_file, "--allowedTools", allowed, "--system-prompt-file", system_file,
           "--output-format", "stream-json", "--verbose", "--max-budget-usd", str(run.cfg["AURORA_CONDUCTOR_MAX_USD"])]
    return cmd + (["--resume", sid] if resume else ["--session-id", sid])


def _vault_first(run: Run) -> str:
    """The vault on the owner's words, looked up before the conductor starts (owner, 28 Oct, after a trial where the CLI
    never searched it: the search is Aurora's, always, not left to the model); compressed by SSCC when long."""
    from . import agt_vault
    try:
        from .api.core import pipeline
        with sys_context.acting_as(run.user):
            found = agt_vault.run(pipeline(run.user), {"query": f"{run.project.replace('-', ' ')}: {run.goal}"[:300],
                                                       "top_k": 5}, lambda *x: None)
    except Exception as e:                               # noqa: BLE001 — no vault here (a test, the models down): said
        found = f"(the vault could not be searched: {type(e).__name__})"
    _note(run.cfg, run.project, step="⏺ search_vault (Aurora, before the start)")
    return "\n\n## The vault on this request (searched by Aurora before you started; search again for more)\n" + _prose(run, found)


def _work(run: Run, cc, system: str, s: dict) -> None:
    from . import prj_talk
    from .mdl_router import _cloud_call
    from .sec_mask import KEEP
    cfg, project, p = run.cfg, run.project, run.mask
    system += _vault_first(run)                          # the vault looked up by Aurora before the CLI starts
    ms, mu = p.mask(sys_config.personal(system, cfg)), p.mask(run.goal)
    if p.to_val:
        ms += KEEP
    folder = cfg.path("AURORA_STATUS_DIR") / "claude_code" / "talk" / str(run.user or "_") / project
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)    # empty: no project instructions, the session's home
    relay = Path(__file__).resolve().parent.parent / "script" / "mcp_relay.py"
    url = f"http://127.0.0.1:{cfg['AURORA_API_PORT']}/v1/aurora/conductor"
    sid, fresh = s.get("session") or "", not s.get("session")
    t0, result, cost = time.time(), None, None
    files = []
    try:
        for content, suffix in ((ms, ".txt"), (json.dumps({"mcpServers": {"aurora": {
                "command": sys.executable, "args": ["-I", str(relay)],
                "env": {"CONDUCTOR_RELAY_URL": url, "CONDUCTOR_RELAY_TOKEN": run.token}}}}), ".json")):
            f = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="aurora-act-", suffix=suffix, delete=False)
            with f:
                f.write(content)
            os.chmod(f.name, 0o600)
            files.append(f.name)
        with _cloud_call(cc.name, len(ms) + len(mu)) as cl:
            for attempt in (0, 1):
                if fresh:
                    sid = str(uuid.uuid4())
                run.proc = subprocess.Popen(_command(run, cc, files[0], files[1], sid, not fresh), cwd=folder,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True, env=cc._env(8000))
                run.proc.stdin.write(mu)
                run.proc.stdin.close()
                tail = []
                for line in run.proc.stdout:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("type") == "assistant":
                        for c in (e.get("message") or {}).get("content") or []:
                            if c.get("type") == "text" and c.get("text", "").strip():
                                tail.append(c["text"])
                                _note(cfg, project, step="✻ " + p.unmask(c["text"]).strip().splitlines()[0])
                    elif e.get("type") == "result":
                        result = e
                    if time.time() - t0 > int(cfg["AURORA_CONDUCTOR_TIMEOUT_S"]):
                        run.proc.terminate()
                        break
                err = run.proc.stderr.read()
                run.proc.wait(30)
                lost = "No conversation found" in err or bool(result and result.get("is_error")
                                                              and result.get("subtype") == "error_during_execution")
                if attempt or fresh or not lost:
                    break
                # the CLI lost the session — or, after the services moved to their own account (U6, 28 Oct), the
                # session belongs to the login of before and resuming it fails «error_during_execution»: a new one
                fresh, result = True, None
            cl.got = len(str((result or {}).get("result", "")))
        if run.stopped:
            raise RuntimeError("stopped by the owner")
        if not result:
            raise RuntimeError(f"claude -p ended with no answer: {err[-300:] or 'timeout'}")
        if result.get("is_error"):
            raise RuntimeError(f"claude -p: {result.get('result') or result.get('subtype')}")
        cc._account(result, time.time() - t0)
        cost = result.get("total_cost_usd")
        prj_talk._keep_session(cfg, project, {"session": result.get("session_id") or sid, "backend": "cli",
                                              "mask": p.to_val, "since": s.get("since") or time.time()})
        u = result.get("usage") or {}
        prj_talk._add(cfg, project, "conductor", p.unmask(str(result.get("result", "")).strip()) or "…", backend="cli",
                      acted=True, cost_usd=cost, seconds=round(time.time() - t0, 1), new_session=fresh,
                      tokens=(u.get("input_tokens") or 0) + (u.get("output_tokens") or 0) or None,
                      steps=len((working(cfg, project) or {}).get("steps", [])))
    except Exception as e:                                # never left «working»: the failure said in the talk
        prj_talk._add(cfg, project, "conductor", f"⚠️ {str(e)[:400]}", backend="cli", error=True)
    finally:
        for f in files:
            Path(f).unlink(missing_ok=True)
        with _lock:
            _RUNS.pop(run.token, None)
        _note(cfg, project, working=False, ended=time.time())

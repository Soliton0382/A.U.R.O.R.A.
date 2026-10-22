# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💬 Talking with a project's conductor (ROADMAP N39, step 2; owner, 21 Oct: «avere proprio integrazione claude code
come se fosse il terminale che stiamo usando adesso con il --resume così lo storico di interazione rimane, e nel caso
se non si ha claude code, medesimo concetto per modello locale o api»).

A conversation on the project's page, kept per project and per user in the user's state (state/projects/<name>/:
talk.jsonl the turns, talk.json the session), never in the project's history. Who answers:
  local    a project whose policy is «local» (prj_policy), or an agent role assigned to the local model: the local
           model, the stored turns sent again each time
  cli      the agent role on the Claude CLI: one CLI session per project and user (--session-id, then --resume), so
           the CLI keeps the history itself; run from an empty folder of its own, with no tools, no settings, no MCP
           (as mdl_cloud): it talks, it does not act — what must be done becomes a phase (prj_conduct), run by
           Aurora's agent in the project's cage as before
  cloud    the agent role on an API (mdl_router.MaskedLLM): the stored turns sent again, masked
Whatever leaves for the cloud is masked (sec_mask), always: for a CLI session the same Pseudonymizer's map is kept
with the session, so a name is the same placeholder in every turn the CLI keeps, and comes back unmasked. Each turn
says what it cost when the CLI reports it (total_cost_usd); otherwise «non misurato».
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from . import prj_conduct, sys_config
from . import sys_users_layout as L

KEEP_TURNS = 20                 # turns sent again to a model that keeps no session (local, API)
MAX_TOKENS = 1800

TALK = """You are the conductor of the project «{name}» for its owner: a lead engineer they talk with, in their
language ({lang}). Answer from the project's context below and the conversation; explain, check, compare, plan.
You cannot run tools, read other files or change anything: when something must be done, say so and write it as a
phase the owner can start (the page has «🏗️ Fanne una fase» under your answer: write the phase's goal as numbered
points in that answer). Never give a number that is not in the context or the conversation; say when the context
does not have it. The project's policy: {policy}.

{context}"""


def _dir(cfg: sys_config.Config, project: str) -> Path:
    prj_conduct._project(cfg, project)                   # a project's name, and the project exists
    return L.place(cfg, "state", cfg.user) / "projects" / project


def turns(cfg: sys_config.Config, project: str) -> list[dict]:
    try:
        lines = (_dir(cfg, project) / "talk.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _add(cfg: sys_config.Config, project: str, role: str, text: str, **extra) -> dict:
    d = _dir(cfg, project)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    e = {"id": uuid.uuid4().hex[:10], "t": time.time(), "role": role, "text": text, **extra}
    with (d / "talk.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def session(cfg: sys_config.Config, project: str) -> dict:
    try:
        return json.loads((_dir(cfg, project) / "talk.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _keep_session(cfg: sys_config.Config, project: str, s: dict) -> None:
    f = _dir(cfg, project) / "talk.json"
    f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    f.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    os.chmod(f, 0o600)                                   # the mask's map holds the real values


def new(cfg: sys_config.Config, project: str) -> dict:
    """A new conversation: the turns so far kept aside (talk-<time>.jsonl), the session and its mask forgotten."""
    d = _dir(cfg, project)
    t = d / "talk.jsonl"
    if t.is_file():
        t.rename(d / f"talk-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    (d / "talk.json").unlink(missing_ok=True)
    return {"new": True}


def backend(cfg: sys_config.Config, project: str, pipeline) -> tuple[str, object]:
    """(local | cli | cloud, the model): a «local» project never leaves the machine."""
    from . import mdl_router
    if prj_conduct.local(cfg, project):
        return "local", pipeline.llm
    agent = pipeline._for("agent")
    masked = getattr(agent, "primary", agent)            # model_for: Fallback(MaskedLLM(provider), local)
    if mdl_router.is_local(agent, pipeline.llm) or not isinstance(masked, mdl_router.MaskedLLM):
        return "local", agent                            # the agent role is on the local model
    from . import mdl_budget
    if mdl_budget.over(cfg, getattr(agent, "provider", "")):            # today's ceiling reached: the local model
        return "local", pipeline.llm
    if getattr(masked.inner, "name", "") == "claude_code":
        return "cli", masked
    return "cloud", agent                                # an API: masked, the local model if it fails


def _system(cfg: sys_config.Config, project: str, lang: str) -> str:
    from . import prj_policy
    pol = prj_policy.load(cfg, project)
    policy = ("local model only" if pol["models"] == "local" else "masked cloud allowed") + \
        ("" if pol["publish"] else ", never published nor pushed")
    return TALK.format(name=project, lang=lang, policy=policy, context=prj_conduct.context(cfg, project))


def _cli_turn(cfg: sys_config.Config, project: str, masked, system: str, text: str, s: dict) -> dict:
    """One turn on the Claude CLI session of this project and user, masked with the session's own map."""
    from .mdl_router import _cloud_call
    from .sec_mask import KEEP, Pseudonymizer
    cc = masked.inner
    p = Pseudonymizer(cfg)
    p.to_val.update(s.get("mask", {}))
    p.to_ph.update({v: k for k, v in p.to_val.items()})
    ms, mu = p.mask(sys_config.personal(system, cfg)), p.mask(text)
    if p.to_val:
        ms += KEEP
    sid = s.get("session") or ""
    folder = cfg.path("AURORA_STATUS_DIR") / "claude_code" / "talk" / str(cfg.user or "_") / project
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)          # empty: no project instructions, the session's home

    def run(resume: bool):
        f = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="aurora-talk-", suffix=".txt", delete=False)
        try:
            with f:
                f.write(ms)
            # as mdl_cloud: no tools, no settings, no MCP; the session kept (no --no-session-persistence)
            cmd = [cc.bin, "-p", "--model", cc.model, "--tools", "", "--setting-sources", "", "--strict-mcp-config",
                   "--system-prompt-file", f.name, "--output-format", "json"]
            cmd += ["--resume", sid] if resume else ["--session-id", sid]
            return subprocess.run(cmd, input=mu, capture_output=True, text=True, cwd=folder,
                                  timeout=cfg["AURORA_LLM_TIMEOUT_S"], env=cc._env(MAX_TOKENS))
        finally:
            os.unlink(f.name)

    t0 = time.time()
    with _cloud_call(cc.name, len(ms) + len(mu)) as call:
        fresh = not sid
        if fresh:
            sid = str(uuid.uuid4())
        r = run(not fresh)
        if not fresh and "No conversation found" in (r.stderr + r.stdout):   # the CLI lost it: a new session
            sid, fresh = str(uuid.uuid4()), True
            r = run(False)
        try:
            d = json.loads(r.stdout)
        except ValueError:
            raise RuntimeError(f"claude -p: {(r.stderr or r.stdout)[-400:]}") from None
        if d.get("is_error"):
            raise RuntimeError(f"claude -p: {d.get('result') or d.get('api_error_status')}")
        call.got = len(str(d.get("result", "")))
    cc._account(d, time.time() - t0)
    _keep_session(cfg, project, {"session": d.get("session_id") or sid, "backend": "cli", "mask": p.to_val,
                                 "since": s.get("since") or time.time()})
    u = d.get("usage") or {}
    return {"text": p.unmask(str(d.get("result", "")).strip()), "cost_usd": d.get("total_cost_usd"),
            "tokens": (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0) or None,
            "seconds": round(time.time() - t0, 1), "new_session": fresh}


def say(cfg: sys_config.Config, project: str, text: str, pipeline, lang: str = "it") -> dict:
    """The owner's words → the conductor's answer, both kept; a failure kept as the answer, said as such."""
    kind, llm = backend(cfg, project, pipeline)
    before = turns(cfg, project)
    _add(cfg, project, "owner", text)
    system = _system(cfg, project, lang)
    try:
        if kind == "cli":
            out = _cli_turn(cfg, project, llm, system, text, session(cfg, project))
        else:
            msgs = [{"role": "system", "content": system}]
            msgs += [{"role": "user" if e["role"] == "owner" else "assistant", "content": e["text"]}
                     for e in before[-KEEP_TURNS:] if not e.get("error")]
            msgs.append({"role": "user", "content": text})
            t0 = time.time()
            c = llm.complete_turns(msgs, MAX_TOKENS)
            out = {"text": c.answer.strip(), "cost_usd": None, "tokens": c.tokens or None,
                   "seconds": round(time.time() - t0, 1)}
    except Exception as e:                               # the cloud out of its session, the CLI missing: said plainly
        return _add(cfg, project, "conductor", f"⚠️ {str(e)[:400]}", backend=kind, error=True)
    return _add(cfg, project, "conductor", out.pop("text") or "…", backend=kind, **out)

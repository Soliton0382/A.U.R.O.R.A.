# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Back to the factory (owner, 2026-10-06: "a reset to factory defaults, inside the settings").

settings(): every setting back to its recommended value, except what makes this installation itself (folders, ports,
domain, certificates, services, users) and — when asked — the keys, tokens and passwords; the .env before is kept in
<STATUS>/env-backups/. It runs from the Settings page.

mind(): Aurora as just installed — her memory (the conversations, reflections, what she studied), her state (routines,
approvals, incidents, shadows, synapses, autonomy ledger, forge) — moved aside into <root>-before-reset-<time>, never
deleted. Never touched: usr/ (the owners' documents, papers, projects, health), the users and their keys, the
knowledge vault (only with with_knowledge). It stops Aurora, so it runs from a terminal (script/sys_factory_reset.py).
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from . import sys_config

# only what decides how Aurora behaves goes back to the factory: never what makes this installation itself — folders,
# ports, domain, certificates, services, users, the connections (NAS, firewall, programs) and the hardware tuning
# (C158: the first version reset AURORA_BACKUP_DIR, AURORA_FIREWALL_API_URL, AURORA_LLM_CTX and 12 more)
BEHAVIOUR = {"search", "pipeline", "memory", "autonomy", "rem", "acquire", "agents", "interface", "compliance", "logging"}
SECRET = re.compile(r"(KEY|TOKEN|PASSWORD|SECRET)", re.I)
PLACE = re.compile(r"(URL|USER|_DIR$|_BIN$|BIND|ALLOW|HOST|PORT|PATH|_CTX$|PARALLEL|GPU|SPLIT|DOMAIN|_DOC$)", re.I)
# Aurora's mind in the status folder (relative names); everything else there stays (users, devices, keys, backup...)
MIND_STATUS = ("routines.json", "approvals.json", "incidents.json", "synapses.db", "autonomy_ledger.jsonl", "forge",
               "security", "soak.jsonl", "plugins_ready.json", "react.json", "study.json", "shadow.db", "plugin_shadow",
               "tts")                           # kept: push (the devices' subscriptions), ideas.json (the owner's words)
KNOWLEDGE_STATUS = ("harvest",)                 # the harvester's progress goes only with the knowledge


def settings(cfg: sys_config.Config, keep_keys: bool = True) -> dict:
    env = getattr(cfg, "env_file", None) or sys_config.env_file_path()   # the config's own .env (C158: tests wrote the real one)
    backup = cfg.path("AURORA_STATUS_DIR") / "env-backups" / f".env.{time.strftime('%Y%m%d-%H%M%S')}"
    backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copy2(env, backup)
    backup.chmod(0o600)
    current = sys_config.parse_env(env.read_text(encoding="utf-8"))
    changes, services = {}, set()
    for s in sys_config.load_schema()["settings"]:
        k = s["key"]
        if s.get("category") not in BEHAVIOUR or s.get("scope") == "user" or PLACE.search(k):
            continue
        if keep_keys and (s.get("secret") or SECRET.search(k)):
            continue
        rec = str(s.get("recommended", ""))
        if str(current.get(k, "")) != rec:
            changes[k] = rec
            services.update(s.get("services") or [])
    if changes:
        sys_config.write_env(env, changes)
    return {"changed": sorted(changes), "restart": sorted(services), "backup": str(backup)}


def mind_plan(cfg: sys_config.Config, with_knowledge: bool = False) -> dict:
    """What mind() would move aside (paths that exist), and where."""
    root = cfg.root.resolve()
    status = cfg.path("AURORA_STATUS_DIR")
    vault = cfg.path("AURORA_VAULT_DIR")
    users = [d for d in (status / "users").iterdir() if d.is_dir()] if (status / "users").is_dir() else []
    places = [base / n for base in [status, *users] for n in MIND_STATUS]          # the machine's and each user's state
    places += [vault / "memory", vault / "index" / "memory"]
    if with_knowledge:
        places += [vault / "knowledge", vault / "index" / "knowledge"] + [status / n for n in KNOWLEDGE_STATUS]
    places = [p for p in places if p.exists()]
    usr = (root / "usr").resolve()
    assert not any(usr == p.resolve() or usr in p.resolve().parents for p in places), "never usr/"
    return {"places": [str(p.resolve().relative_to(root)) for p in places],
            "aside": str(root.parent / f"{root.name}-before-reset-{time.strftime('%Y%m%d-%H%M%S')}")}


def mind(cfg: sys_config.Config, plan: dict) -> None:
    root, aside = cfg.root.resolve(), Path(plan["aside"])
    for rel in plan["places"]:
        (aside / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root / rel), str(aside / rel))

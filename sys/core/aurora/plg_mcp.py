# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""MCP servers of the owner's, used by Aurora like her plugins (owner, 10 Nov: «aggiungerei ad aurora la possibilità di
integrare server mcp che può usare magari nella chat sua… una sezione dedita»).

A server is a plugin made of a manifest only, in AURORA_PLUGINS_DIR/local_<name>/plugin.json, kind «mcp» — «local_»
because it is the owner's own (its paths, its address): git ignores those folders, so publishing never carries it
(C546, found 10 Nov: under its bare name the first server would have gone public with the home's paths):
 - local: a program started on stdio, in the plugins' cage (plg_sandbox): no network unless asked, and it reads only
   the few places it names («read»: its program, its code, a socket — never the home, a hidden place, Aurora's state);
 - remote: an http or https address (owner, 10 Nov: «http e https… non limitiamoci»; http is said to travel in
   clear on the page), reached only there (plg_host._remote_session).
Like every plugin of the owner's it is loaded only once signed (sudo aurora-root sign): nothing runs as Aurora without
his yes. Its tools wait for his approval (effect «external») unless he marks them as reads; «memory»: false keeps any
answer that used it out of Aurora's memory (a document archive the owner keeps apart never becomes hers: owner, 9 Nov)."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from . import plg_sandbox, sys_config

NAME = re.compile(r"^[a-z][a-z0-9_]{1,29}$")              # the plugins' contract: the folder's name
EFFECTS = ("read", "write_local", "external")
LOCAL = "local_"                                           # the owner's own plugins: never published (.gitignore)


def folder(cfg: sys_config.Config, name: str) -> Path:
    return cfg.path("AURORA_PLUGINS_DIR") / name


def manifest(cfg: sys_config.Config, body: dict) -> dict:
    """The manifest of a server from the owner's form; ValueError says what is wrong."""
    name = str(body.get("name", "")).strip().lower()
    name = name if name.startswith(LOCAL) else LOCAL + name
    if not NAME.match(name):
        raise ValueError(f"name: lowercase letters, digits and _, 2–{30 - len(LOCAL)}, starting with a letter")
    desc = str(body.get("description", "")).strip()
    if not 10 <= len(desc) <= 400:
        raise ValueError("description: 10–400 characters — the chat reads it to know when the server helps")
    m: dict = {"name": name, "version": "1.0", "kind": "mcp", "description": {"en": desc, "it": desc}, "requires": [],
               "memory": bool(body.get("memory", True)), "chat": bool(body.get("chat", True))}
    url, command = str(body.get("url", "") or "").strip(), body.get("command") or []
    if bool(url) == bool(command):
        raise ValueError("either a command (a local server) or an address (a remote one), not both")
    if url:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:      # both (owner, 10 Nov); http said «in chiaro»
            raise ValueError("address: http://host/… or https://host/…")
        m["url"] = url
    else:
        if not isinstance(command, list) or not command or not all(isinstance(a, str) and a for a in command):
            raise ValueError("command: the program and its arguments, as a list")
        prog = Path(command[0])
        if not prog.is_absolute() or not prog.exists():
            raise ValueError(f"command: {command[0]} — an absolute path to a program that exists")
        m["command"] = [str(a) for a in command]
        read = [str(x) for x in body.get("read", []) if str(x).strip()]
        net = body.get("network", False)
        if net not in (False, "proxy"):
            raise ValueError("network: none, or through Aurora's proxy to the hosts named")
        m["sandbox"] = {"read": read, "network": net}
        if net == "proxy":
            hosts = [str(h).strip().lower() for h in body.get("hosts", []) if str(h).strip()]
            if not hosts:
                raise ValueError("network through the proxy: name its hosts")
            m["hosts"] = hosts
        plg_sandbox.read_paths(m, cfg)                       # the cage's own check, said now rather than at a call
    # what a server that reaches the network answers is from outside: through the honeypot like a web page (audit,
    # 10 Nov: «checked as every tool result» was not true for them)
    if m.get("url") or m.get("sandbox", {}).get("network") == "proxy" or body.get("untrusted"):
        m["from_network"] = ["*"]                          # every tool of it
    reads = [str(t) for t in body.get("read_tools", [])]
    default = str(body.get("effect", "external"))
    if default not in EFFECTS:
        raise ValueError(f"effect: one of {', '.join(EFFECTS)}")
    m["effects"] = {**{t: "read" for t in reads}, "*": default}
    return m


def save(cfg: sys_config.Config, m: dict) -> Path:
    """Written whole; never over a plugin that is not an MCP server of this section (ValueError)."""
    from . import plg_contract
    if errs := plg_contract.check(m, m["name"]):
        raise ValueError("; ".join(errs))
    d = folder(cfg, m["name"])
    mf = d / "plugin.json"
    if d.exists() and (not mf.is_file() or json.loads(mf.read_text(encoding="utf-8")).get("kind") != "mcp"):
        raise ValueError(f"{m['name']}: another plugin has that name")
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "plugin.json.tmp"
    tmp.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(d / "plugin.json")
    return d


def remove(cfg: sys_config.Config, name: str) -> bool:
    d = folder(cfg, name)
    mf = d / "plugin.json"
    if not NAME.match(name) or not name.startswith(LOCAL) or not mf.is_file():
        return False
    if json.loads(mf.read_text(encoding="utf-8")).get("kind") != "mcp":     # only what this section made
        return False
    shutil.rmtree(d)
    return True


def listed(host) -> list[dict]:
    """The MCP servers with their state: tools, signed or not, the error if any."""
    out = []
    for p in host.plugins():
        if p.manifest.get("kind") != "mcp":
            continue
        m = p.manifest
        out.append({"name": p.name, "description": (m.get("description") or {}).get("en", ""),
                    "where": m.get("url") or " ".join(m.get("command", [])), "remote": bool(m.get("url")),
                    "clear": str(m.get("url", "")).startswith("http://"),
                    "memory": m.get("memory", True), "chat": m.get("chat", True), "enabled": p.enabled,
                    "available": p.available, "error": p.error, "unsigned": "not signed" in p.error,
                    "tools": [{"name": t["name"], "effect": p.effect(t["name"])} for t in p.tools]})
    return out


def unremembered(host) -> set[str]:
    """The servers whose answers never enter Aurora's memory."""
    return {p.name for p in host.plugins(with_tools=False) if p.manifest.get("kind") == "mcp" and p.manifest.get("memory") is False}

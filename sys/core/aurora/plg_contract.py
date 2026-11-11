# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The plugin contract: how a plugin's plugin.json is made, one definition for the hand-made, the forged and the
private ones (owner, 16 Oct: «plugin, agenti etc. hanno tutti un contratto di funzionamento di come devono essere
costruiti? se no creiamo casini»). check() lists what breaks it; the tests run it on every plugin; the forge on every
plugin it builds; doc_plugins writes FIELDS into docs/PLUGINS.md.

A plugin is a folder of sys/plugins with plugin.json and its program (an MCP server over stdio, or a remote one through
the gateway). Its tools are found by asking the program; each tool has one effect: read (automatic), write_local
(automatic, logged), external (waits for the owner, unless the autonomy allows it). What a tool may touch is said by the
manifest, never assumed: the network (sandbox.network), the folders it writes (sandbox.write, setting names), the
settings it receives (env, requires, settings), what it publishes (publishes)."""
from __future__ import annotations

import re

KINDS = ("tool", "connector", "service", "mcp")       # mcp: a server of the owner's, manifest only (plg_mcp)
EFFECTS = ("read", "write_local", "external")
NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
SETTING = re.compile(r"^AURORA_[A-Z0-9_]+$")
# C591: the environment name «env_as» gives a setting's value to. Capitals, digits and _ only, and never a name the
# system, the loader, Python or Aurora read themselves: with PATH or LD_PRELOAD the host ran a planted program, outside
# the cage, when it started the cage.
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
ENV_RESERVED = {"PATH", "HOME", "IFS", "ENV", "BASH_ENV", "SHELL", "USER", "LOGNAME", "TMPDIR", "TERM", "LANG", "PWD",
                "HOSTALIASES", "LOCPATH", "NLSPATH", "RESOLV_HOST_CONF", "TZDIR", "MALLOC_TRACE"}
ENV_RESERVED_PREFIX = ("LD_", "DYLD_", "PYTHON", "AURORA_", "GLIBC_", "GCONV_", "BASH_FUNC_", "LC_", "BWRAP_", "GIT_")


def env_name_ok(name) -> bool:
    """True for a name «env_as» may set in a plugin's environment."""
    name = str(name)
    return bool(ENV_NAME.match(name)) and name not in ENV_RESERVED and not name.startswith(ENV_RESERVED_PREFIX)

# field: (type, required, what it is) — the order is the documentation's
FIELDS = {
    "name": (str, True, "the folder's name: lowercase letters, digits, _; the tools are called <name>__<tool>"),
    "version": (str, True, "the plugin's own version"),
    "kind": (str, True, "tool (works on this machine), connector (an account somewhere), service (no tools: a job), "
                        "mcp (an MCP server of the owner's, added from the Plugins page: plg_mcp)"),
    "description": (dict, True, "{it, en}: what it does, shown in the Plugins page and to the agent"),
    "command": (list, True, "how its program starts: [\"{python}\", \"server.py\"], or a program of its own (a remote "
                            "MCP server has an url instead)"),
    "url": (str, False, "a remote MCP server's address, http or https (kind mcp): no command"),
    "lan": (bool, False, "true: the remote MCP server is in the house (a private address); without it only a public "
                         "one is reached (kind mcp)"),
    "memory": (bool, False, "false: an answer that used it never enters Aurora's memory (kind mcp)"),
    "chat": (bool, False, "false: kept out of the chat, only an agent that chose it uses it (kind mcp)"),
    "requires": (list, True, "settings without which it does not start (named, never their values)"),
    "effects": (dict, True, "tool → read | write_local | external; \"*\" for the rest"),
    "env": (list, False, "settings passed to its program"),
    "settings": (list, False, "settings shown in its card"),
    "settings_spec": (list, False, "its own settings: {key AURORA_<NAME>_…, type, secret, scope, it, en}; scope "
                                   "\"user\": a person's account, kept in their own .env"),
    "setup": (dict, False, "{it, en, links}: how to set it up"),
    "sandbox": (dict, False, "{network: true (the host's), false (none: the default), \"local\" (the local model only) or \"proxy\" (its hosts only), write: [setting "
                             "names of folders], read: [absolute paths outside Aurora, kind mcp only]}: the cage"),
    "tests": ((list, dict), False, "read tools called by «Prova»: [{tool, args}] or {tool: args}"),
    "welcome": (dict, False, "{it, en}: said once when it is first switched on"),
    "publishes": (dict, False, "tool → the argument that is published (a post, a comment): checked before it leaves"),
    "page": (str, False, "the page it belongs to (a menu id): configured there, not in the Plugins grid"),
    "on_demand": (dict, False, "{words: [...]}: its tools in the agent's catalog only when the goal names one (agt_tools)"),
    "cache": (dict, False, "tool → seconds an answer is kept"),
    "capabilities": (list, False, "what it lets Aurora do, checked by the ethics code"),
    "from_network": (list, False, "tools whose answers come from the internet (marked as such; «*»: all of them)"),
    "social": (dict, False, "a social platform: its statistics and posts in the 📣 Social page"),
    "routines": (list, False, "routines it proposes"),
    "private": (bool, False, "its data are private: after one of its reads the run uses the local model only"),
    "install": (dict, False, "what it brings: Python libraries pinned by hash, programs by sha256 (plg_deps)"),
    "home_commands": (list, False, "tools that command the house's devices (AURORA_HA_COMMANDS)"),
    "owner_only": (list, False, "tools only the owner's own words may start (never a run's idea)"),
    "oauth": (str, False, "the name of its OAuth flow (api/oauth)"),
    "env_as": (dict, False, "setting → the environment name its program expects"),
    "seal_keys": (list, False, "the sealed stores it keeps (calendar, health): their key given to it opened (N64)"),
    "effect_prefixes": (dict, False, "tool-name prefix → effect, for a program with many tools"),
    "outputs": (dict, False, "tool → {pattern, url, mime}: a file it makes, offered for download"),
    "forged": (dict, False, "made by the forge: {request, at, need}"),
    "hosts": (list, False, "a forged plugin's public places: host names its proxy lets it reach (plg_netproxy)"),
}


def check(m: dict, folder: str = "") -> list[str]:
    """What breaks the contract in a manifest (empty: none)."""
    out = []
    for k, (typ, required, _) in FIELDS.items():
        if k not in m:
            if required and not (k == "command" and m.get("url")):
                out.append(f"{k}: missing")
        elif not isinstance(m[k], typ):
            out.append(f"{k}: {type(m[k]).__name__}, not {getattr(typ, '__name__', typ)}")
    if unknown := sorted(set(m) - set(FIELDS)):
        out.append(f"fields not in the contract: {', '.join(unknown)}")
    name = str(m.get("name", ""))
    if not NAME.match(name):
        out.append(f"name {name!r}: lowercase letters, digits, _")
    elif folder and folder != name:
        out.append(f"name {name!r} is not its folder's {folder!r}")
    if m.get("kind") not in KINDS:
        out.append(f"kind {m.get('kind')!r}: one of {', '.join(KINDS)}")
    d = m.get("description")
    if isinstance(d, dict) and not (d.get("it") and d.get("en")):
        out.append("description: both it and en")
    for k in ("requires", "env", "settings"):
        if bad := [s for s in m.get(k) or [] if not SETTING.match(str(s))]:
            out.append(f"{k}: not settings: {', '.join(map(str, bad))}")
    env_as = m.get("env_as") if isinstance(m.get("env_as"), dict) else {}
    if bad := [s for s in env_as if not SETTING.match(str(s))]:
        out.append(f"env_as: not settings: {', '.join(map(str, bad))}")
    if bad := [v for v in env_as.values() if not env_name_ok(v)]:
        out.append(f"env_as: {', '.join(map(str, bad))}: not a name a plugin's program may be given (capitals, digits, _; "
                   "never PATH, HOME, LD_…, PYTHON…, AURORA_…)")
    effects = m.get("effects") or {}
    if bad := [f"{t}={e}" for t, e in effects.items() if e not in EFFECTS]:
        out.append(f"effects: {', '.join(bad)} (read, write_local, external)")
    for prefix, e in (m.get("effect_prefixes") or {}).items():
        if e not in EFFECTS:
            out.append(f"effect_prefixes: {prefix}={e}")
    sb = m.get("sandbox") or {}
    if bad := sorted(set(sb) - {"network", "write", "read"}):
        out.append(f"sandbox: {', '.join(bad)} not in the contract (network, write, read)")
    if "network" in sb and not (isinstance(sb["network"], bool) or sb["network"] in ("local", "proxy")):
        out.append("sandbox.network: true, false, \"local\" (the local model only) or \"proxy\" (its hosts only)")
    if sb.get("read") and m.get("kind") != "mcp":
        out.append("sandbox.read: only an MCP server of the owner's (kind mcp) reads outside Aurora")
    if bad := [r for r in sb.get("read") or [] if not str(r).startswith("/")]:
        out.append(f"sandbox.read: absolute paths, not {', '.join(map(str, bad))}")
    if m.get("url") and m.get("kind") != "mcp":
        out.append("url: only an MCP server (kind mcp)")
    if m.get("lan") and not m.get("url"):
        out.append("lan: only a remote MCP server (url)")
    if m.get("url") and not str(m["url"]).startswith(("http://", "https://")):
        out.append("url: http:// or https://")
    if bad := [s for s in sb.get("write") or [] if not SETTING.match(str(s))]:
        out.append(f"sandbox.write: folders by their setting's name, not {', '.join(map(str, bad))}")
    if "page" in m and not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", str(m["page"])):
        out.append(f"page {m['page']!r}: a page's id (lowercase)")
    od = m.get("on_demand")
    if isinstance(od, dict) and not (isinstance(od.get("words"), list) and od["words"]):
        out.append("on_demand: {words: [one or more]}")
    prefix = f"AURORA_{name.upper()}_"
    for s in m.get("settings_spec") or []:
        key = str((s or {}).get("key", ""))
        if not key.startswith(prefix):
            out.append(f"settings_spec {key}: its own settings start with {prefix}")
        if (s or {}).get("scope", "machine") not in ("machine", "user"):
            out.append(f"settings_spec {key}: scope machine or user")
    return out

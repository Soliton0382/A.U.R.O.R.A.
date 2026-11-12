# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin host: Aurora is the only MCP client; plugins are child processes on stdio, never on a port.

A plugin is a folder in AURORA_PLUGINS_DIR with a manifest, plugin.json:

  {"name": "telegram", "version": "1.0", "kind": "connector",
   "description": {"en": "...", "it": "..."},
   "command": ["{python}", "server.py"],          # {python}: Aurora's venv, {plugin}: this folder, {root}
   "env": ["AURORA_TELEGRAM_BOT_TOKEN"],           # the only .env values the process receives
   "requires": ["AURORA_TELEGRAM_BOT_TOKEN"],      # available only when these are not empty
   "effects": {"send_message": "external", "*": "read"},
   "effect_prefixes": {"get_": "read"},            # optional: by tool-name prefix (large connectors)
   "sandbox": {"write": ["AURORA_PROJECTS_DIR"]}}  # optional: the only folders it may write (plg_sandbox)

Effects decide the gate (sys_approvals): read and write_local run at once, external and
code_change wait for the owner as the .env says. The owner can switch a plugin off; the
state lives in <AURORA_STATUS_DIR>/plugins.json. One process per call keeps plugins
isolated and stateless; tool lists are cached until the manifest changes.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import sys_config, sys_log

EFFECTS = ("read", "write_local", "external", "code_change")
# the sealed stores a caged plugin may open with its own key (N64): its manifest asks for them in «seal_keys»
SEAL_KEYS = ("calendar", "health", "diary", "push", "expenses", "routines", "network",
             "firewalls")   # the security plugin's network map and the other firewalls' passwords (C480)
_lock = threading.Lock()


def _explain(e: BaseException) -> str:
    """The real error inside the task groups of the MCP client."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return f"{type(e).__name__}: {e}"


# what a plugin writes on its stderr reaches its log with its tokens cut (C429, 28 Oct: 234 Graph «access_token=» in a
# readable log — httpx's INFO lines carry the URL): a pipe, a thread that redacts each line, the file 0600
_SECRET_IN_LOG = __import__("re").compile(
    r"(?i)((?:access_token|refresh_token|token|api_key|apikey|key|secret|password|passwd|signature|sig)=)[^&\s\"']+"
    r"|(authorization:\s*(?:bearer|basic)\s+)\S+|\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{40,}\b")


def _redact(line: str) -> str:
    return _SECRET_IN_LOG.sub(lambda m: (m.group(1) or m.group(2) or "") + "<redacted>", line)


def _redacted_log(path: Path):
    """A file-like object for the plugin's stderr (a real descriptor: the process writes to it)."""
    import threading
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:                                             # 0600, or 0660 when the file is the services' group's (U6)
        shared = sys_config._group_name(os.fstat(fd).st_gid) == sys_config.SERVICE_GROUP
        os.fchmod(fd, 0o660 if shared else 0o600)
    except OSError:                                  # not ours to change (another account wrote it first): as it is
        pass
    r, w = os.pipe()

    def pump():
        with os.fdopen(r, "r", encoding="utf-8", errors="replace") as src, os.fdopen(fd, "a", encoding="utf-8") as out:
            for line in src:
                out.write(_redact(line))
                out.flush()
    threading.Thread(target=pump, name=f"stderr-{path.stem}", daemon=True).start()
    return os.fdopen(w, "w", encoding="utf-8")


@dataclass
class Plugin:
    name: str
    folder: Path
    manifest: dict
    missing: list[str] = field(default_factory=list)       # required .env keys that are empty
    enabled: bool = True
    tools: list[dict] = field(default_factory=list)          # {"name", "description", "input_schema", "effect"}
    error: str = ""
    away: dict = field(default_factory=dict)                 # its scheduled pause (plg_away), off by default

    @property
    def paused(self) -> bool:
        from . import plg_away
        return plg_away.paused(self.away)

    @property
    def available(self) -> bool:
        return self.enabled and not self.missing and not self.error and not self.paused

    def effect(self, tool: str) -> str:
        m = self.manifest
        if tool in m.get("effects", {}):
            return m["effects"][tool]
        for prefix, eff in m.get("effect_prefixes", {}).items():
            if tool.startswith(prefix):
                return eff
        return m.get("effects", {}).get("*", "external")      # unknown: the careful default


# a plugin that could not list its tools, remembered (C229: on Windows, where the plugins' cage is not finished, all
# 36 were started again before every question — about a minute each time on 2 cores); a changed manifest, or
# FAILED_S later, and it is tried again
FAILED_S = 600
_FAILED: dict[tuple[str, float], tuple[float, str]] = {}
# a plugin that is not loaded is said once per process, and again only after it loaded in between (12 Nov: with the
# code unsigned for six minutes, «not loaded, not signed and not forged» was written 5,788 times — every listing, for
# each plugin)
_REFUSED: set[tuple[str, str]] = set()


class PluginHost:
    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.dir = self.cfg.path("AURORA_PLUGINS_DIR")
        self.state_file = self.cfg.path("AURORA_STATUS_DIR") / "plugins.json"
        self.log = sys_log.get_logger("plugins")
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    # ---- discovery and state ---------------------------------------------------------------
    def _state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8")) if self.state_file.exists() else {}

    def set_enabled(self, name: str, enabled: bool) -> None:
        with _lock:
            st = self._state()
            st.setdefault(name, {})["enabled"] = enabled
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
            os.replace(tmp, self.state_file)
        self.log.info("audit: plugin %s %s", name, "enabled" if enabled else "disabled")

    def set_away(self, name: str, window: dict) -> dict:
        """Its scheduled pause (plg_away.clean: ValueError when the times are not valid), stored with its state."""
        from . import plg_away
        w = plg_away.clean(window)
        with _lock:
            st = self._state()
            st.setdefault(name, {})["away"] = w
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
            os.replace(tmp, self.state_file)
        self.log.info("audit: plugin %s: scheduled pause %s", name, f"{w['from']}-{w['to']}" if w["on"] else "off")
        return w

    def plugins(self, with_tools: bool = True) -> list[Plugin]:
        out, st = [], self._state()
        if not self.dir.is_dir():
            return out
        from . import sys_ethics
        signed = self.cfg.root / "sys" / "plugins"
        outside = (self.cfg.root / sys_ethics.MANIFEST).is_file() and self.dir.resolve() != signed.resolve()
        # 13 Nov: asked once a plugin, the signature's stamp looked at every plugin's file each time — 9,792 stats a
        # scan, 0.08 s alone and 20 s inside the API beside its other threads (C600): once a scan now
        unsigned = sys_ethics.unsigned_plugins(self.cfg.root)
        for mf in sorted(self.dir.glob("*/plugin.json")):
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except ValueError as e:
                out.append(Plugin(mf.parent.name, mf.parent, {}, error=f"bad manifest: {e}"))
                continue
            p = Plugin(manifest.get("name", mf.parent.name), mf.parent, manifest,
                       missing=[k for k in manifest.get("requires", []) if not str(self.cfg.values.get(k, "") or "").strip()],
                       enabled=st.get(manifest.get("name", mf.parent.name), {}).get("enabled", True),
                       away=st.get(manifest.get("name", mf.parent.name), {}).get("away", {}))
            from . import sys_ethics
            if (bad := sys_ethics.forbidden_capabilities(manifest)):      # ethics code, level A: never loaded
                p.error = f"refused by the ethics code (level A): {', '.join(bad)}"
                self._refused(p.name, "ethics", "plugin %s refused by the ethics code: %s", p.name, ", ".join(bad))
                out.append(p)
                continue
            if outside:                                        # a plugins' folder the signature does not cover (audit,
                p.error = ("not in sys/plugins, the folder the owner's signature covers: "   # 10 Nov: a setting moved it)
                           "set AURORA_PLUGINS_DIR back to sys/plugins")
                self._refused(p.name, "outside", "plugin %s: not loaded, outside the signed plugins' folder", p.name)
                out.append(p)
                continue
            if mf.parent.name in unsigned:                     # neither Aurora's (forged) nor signed
                p.error = "not signed by the owner and not one of Aurora's own plugins: sudo aurora-root sign"
                self._refused(p.name, "unsigned", "plugin %s: not loaded, not signed and not forged", p.name)
                out.append(p)
                continue
            _REFUSED.difference_update({(p.name, why) for why in ("ethics", "outside", "unsigned")})   # loaded again
            if with_tools and p.enabled and not p.missing:
                try:
                    p.tools = self._tools(p, mf.stat().st_mtime)
                except Exception as e:                       # a broken plugin must not break the others
                    p.error = _explain(e)
                    self.log.warning("plugin %s: cannot list tools: %s", p.name, p.error)
            out.append(p)
        return out

    def _refused(self, name: str, why: str, msg: str, *args) -> None:
        if (name, why) not in _REFUSED:
            _REFUSED.add((name, why))
            self.log.warning(msg, *args)

    def get(self, name: str) -> Plugin | None:
        return next((p for p in self.plugins() if p.name == name), None)

    # ---- MCP over stdio ------------------------------------------------------------------
    def _params(self, p: Plugin):
        from mcp import StdioServerParameters
        subst = {"{python}": sys.executable, "{plugin}": str(p.folder), "{root}": str(self.cfg.root)}
        cmd = []
        for a in p.manifest["command"]:
            for k, v in subst.items():
                a = a.replace(k, v)
            cmd.append(a)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", ""),
               "AURORA_ENV_FILE": str(self.cfg.env_file), "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
               "AURORA_PLUGIN": p.name}                 # its config is its user's filtered one, taken as it is (U3)
        from . import plg_sandbox
        # a plugin Aurora wrote herself (9 Nov): its own settings only (AURORA_<NAME>_…), never another's value
        if plg_sandbox.forged(p.manifest):           # nor a key of Aurora's core or another plugin (audit 9 Nov)
            theirs = sys_config.others_keys(p.name)
            mine = lambda k: k.startswith(f"AURORA_{p.name.upper()}_") and k not in theirs   # noqa: E731
        else:
            mine = lambda k: True                        # noqa: E731
        fixed = dict(env)
        from . import plg_contract
        for k in p.manifest.get("env", []):
            if mine(k) and plg_contract.SETTING.match(str(k)):
                env[k] = str(self.cfg.values.get(k, "") or "")
        for k, v in (p.manifest.get("env_as") or {}).items():     # .env key -> name the program expects
            # C591: never a name the system, the loader or Aurora read (PATH, LD_PRELOAD: the host itself ran a planted
            # «bwrap» with them, outside the cage) — refused here at every start, whoever wrote the manifest
            if not plg_contract.env_name_ok(v):
                raise RuntimeError(f"env_as: {v!r} is not a name a plugin's program may be given: the plugin is not run")
            if mine(k):
                env[v] = str(self.cfg.values.get(k, "") or "")
        env.update(fixed)                                # what Aurora sets herself is never a manifest's to change
        # N64: the cage holds neither Aurora's key nor the user's key files; a plugin keeping sealed data of its own
        # gets that one key, opened — only the purposes below, never the memory's or the state's
        from . import sys_seal
        for purpose in [] if plg_sandbox.forged(p.manifest) else p.manifest.get("seal_keys", []):   # never a forged one's
            if purpose in SEAL_KEYS:
                env[f"AURORA_SEAL_KEY_{purpose.upper()}"] = sys_seal._key(self.cfg, self.cfg.user, purpose).hex()
        filtered = plg_sandbox.env_file(p.name, p.manifest, self.cfg)    # only this plugin's own secrets, by name
        specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
        for k in plg_sandbox._declared(p.manifest):      # their values in its environment, never on the disk (C463)
            if specs.get(k, {}).get("secret"):
                env[sys_config.PLUGIN_SECRET + k] = str(self.cfg.raw.get(k, "") or "")
        if self.cfg["AURORA_PLUGIN_SANDBOX"]:
            if not plg_sandbox.available():
                # never uncaged because the cage is missing (C226: a container without bubblewrap ran them bare, as
                # the ports already refuse): the owner may switch the cage off on purpose, never by accident
                raise RuntimeError("no cage here (bubblewrap is missing): the plugin is not run")
            from . import plg_deps                         # C579: what it fetched, as fetched
            plg_deps.verify(self.cfg, p.folder, p.manifest, log=lambda m: sys_log.get_logger("plugins").warning(m))
            cmd = plg_sandbox.wrap(cmd, p.folder, p.manifest, filtered, self.cfg)   # inside, .env is the filtered one
        else:
            env["AURORA_ENV_FILE"] = str(filtered)
        return StdioServerParameters(command=cmd[0], args=cmd[1:], env=env, cwd=str(p.folder))

    async def _session(self, p: Plugin, work):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        if p.manifest.get("url"):                         # a remote MCP server (owner, 10 Nov): its address only —
            if p.manifest.get("kind") != "mcp" or p.manifest.get("forged"):    # the owner's own, never a forged one
                raise RuntimeError("an address is only for the owner's MCP servers (kind mcp), never a forged plugin")
            return await self._remote_session(p, work)
        errlog = _redacted_log(self.cfg.path("AURORA_LOG_DIR") / "plugins" / f"{p.name}.stderr.log")
        from . import plg_sandbox
        marks = plg_sandbox.repo_marks(self.cfg) if plg_sandbox.forged(p.manifest) else None
        try:
            async with stdio_client(self._params(p), errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await work(session)
        finally:
            errlog.close()
            if marks is not None:                        # C591: a repository or an environment it left behind
                plg_sandbox.set_aside_new(self.cfg, marks, self.log.warning)

    async def _remote_session(self, p: Plugin, work):
        """An MCP server at an address (streamable HTTP, http or https: owner, 10 Nov), reached there only — what it
        answers is data from outside, through the honeypot (plg_mcp marks it from_network, C553)."""
        from urllib.parse import urlparse
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        url = str(p.manifest["url"])
        if urlparse(url).scheme not in ("http", "https"):
            raise RuntimeError("a remote MCP server is reached over http or https only")
        from . import plg_mcp                             # C571: where the name leads now, not when it was added
        if why := await asyncio.to_thread(plg_mcp.address_problem, url, p.manifest.get("lan") is True, self.cfg):
            raise RuntimeError(f"the MCP server's address is not reached: {why}")
        async with streamable_http_client(url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                return await work(session)

    def _gateway(self) -> str:
        """Aurora in Docker: the plugins run in a container of their own, in their cage (docker/plugins_gateway.py),
        asked over the internal network (owner, 9 Oct: «per i plugin si crea un docker apposito che farà parte della
        stessa rete del docker aurora»). The checks stay here: the secrets in the arguments, the approvals."""
        return os.environ.get("AURORA_PLUGIN_GATEWAY", "").rstrip("/")

    def _remote(self, path: str, body: dict) -> dict:
        import httpx
        r = httpx.post(self._gateway() + path, json=body, headers={"Authorization": f"Bearer {self.cfg['AURORA_API_KEY']}"},
                       timeout=float(self.cfg["AURORA_PLUGIN_TIMEOUT_S"]) + 15)
        r.raise_for_status()
        return r.json()

    def _run(self, coro):
        """The plugin's call to its end. From inside a running event loop (an async endpoint asked for a plugin before
        the background listing was over) asyncio.run cannot run: there, in a thread of its own (C372: every plugin
        said «cannot list tools», Home Assistant «not on», until the next listing)."""
        work = asyncio.wait_for(coro, self.cfg["AURORA_PLUGIN_TIMEOUT_S"])
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(work)
        out: dict = {}

        def alone():
            try:
                out["value"] = asyncio.run(work)
            except BaseException as e:                   # noqa: BLE001 — given back to the caller, as asyncio.run would
                out["error"] = e
        t = threading.Thread(target=alone, name="plugin-call", daemon=True)
        t.start()
        t.join()
        if "error" in out:
            raise out["error"]
        return out.get("value")

    def _tools(self, p: Plugin, mtime: float) -> list[dict]:
        cached = self._cache.get(p.name)
        if cached and cached[0] == mtime:
            return cached[1]
        failed = _FAILED.get((p.name, mtime))
        if failed and time.time() < failed[0]:            # it could not start a moment ago: not tried at every question
            raise RuntimeError(failed[1])
        if self._gateway():
            tools = self._remote("/tools", {"plugin": p.name, "user": self.cfg.user})["tools"]
            self._cache[p.name] = (mtime, tools)
            return tools

        async def work(session):
            res = await session.list_tools()
            return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema or {},
                     "effect": p.effect(t.name)} for t in res.tools]
        (self.cfg.path("AURORA_LOG_DIR") / "plugins").mkdir(parents=True, exist_ok=True)
        try:
            tools = self._run(self._session(p, work))
        except Exception as e:
            _FAILED[(p.name, mtime)] = (time.time() + FAILED_S, _explain(e))
            raise
        self._cache[p.name] = (mtime, tools)
        return tools

    def _secrets_in(self, args: dict, p: Plugin) -> list[str]:
        """Names of the .env secrets whose value appears in the arguments (except the plugin's own, which it
        receives anyway). A prompt-injected agent cannot send a key or a token out through a tool."""
        mine = set(p.manifest.get("env", [])) | set(p.manifest.get("env_as", {}))
        blob = json.dumps(args or {}, ensure_ascii=False)
        specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
        return sorted(k for k, s in specs.items()
                      if s.get("secret") and k not in mine and len(str(self.cfg.values.get(k) or "")) >= 8
                      and str(self.cfg.values[k]) in blob)

    def call(self, plugin: str, tool: str, args: dict, run_id: str | None = None) -> dict:
        """Run one tool now (the gate is the caller's job). Returns {"ok", "text", "seconds"}."""
        p = self.get(plugin)
        if p is not None and p.paused:
            return {"ok": False, "text": f"plugin {plugin} in its scheduled pause until {p.away.get('to')}", "seconds": 0}
        if p is None or not p.available:
            return {"ok": False, "text": f"plugin {plugin} not available"
                                        + (f" (missing {', '.join(p.missing)})" if p and p.missing else ""), "seconds": 0}
        leaked = self._secrets_in(args, p)
        if leaked:                                    # whatever the model "decided": a secret never leaves in arguments
            self.log.warning("audit: call %s.%s REFUSED: its arguments contain the secret %s", plugin, tool, ", ".join(leaked))
            sys_log.trace("plugins", "plugin.refused", {"plugin": plugin, "tool": tool, "secrets": leaked}, run_id=run_id)
            return {"ok": False, "text": f"refused: the arguments contain a secret of Aurora ({', '.join(leaked)})",
                    "seconds": 0}
        t0 = time.time()

        async def work(session):
            return await session.call_tool(tool, args or {})
        try:
            if self._gateway():
                out = self._remote("/call", {"plugin": plugin, "user": self.cfg.user, "tool": tool, "args": args or {},
                                             "run_id": run_id})
                ok, text = bool(out.get("ok")), str(out.get("text", ""))
            else:
                res = self._run(self._session(p, work))
                parts = [c.text for c in getattr(res, "content", []) if getattr(c, "type", "") == "text"]
                ok = not getattr(res, "is_error", False)
                text = "\n".join(parts)
        except Exception as e:
            ok, text = False, _explain(e)
        secs = round(time.time() - t0, 2)
        self.log.info("call %s.%s (%s) %s in %.1f s", plugin, tool, p.effect(tool), "ok" if ok else "FAILED", secs)
        sys_log.trace("plugins", "plugin.call", {"plugin": plugin, "tool": tool, "effect": p.effect(tool), "ok": ok,
                                                 "seconds": secs}, run_id=run_id)
        return {"ok": ok, "text": text, "seconds": secs}

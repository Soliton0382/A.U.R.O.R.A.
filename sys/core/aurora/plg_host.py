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
_lock = threading.Lock()


def _explain(e: BaseException) -> str:
    """The real error inside the task groups of the MCP client."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return f"{type(e).__name__}: {e}"


@dataclass
class Plugin:
    name: str
    folder: Path
    manifest: dict
    missing: list[str] = field(default_factory=list)       # required .env keys that are empty
    enabled: bool = True
    tools: list[dict] = field(default_factory=list)          # {"name", "description", "input_schema", "effect"}
    error: str = ""

    @property
    def available(self) -> bool:
        return self.enabled and not self.missing and not self.error

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

    def plugins(self, with_tools: bool = True) -> list[Plugin]:
        out, st = [], self._state()
        if not self.dir.is_dir():
            return out
        for mf in sorted(self.dir.glob("*/plugin.json")):
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except ValueError as e:
                out.append(Plugin(mf.parent.name, mf.parent, {}, error=f"bad manifest: {e}"))
                continue
            p = Plugin(manifest.get("name", mf.parent.name), mf.parent, manifest,
                       missing=[k for k in manifest.get("requires", []) if not str(self.cfg.values.get(k, "") or "").strip()],
                       enabled=st.get(manifest.get("name", mf.parent.name), {}).get("enabled", True))
            from . import sys_ethics
            if (bad := sys_ethics.forbidden_capabilities(manifest)):      # ethics code, level A: never loaded
                p.error = f"refused by the ethics code (level A): {', '.join(bad)}"
                self.log.warning("plugin %s refused by the ethics code: %s", p.name, ", ".join(bad))
                out.append(p)
                continue
            if with_tools and p.enabled and not p.missing:
                try:
                    p.tools = self._tools(p, mf.stat().st_mtime)
                except Exception as e:                       # a broken plugin must not break the others
                    p.error = _explain(e)
                    self.log.warning("plugin %s: cannot list tools: %s", p.name, p.error)
            out.append(p)
        return out

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
        for k in p.manifest.get("env", []):
            env[k] = str(self.cfg.values.get(k, "") or "")
        for k, v in p.manifest.get("env_as", {}).items():     # .env key -> name the program expects
            env[v] = str(self.cfg.values.get(k, "") or "")
        from . import plg_sandbox
        filtered = plg_sandbox.env_file(p.name, p.manifest, self.cfg)    # only this plugin's own secrets
        if self.cfg["AURORA_PLUGIN_SANDBOX"]:
            if not plg_sandbox.available():
                # never uncaged because the cage is missing (C226: a container without bubblewrap ran them bare, as
                # the ports already refuse): the owner may switch the cage off on purpose, never by accident
                raise RuntimeError("no cage here (bubblewrap is missing): the plugin is not run")
            cmd = plg_sandbox.wrap(cmd, p.folder, p.manifest, filtered, self.cfg)   # inside, .env is the filtered one
        else:
            env["AURORA_ENV_FILE"] = str(filtered)
        return StdioServerParameters(command=cmd[0], args=cmd[1:], env=env, cwd=str(p.folder))

    async def _session(self, p: Plugin, work):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        errlog = open(self.cfg.path("AURORA_LOG_DIR") / "plugins" / f"{p.name}.stderr.log", "a", encoding="utf-8")
        try:
            async with stdio_client(self._params(p), errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await work(session)
        finally:
            errlog.close()

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
        return asyncio.run(asyncio.wait_for(coro, self.cfg["AURORA_PLUGIN_TIMEOUT_S"]))

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

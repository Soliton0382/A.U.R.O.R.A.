# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Status, features, services, settings (.env through the schema)."""
from __future__ import annotations

import asyncio
import httpx

from aurora import sys_config, sys_log
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import _admin, auth, cfg, log, user_of

router = APIRouter()
from aurora.net_cloudflare import KEYS as TUNNEL_KEYS  # noqa: E402


# ---- status and settings -------------------------------------------------------------------
@router.get("/v1/aurora/status", dependencies=[Depends(auth)])
def status() -> dict:
    import httpx
    from aurora.sol_reader import VaultReader
    out = {"vault": VaultReader(cfg).count()}
    for name, url in (("models", f"http://{cfg['AURORA_MODELS_HOST']}:{cfg['AURORA_MODELS_PORT']}/health"),
                      ("llm", f"http://{cfg['AURORA_LLM_HOST']}:{cfg['AURORA_LLM_PORT']}/health")):
        if name == "llm" and str(cfg["AURORA_LLM_BACKEND"]) == "cloud":
            from aurora import mdl_router
            why = mdl_router.CloudBase(cfg).problem()
            out[name] = {"status": "down" if why else "cloud", "provider": cfg["AURORA_CLOUD_PROVIDER"],
                         "model": cfg["AURORA_CLOUD_MODEL"], **({"error": why} if why else {})}
            continue
        try:
            out[name] = httpx.get(url, timeout=3).json()
        except httpx.HTTPError as e:
            out[name] = {"status": "down", "error": str(e)}
    return out


@router.get("/v1/aurora/settings", dependencies=[Depends(auth)])
def settings(request: Request) -> dict:
    """The settings as the asking user sees them: the machine's, and their own (U3: their usr/<name>/.env)."""
    from aurora import sys_user_config, sys_users_layout
    schema = sys_config.load_schema()
    current = sys_config.parse_env(sys_config.env_file_path().read_text(encoding="utf-8"))
    user = user_of(request)
    if user and sys_users_layout.migrated(cfg):
        own = sys_config.parse_env(sys_user_config.env_path(cfg, user).read_text(encoding="utf-8")) \
            if sys_user_config.env_path(cfg, user).is_file() else {}
        current.update({s["key"]: own.get(s["key"], s["recommended"]) for s in schema["settings"] if s.get("scope") == "user"})
    from .core import plugin_host
    card = {}                                           # a plugin's settings live in its card on the Plugins page
    for p in plugin_host().plugins(with_tools=False):
        if getattr(p, "admin_only", False):
            continue
        m = p.manifest
        for k in m.get("env", []) + m.get("requires", []) + list(m.get("env_as", {})) + m.get("settings", []):
            card.setdefault(k, p.name)
    items = []
    mine_only = bool(user) and user != _admin()   # a user: only their own settings, never the machine's values
    for s in schema["settings"]:
        if mine_only and s.get("scope") != "user":
            continue
        value = current.get(s["key"], "")
        items.append({**s, "value": ("••••••" if s.get("secret") and value else value), "plugin": card.get(s["key"])})
    return {"categories": schema["categories"], "settings": items}


@router.post("/v1/aurora/settings/factory", dependencies=[Depends(auth)])
async def settings_factory(request: Request) -> dict:
    """{"keep_keys": true}: the behaviour settings back to their recommended values (sys_reset.settings); the .env before
    is kept. The admin's only. Aurora as just installed (memory, state) is script/sys_factory_reset.py."""
    from aurora import sys_reset
    user, admin = user_of(request), _admin()
    if user and admin and user != admin:
        raise HTTPException(status_code=403, detail="only the admin")
    body = await request.json()
    out = sys_reset.settings(cfg, keep_keys=body.get("keep_keys", True) is not False,
                             base="recommended" if body.get("base") == "recommended" else "installed")
    log.info("audit: factory settings (%s): %d changed, .env kept in %s", out["base"], len(out["changed"]), out["backup"])
    return {**out, "command_mind": f"cd {cfg.root} && .venv/bin/python sys/core/script/sys_factory_reset.py --apply"}


@router.get("/v1/aurora/factory", dependencies=[Depends(auth)])
def factory_state() -> dict:
    """What «back to the factory» means here (ROADMAP 102): a copy of the installation's settings or not, what the
    mind's reset would move aside, and the last reset's result."""
    import json
    from aurora import sys_reset
    f, last = sys_reset.installed_file(cfg), None
    try:
        last = json.loads(sys_reset.result_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"installed": f.exists(), "installed_at": f.stat().st_mtime if f.exists() else None,
            "mind": sys_reset.mind_plan(cfg)["places"], "last": last}


@router.post("/v1/aurora/factory/mind", dependencies=[Depends(auth)])
async def factory_mind(request: Request) -> dict:
    """{"confirm": "AZZERA", "with_knowledge": false, "keep_keys": true}: Aurora as just installed, from the WebUI. It
    stops Aurora, so it runs in aurora-reset.service (outside the API); nothing is deleted (moved aside)."""
    import subprocess
    from aurora import sys_reset
    user, admin = user_of(request), _admin()
    if user and admin and user != admin:
        raise HTTPException(status_code=403, detail="only the admin")
    body = await request.json()
    if str(body.get("confirm", "")).strip() != "AZZERA":
        raise HTTPException(status_code=400, detail="type AZZERA to confirm")
    sys_reset.ask(cfg, bool(body.get("with_knowledge")), body.get("keep_keys", True) is not False, user or admin or "")
    r = subprocess.run(["systemctl", "start", "--no-block", "aurora-reset.service"], capture_output=True, text=True,
                       timeout=30)
    if r.returncode:
        sys_reset.take(cfg)                               # not started: the request must not wait for a later start
        raise HTTPException(status_code=409, detail="aurora-reset.service is not installed yet: "
                            f"cd {cfg.root} && .venv/bin/python sys/core/script/sys_install_services.py && "
                            f"sudo bash sys/deploy/systemd/install.sh ({r.stderr.strip()[:200]})")
    log.info("audit: factory reset of the mind asked from the WebUI (knowledge: %s)", bool(body.get("with_knowledge")))
    return {"started": True}


@router.put("/v1/aurora/settings", dependencies=[Depends(auth)])
async def update_settings(request: Request) -> dict:
    changes: dict = await request.json()
    specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
    problems = []
    for key, value in changes.items():
        if key not in specs:
            problems.append(f"{key}: not in the settings schema")
            continue
        try:
            sys_config.convert(specs[key], str(value))
        except ValueError as e:
            problems.append(f"{key}: {e}")
    if not problems and {"AURORA_HTTPS_PORT", "AURORA_HTTP_PORT"} & set(changes):
        from aurora import net_https                 # the 🔒 page's checks (C227: 9700, the API's port, was accepted)
        now = net_https.fresh(cfg)
        try:
            net_https.check_ports(cfg, int(changes.get("AURORA_HTTPS_PORT", now["AURORA_HTTPS_PORT"])),
                                  int(changes.get("AURORA_HTTP_PORT", now["AURORA_HTTP_PORT"])))
        except net_https.HttpsError as e:
            problems.append(f"AURORA_HTTPS_PORT / AURORA_HTTP_PORT: {e}")
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    moved = None
    if {"AURORA_HTTPS_PORT", "AURORA_HTTP_PORT"} & set(changes):
        # the ports: never only written — Caddy moved with them at once (C228: the .env changed, Caddy did not)
        from aurora import net_https
        now = net_https.fresh(cfg)
        try:
            moved = await asyncio.to_thread(net_https.set_ports, cfg,
                                            int(changes.pop("AURORA_HTTPS_PORT", now["AURORA_HTTPS_PORT"])),
                                            int(changes.pop("AURORA_HTTP_PORT", now["AURORA_HTTP_PORT"])))
        except net_https.HttpsError as e:
            raise HTTPException(status_code=422, detail=[f"AURORA_HTTPS_PORT / AURORA_HTTP_PORT: {e}"]) from None
        if not changes:
            return {"changed": ["AURORA_HTTPS_PORT", "AURORA_HTTP_PORT"], "restart": [], "mounting": False,
                    "retimed": False, "tunnel": False, **({"moved": moved["urls"]} if moved.get("changed") else {})}
    from aurora import sys_user_config, sys_users_layout, sys_users_mode
    user, admin = user_of(request), _admin()
    if user and admin and user != admin and any(specs[k].get("scope") != "user" for k in changes):
        raise HTTPException(status_code=403, detail="only the admin changes the machine's settings")   # before anything
    if "AURORA_USER_MODE" in changes and str(changes["AURORA_USER_MODE"]) != sys_users_mode.current(cfg):
        try:                                                 # single ↔ multi: what it does, refused or confirmed
            sys_users_mode.switch(cfg, str(changes["AURORA_USER_MODE"]), user, admin,
                                  confirm=request.query_params.get("confirm") == "purge")
        except sys_users_mode.ModeError as e:
            raise HTTPException(status_code=409, detail={"message": str(e), "plan": e.plan}) from None
    who = user or admin                                    # the API's own key (no user): the admin's (C340)
    if who and sys_users_layout.migrated(cfg):               # U3: a user's own settings go to their usr/<name>/.env
        user = who
        mine = {k: str(v) for k, v in changes.items() if specs[k].get("scope") == "user"}
        machine = {k: str(v) for k, v in changes.items() if k not in mine}
        if machine and user != admin:
            raise HTTPException(status_code=403, detail="only the admin changes the machine's settings")
        from aurora import sys_users_perm                  # a user's own settings: when the admin lets them
        if set(mine) - set(sys_users_perm.PERSONAL) and not sys_users_perm.may(cfg, user, "settings", admin):
            raise HTTPException(status_code=403, detail="the admin keeps your settings for themselves (👥 Users → permissions)")
        if mine:
            sys_user_config.write(cfg, user, mine)
    else:
        machine = {k: str(v) for k, v in changes.items()}
    if machine:
        sys_config.write_env(sys_config.env_file_path(), machine)
    restart = sorted({svc for k in changes for svc in specs[k]["services"]})
    log.info("audit: settings changed: %s; services to restart: %s", ", ".join(sorted(changes)), ", ".join(restart))
    sys_log.trace("api", "settings.change", {"keys": sorted(changes), "restart": restart})
    from .backup import NAS_KEYS, start_mount             # the backup plugin saved with a NAS folder: mount it now
    mounting = bool(NAS_KEYS & set(changes)) and start_mount(str(changes.get("AURORA_BACKUP_DIR", cfg["AURORA_BACKUP_DIR"])))
    mounting = mounting or start_mount(str(changes.get("AURORA_ASTRO_FRAMES_DIR", "")))   # the frames on the NAS (N29)
    from .tunnel import start_tunnel                        # the cloudflare plugin saved: everything set up (roadmap 56)
    tunnel = bool(TUNNEL_KEYS & set(changes)) and start_tunnel()
    from .backup import start_retime                        # a new backup time: the timer follows it
    retimed = "AURORA_BACKUP_TIME" in changes and start_retime()
    return {"changed": sorted(changes), "restart": restart, "mounting": mounting, "retimed": retimed, "tunnel": tunnel,
            **({"moved": moved["urls"]} if moved and moved.get("changed") else {})}


@router.get("/v1/aurora/ups", dependencies=[Depends(auth)])
def ups() -> dict:
    """The UPS's last read (sys_ups, aurora-rem's watch): mains or battery, charge, runtime, the mode."""
    from aurora import sys_ups
    return sys_ups.status(cfg)


@router.get("/v1/aurora/debug/memory", dependencies=[Depends(auth)])
def debug_memory(request: Request, trim: bool = False) -> dict:
    """What the API's memory is (C389): anonymous memory, glibc's arenas, the most numerous Python objects; with
    trim=1, malloc_trim(0) and the anonymous memory again — freed by it = fragmentation, kept = live objects."""
    user = user_of(request)
    if user and user != _admin():
        raise HTTPException(status_code=403, detail="the owner's only")
    import collections
    import ctypes
    import gc

    def anon() -> float:
        with open("/proc/self/smaps_rollup", encoding="ascii") as f:
            return next(int(l.split()[1]) for l in f if l.startswith("Anonymous:")) / 1024

    try:
        before = anon()
    except OSError:                                    # no /proc (the Mac, Windows): nothing to read
        return {"error": "not available on this system"}
    out = {"anon_mib": round(before), "threads": len(__import__("os").listdir("/proc/self/task"))}
    with open("/proc/self/smaps", encoding="ascii", errors="replace") as f:
        sizes, cur = [], None
        for line in f:
            if "-" in line.split(" ", 1)[0] and len(line.split()) < 6:     # an anonymous mapping's header
                cur = len(sizes)
                sizes.append(0)
            elif "-" in line.split(" ", 1)[0]:
                cur = None
            elif cur is not None and line.startswith("Anonymous:"):
                sizes[cur] += int(line.split()[1])
    out["anon_mappings"] = len(sizes)
    out["arena_like_mib"] = round(sum(s for s in sizes if 60_000 <= s <= 132_000) / 1024)
    counts = collections.Counter(type(o).__name__ for o in gc.get_objects())
    out["objects"] = sum(counts.values())
    out["top_types"] = counts.most_common(15)
    if trim:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        out["after_trim_mib"] = round(anon())
        out["freed_by_trim_mib"] = round(before - anon())
    return out


# ---- the devices' management pages (sys_consoles) ------------------------------------------------
@router.get("/v1/aurora/consoles", dependencies=[Depends(auth)])
def consoles() -> list[dict]:
    from aurora import sys_consoles
    return sys_consoles.load(cfg)


@router.post("/v1/aurora/consoles", dependencies=[Depends(auth)])
def console_add(body: dict) -> dict:
    from aurora import sys_consoles
    try:
        return sys_consoles.put(cfg, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.put("/v1/aurora/consoles/{cid}", dependencies=[Depends(auth)])
def console_change(cid: str, body: dict) -> dict:
    from aurora import sys_consoles
    try:
        return sys_consoles.put(cfg, body, cid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.delete("/v1/aurora/consoles/{cid}", dependencies=[Depends(auth)])
def console_delete(cid: str) -> dict:
    from aurora import sys_consoles
    if not sys_consoles.delete(cfg, cid):
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": cid}

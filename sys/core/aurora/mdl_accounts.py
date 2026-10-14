# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Cloud accounts, per installation or per user (ROADMAP 106; owner, 15 Oct: «rendiamo più facile la gestione degli
account per user o per environment… da cli voglio che si acceda il minimo possibile»).

An account is a provider's key (anthropic, openai…) or a Claude subscription logged in from the WebUI (claude_code: its
own CLAUDE_CONFIG_DIR, `claude auth login` run by Aurora, the code pasted in the page — no terminal). It is «shared»
(the installation's, the admin's to manage: the enterprise case) or a user's own. The admin's POLICY says who uses what:
  shared           everyone uses the shared accounts (the default: nothing changes)
  own              each user only their own; without one, the local model
  own_else_shared  their own first, else the shared one
Without a shared account for a provider, the installation's setup of before (the .env's key, the service user's own
claude login) is the shared one. The file and the login folders are the service user's alone (0600/0700): the
machine's administrator can still read them — said on the page, never promised otherwise."""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import sys_config

POLICIES = ("shared", "own", "own_else_shared")
LEGACY = object()                                   # the installation's setup of before (.env, ~/.claude)
_lock = threading.Lock()
_logins: dict[str, dict] = {}


def _base(cfg: sys_config.Config) -> sys_config.Config:
    return cfg.base or cfg


def _admin(cfg: sys_config.Config) -> str | None:
    try:
        from .sys_users import Users
        return Users(_base(cfg)).admin_name()
    except Exception:                                  # noqa: BLE001 — no users store: no admin to tell apart
        return None


def _file(cfg: sys_config.Config) -> Path:
    return _base(cfg).path("AURORA_STATUS_DIR") / "cloud_accounts.json"


def claude_dir(cfg: sys_config.Config, account_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", account_id or ""):
        raise ValueError("not an account")
    return _base(cfg).path("AURORA_STATUS_DIR") / "cloud_accounts" / account_id


def load(cfg: sys_config.Config) -> dict:
    try:
        d = json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"policy": d.get("policy") if d.get("policy") in POLICIES else "shared", "accounts": d.get("accounts", [])}


def _save(cfg: sys_config.Config, d: dict) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(d, h, ensure_ascii=False, indent=1)
    os.replace(tmp, f)


# ---- who uses what ------------------------------------------------------------------------------------------------
def pick(cfg: sys_config.Config, provider: str):
    """The account `cfg`'s user uses for `provider`: an account dict, LEGACY (the setup of before), or None (the policy
    leaves this user without a cloud account: the local model)."""
    d = load(cfg)
    user = cfg.user
    mine = [a for a in d["accounts"] if a["provider"] == provider and a["scope"] == "user" and a.get("user") == user]
    shared = [a for a in d["accounts"] if a["provider"] == provider and a["scope"] == "shared"]
    if user is None or user == _admin(cfg) or d["policy"] == "shared":   # the admin's work, or one account for all
        return shared[0] if shared else LEGACY
    if mine:
        return mine[0]
    if d["policy"] == "own":
        return None
    return shared[0] if shared else LEGACY


def key_for(cfg: sys_config.Config, provider: str, env_key: str) -> str:
    """The key of the account in use; the .env's for the setup of before; empty without one."""
    a = pick(cfg, provider)
    if a is LEGACY:
        return str(cfg.values.get(env_key) or "")
    return str((a or {}).get("key") or "")


def claude_env(cfg: sys_config.Config) -> dict | None:
    """What the claude CLI runs with for this user: {} the service user's own login, {"CLAUDE_CONFIG_DIR": …} an
    account's, None no account for this user (the local model)."""
    a = pick(cfg, "claude_code")
    if a is LEGACY:
        return {}
    if a is None:
        return None
    return {"CLAUDE_CONFIG_DIR": str(claude_dir(cfg, a["id"]))}


# ---- accounts -----------------------------------------------------------------------------------------------------
def visible(cfg: sys_config.Config, user: str | None, admin: bool) -> list[dict]:
    """The shared accounts and the user's own (every one for the admin), keys never shown whole."""
    out = []
    for a in load(cfg)["accounts"]:
        if a["scope"] == "shared" or a.get("user") == user or admin:
            k = str(a.get("key") or "")
            out.append({**{x: y for x, y in a.items() if x != "key"}, "key": f"…{k[-4:]}" if k else "",
                        "mine": a.get("user") == user and a["scope"] == "user"})
    return out


def add(cfg: sys_config.Config, provider: str, scope: str, user: str | None, label: str = "", key: str = "") -> dict:
    from .mdl_router import PROVIDERS, _services
    _services(cfg)
    if provider not in PROVIDERS or provider == "local":
        raise ValueError(f"no cloud provider {provider!r}")
    if scope not in ("shared", "user"):
        raise ValueError("scope: shared or user")
    needs_key = provider != "claude_code" and not PROVIDERS[provider].get("key_optional")
    if needs_key and len(key.strip()) < 8:
        raise ValueError("this provider needs its key")
    a = {"id": secrets.token_hex(6), "provider": provider, "scope": scope, "user": user if scope == "user" else None,
         "label": label.strip()[:60], "key": key.strip(), "created": time.time()}
    with _lock:
        d = load(cfg)
        d["accounts"].append(a)
        _save(cfg, d)
    if provider == "claude_code":
        claude_dir(cfg, a["id"]).mkdir(parents=True, exist_ok=True, mode=0o700)
    return a


def get(cfg: sys_config.Config, account_id: str) -> dict:
    for a in load(cfg)["accounts"]:
        if a["id"] == account_id:
            return a
    raise KeyError(account_id)


def remove(cfg: sys_config.Config, account_id: str) -> None:
    """The account gone, and a Claude login's folder with it (the credentials are not left behind)."""
    with _lock:
        d = load(cfg)
        d["accounts"] = [a for a in d["accounts"] if a["id"] != account_id]
        _save(cfg, d)
    waiting = _logins.pop(account_id, None)
    if waiting:                                          # a sign-in left open: its CLI closed first
        waiting["proc"].kill()
        os.close(waiting["fd"])
    folder = claude_dir(cfg, account_id)
    if folder.is_dir():
        shutil.rmtree(folder)


def set_policy(cfg: sys_config.Config, policy: str) -> None:
    if policy not in POLICIES:
        raise ValueError(f"policy: one of {POLICIES}")
    with _lock:
        d = load(cfg)
        d["policy"] = policy
        _save(cfg, d)


# ---- the Claude login, from the page --------------------------------------------------------------------------------
URL = re.compile(r"https://[^\s\x07\x1b]*oauth[^\s\x07\x1b]*")


def _bin(cfg: sys_config.Config) -> str:
    return shutil.which(str(cfg["AURORA_CLAUDE_CODE_BIN"])) or str(cfg["AURORA_CLAUDE_CODE_BIN"])


def _env(cfg: sys_config.Config, account_id: str) -> dict:
    return {**os.environ, "CLAUDE_CONFIG_DIR": str(claude_dir(cfg, account_id)), "BROWSER": "/bin/false"}


def login_start(cfg: sys_config.Config, account_id: str, wait: float = 20.0) -> str:
    """`claude auth login` started for the account, in a terminal of its own: the address to open, where the person
    signs in and gets the code to paste back (login_finish)."""
    import pty
    old = _logins.pop(account_id, None)
    if old:
        old["proc"].kill()
    term, slave = pty.openpty()
    proc = subprocess.Popen([_bin(cfg), "auth", "login"], stdin=slave, stdout=slave, stderr=slave,
                            env=_env(cfg, account_id), cwd=str(claude_dir(cfg, account_id)), start_new_session=True)
    os.close(slave)
    seen, t0 = b"", time.time()
    while time.time() - t0 < wait and proc.poll() is None:
        import select
        if select.select([term], [], [], 0.5)[0]:
            try:
                seen += os.read(term, 4096)
            except OSError:
                break
            m = URL.search(seen.decode(errors="replace"))
            if m and b"code" in seen.lower().split(m.group(0).encode())[-1]:
                _logins[account_id] = {"proc": proc, "fd": term, "at": time.time()}
                return m.group(0)
    proc.kill()
    os.close(term)
    raise RuntimeError("the claude login gave no address: " + re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", seen.decode(errors="replace"))[-200:])


def login_finish(cfg: sys_config.Config, account_id: str, code: str, wait: float = 40.0) -> dict:
    """The code from the sign-in page given to the waiting login; then the account's status."""
    s = _logins.pop(account_id, None)
    if not s:
        raise RuntimeError("no login waiting for this account: start it again")
    try:
        os.write(s["fd"], code.strip().encode() + b"\r")
        try:
            s["proc"].wait(timeout=wait)
        except subprocess.TimeoutExpired:
            s["proc"].kill()
    finally:
        os.close(s["fd"])
    return status(cfg, account_id)


def status(cfg: sys_config.Config, account_id: str) -> dict:
    """{"logged_in", "email", "plan"} of a Claude account (`claude auth status`), or of a key: whether it is set."""
    a = get(cfg, account_id)
    if a["provider"] != "claude_code":
        return {"logged_in": bool(a.get("key")), "email": "", "plan": ""}
    try:
        r = subprocess.run([_bin(cfg), "auth", "status", "--json"], capture_output=True, text=True, timeout=20,
                           env=_env(cfg, account_id), cwd=str(claude_dir(cfg, account_id)))
        d = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        d = {}
    return {"logged_in": bool(d.get("loggedIn")), "email": d.get("email") or "", "plan": d.get("subscriptionType") or ""}

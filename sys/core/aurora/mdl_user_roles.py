# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Each user's own models, step by step (ROADMAP 106; owner, 14 Oct: «ogni utente si configura le parti dei modelli
che preferisce con il proprio account cloud… se ovviamente l'admin lo permette»).

The admin's choice (the 🧠 Models page, models/roles.json) is the installation's and every user's start. When the
admin's account policy is not «shared» (own; own, else shared: mdl_accounts.POLICIES), a user may choose for each step
the local model or a provider their account reaches — their own, or the shared one the policy lends them
(mdl_router.configured, asked as that user). Their choice is kept in their own state folder, models/roles.user.<name>.json, and
read for their calls only; a step they did not choose follows the admin's. Under «shared» the admin's choice is
everyone's again: the user's file is kept, not used. The forge's steps are the admin's work, never a user's.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import sys_config

ADMIN_ONLY = {"forge_write", "forge_judge"}


def _file(cfg: sys_config.Config, user: str) -> Path:
    from . import sys_users_layout
    if not user or "/" in user or "\\" in user or user.startswith("."):
        raise ValueError(f"not a user name: {user!r}")
    # a name of its own: before the users' migration (U3) every user's state folder is the installation's, and
    # models/roles.json there is the admin's choice (found by the test, 9 Nov)
    return sys_users_layout.place(cfg, "state", user) / "models" / f"roles.user.{user}.json"


def allowed(cfg: sys_config.Config) -> bool:
    """This user may choose their own models: not the admin (the Models page is theirs), the policy not «shared»."""
    from . import mdl_accounts
    user = getattr(cfg, "user", None)
    if not user:
        return False
    try:
        return user != mdl_accounts._admin(cfg) and mdl_accounts.load(cfg)["policy"] != "shared"
    except Exception:                                    # noqa: BLE001 — no accounts readable: the installation's
        return False


def mine(cfg: sys_config.Config) -> dict[str, dict]:
    """{role: {"provider", "model"}} this user chose, when allowed; {} otherwise (the admin's choice holds)."""
    from .mdl_router import PROVIDERS, ROLES
    if not allowed(cfg):
        return {}
    try:
        saved = json.loads(_file(cfg, cfg.user).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {r: {"provider": a["provider"], "model": str(a.get("model", ""))[:200]}
            for r, a in (saved if isinstance(saved, dict) else {}).items()
            if r in ROLES and r not in ADMIN_ONLY and isinstance(a, dict) and a.get("provider") in PROVIDERS}


def set_mine(cfg: sys_config.Config, changes: dict) -> dict[str, dict]:
    """Some steps chosen by this user ({role: {"provider", "model"}}, None = the admin's again); a provider their
    account does not reach is refused, saying why."""
    from .mdl_router import PROVIDERS, ROLES, configured
    if not allowed(cfg):
        raise PermissionError("the admin's policy gives every user the installation's models («shared»)")
    cur = mine(cfg)
    for role, a in (changes or {}).items():
        if role not in ROLES or role in ADMIN_ONLY:
            raise ValueError(f"not a step a user chooses: {role}")
        if a is None:                                   # this step back to the admin's choice
            cur.pop(role, None)
            continue
        if not isinstance(a, dict) or a.get("provider") not in PROVIDERS:
            raise ValueError(f"unknown provider for {role}: {a.get('provider') if isinstance(a, dict) else a}")
        if not configured(a["provider"], cfg):
            raise ValueError(f"{a['provider']}: no account of yours reaches it — add one in ☁️ Cloud accounts first")
        cur[role] = {"provider": a["provider"], "model": str(a.get("model", ""))[:200]}
    f = _file(cfg, cfg.user)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, f)
    return cur


def reset(cfg: sys_config.Config) -> None:
    """Back to the admin's choice for every step."""
    if getattr(cfg, "user", None):
        _file(cfg, cfg.user).unlink(missing_ok=True)

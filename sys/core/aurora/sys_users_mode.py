# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Single or multi-user (AURORA_USER_MODE), and what a switch does (docs/MULTIUSER.md).

single → multi: nothing moves (one layout for both modes); possible only on the per-user layout and once the login
with password and TOTP exists (U5: MULTI_READY), never a multi-user without a login.
multi → single: every user but the admin is purged with all that is theirs (sys_users_layout.purge, which checks
itself); first the list of what goes, then only with the owner's explicit confirmation. The admin's data never moves.
Only the admin switches.
"""
from __future__ import annotations

from . import sys_config, sys_users_layout as L

MULTI_READY = False          # U5: the login page (name, password, TOTP) and the Users page; until then no "multi"
MODES = ("single", "multi")


class ModeError(Exception):
    """A switch refused, with what to do; `plan` lists what a confirmed switch would remove."""

    def __init__(self, text: str, plan: list | None = None):
        super().__init__(text)
        self.plan = plan or []


def current(cfg: sys_config.Config) -> str:
    return str(cfg["AURORA_USER_MODE"])


def others(cfg: sys_config.Config, admin: str | None) -> list[str]:
    from .sys_users import Users
    if not (cfg.base or cfg).path("AURORA_STATUS_DIR").joinpath("users.db").exists():
        return []
    return sorted(u["name"] for u in Users(cfg.base or cfg).list() if u["name"] != admin)


def switch(cfg: sys_config.Config, to: str, user: str | None, admin: str | None, confirm: bool = False) -> dict:
    """Check (and for multi → single, do) a change of mode before the setting is written."""
    base = cfg.base or cfg
    if to not in MODES:
        raise ModeError(f"mode: one of {MODES}")
    if user and admin and user != admin:
        raise ModeError("only the admin changes the mode")
    if to == "multi":
        if not L.migrated(base):
            raise ModeError("multi-user needs the per-user layout first: sys/core/script/sys_users_migrate.py")
        if not MULTI_READY:
            raise ModeError("il multi-utente si attiva quando l'accesso con password e codice Authenticator sarà pronto "
                            "(fase U5): per ora Aurora resta single")
        return {"removed": []}
    gone = others(base, admin)
    if not gone:
        return {"removed": []}
    plan = [{"user": n, "items": L.purge_plan(base, n)} for n in gone]
    if not confirm:
        raise ModeError(f"passing to single deletes {len(gone)} users with all their data: "
                        f"{', '.join(gone)}. Confirm to go on", plan)
    for n in gone:
        L.purge(base, n, admin)
    return {"removed": gone}

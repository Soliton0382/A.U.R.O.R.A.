# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""«Tutto cloud»: the owner's signed consent that private data (health, the firewall's configuration) may go, masked, to
the cloud model where this machine has no local reasoner running (owner, 2026-10-08: «se invece si vuole tutto Cloud
allora si indica con triangolo giallo e popup e si indica di eseguire il comando da Shell»).

Signed like the level B exemption (sys_ethics), with the installation's key that only root can use (COMMAND, run in
a shell), so nothing reachable from the web can give it. Taking it back needs no shell: the file is removed (the Models page's
«Cloud con privacy» or «Tutto locale» do it), because going back to privacy must always be easy.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from . import sys_config, sys_ethics

PURPOSE = "aurora-private-data-to-cloud"
COMMAND = "sudo .venv/bin/python sys/core/script/sys_ethics_sign.py private-cloud"


def message(root: Path) -> bytes:
    return f"{PURPOSE}|{sys_ethics.machine_id()}|{root}".encode()


def path(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_ETHICS_EXEMPTION").with_name("private_to_cloud.sig")


@lru_cache(maxsize=8)
def _signed(file: str, mtime: float, root: str, public_hex: str) -> bool:
    try:
        sig = Path(file).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return sys_ethics._verify(message(Path(root)), sig, public_hex)


def signed(cfg: sys_config.Config) -> bool:
    """The owner signed it, for this machine and this folder (a copied file is worth nothing elsewhere)."""
    p = path(cfg)
    public_hex, _ = sys_ethics.owner_public_key()
    if not p.exists() or not public_hex:
        return False
    return _signed(str(p), p.stat().st_mtime, str(cfg.root), public_hex)


def revoke(cfg: sys_config.Config) -> bool:
    """Back to privacy: the consent removed. True when there was one."""
    p = path(cfg)
    if not p.exists():
        return False
    p.unlink()
    return True

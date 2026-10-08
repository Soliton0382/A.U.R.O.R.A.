# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The operating system Aurora runs on, behind one interface (base.Platform): linux (the reference), mac, windows.

    from aurora import sys_platform
    sys_platform.current().service_state("aurora-api")

Each port folder carries its own backend next to the reference one; asking for a system whose backend is not in this
build is an error that says so (never a silent fall back to Linux commands)."""
from __future__ import annotations

import importlib
import sys

from .base import Device, Gpu, Platform, Result, run_command  # noqa: F401 — the interface, imported from here

BACKENDS = {"linux": ("linux", "Linux"), "darwin": ("mac", "Mac"), "win32": ("windows", "Windows")}
_current: Platform | None = None


def for_system(system: str, **kw) -> Platform:
    """The backend of `system` (a sys.platform value): the tests build each one on any machine."""
    if system not in BACKENDS:
        raise RuntimeError(f"Aurora has no backend for {system!r}: linux, darwin (Mac) and win32 (Windows) only")
    module, cls = BACKENDS[system]
    try:
        mod = importlib.import_module(f".{module}", __name__)
    except ModuleNotFoundError as e:
        raise RuntimeError(f"this build of Aurora has no {module} backend ({e.name})") from e
    return getattr(mod, cls)(**kw)


def current() -> Platform:
    global _current
    if _current is None:
        _current = for_system(sys.platform)
    return _current

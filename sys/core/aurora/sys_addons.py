# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Add-ons: a piece that lives in a folder of its own beside Aurora's core and is loaded only when installed (owner, 27
Nov, of Evidentia: «essendo che è un add-on sarebbe come concetto un plugin nella sua sandbox»).

An add-on is the package sys/<name>/addon/ whose `__init__.py` declares what it brings to Aurora: `routers()` (its API routes,
which only carry requests to its own service), `ticks()` (work done in each user's routine tick), and `webui/` (its
pages, served at /static/addons/<name>/, entered through webui/index.js). It is «installed» when its root settings file
exists (/etc/aurora/<name>.env, written by `aurora-root install <name>`): the code may be in every copy of Aurora, it is
loaded only where the owner installed it. Nothing of an add-on's data passes through here."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KNOWN = ("evidentia",)                                   # the add-ons this code knows; a new one is added here, signed
# an add-on that keeps ONE archive for the whole machine may be opened to other users only once it keeps one per user:
# until then the admin's access page refuses (owner's data never shown to another user by a click)
PER_USER = {"evidentia": True}
ETC = Path(os.environ.get("ADDONS_ETC") or "/etc/aurora")


def installed() -> list[str]:
    return [n for n in KNOWN if (ETC / f"{n}.env").is_file() and (ROOT / "sys" / n / "addon" / "__init__.py").is_file()]


_loaded: dict = {}


def module(name: str):
    """The add-on's package, loaded by path once (it is not a package of Aurora's); its modules import each other."""
    if name not in _loaded:
        import sys
        folder = ROOT / "sys" / name / "addon"
        pkg = f"aurora_addon_{name}"
        spec = importlib.util.spec_from_file_location(pkg, folder / "__init__.py",
                                                      submodule_search_locations=[str(folder)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[pkg] = mod
        spec.loader.exec_module(mod)
        _loaded[name] = mod
    return _loaded[name]


def webui_dir(name: str) -> Path:
    return ROOT / "sys" / name / "addon" / "webui"


def routers() -> list:
    out = []
    for n in installed():
        out += list(getattr(module(n), "routers", lambda: [])())
    return out


def ticks() -> list:
    out = []
    for n in installed():
        out += list(getattr(module(n), "ticks", lambda: [])())
    return out


def listing(allowed=lambda name: True) -> list[dict]:
    """For the WebUI: each installed add-on's entry module the person may use."""
    return [{"name": n, "entry": f"/static/addons/{n}/index.js"} for n in installed()
            if (webui_dir(n) / "index.js").is_file() and allowed(n)]

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The language of whoever reads (C526): a sentence the server builds follows the person's own choice.

The choice is made in the WebUI and kept per person in <AURORA_STATUS_DIR>/ui_prefs.json (api/users); without one,
the installation's AURORA_LANG_DEFAULT. `reader()` answers "it" or "en" for the user of the request being served
(sys_config.get() is context-aware), or for the configuration it is given; `say(it, en)` picks the sentence.
A process that never loaded a configuration gets Italian: choosing a word never loads one.
Background work without a user reads the admin's choice. What the machine itself speaks or harvests (the harvest's
languages, the seed) stays on AURORA_LANG_DEFAULT: that is the installation's, not a reader's.
"""
from __future__ import annotations

import json

from . import sys_config

_cache: dict = {}            # path -> (mtime_ns, parsed file): a page with thirty sentences reads the file once


def _prefs(path) -> dict:
    try:
        at = path.stat().st_mtime_ns
        hit = _cache.get(str(path))
        if hit and hit[0] == at:
            return hit[1]
        data = json.loads(path.read_text(encoding="utf-8"))
        _cache[str(path)] = (at, data if isinstance(data, dict) else {})
        return _cache[str(path)][1]
    except (OSError, ValueError):
        return {}


def reader(cfg: sys_config.Config | None = None) -> str:
    """"it" or "en": the language chosen by the person `cfg` belongs to (default: the request's user)."""
    if cfg is None:
        if sys_config._cached is None:                # no configuration loaded (a pure function in a script or a
            return "it"                               # test): never load one just to choose a word
        cfg = sys_config.get()
    try:
        base = getattr(cfg, "base", None) or cfg
        mine = _prefs(base.path("AURORA_STATUS_DIR") / "ui_prefs.json").get(getattr(cfg, "user", None) or "", {})
        lang = mine.get("lang", "") if isinstance(mine, dict) else ""
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        lang = ""
    return "en" if str(lang or cfg["AURORA_LANG_DEFAULT"]).startswith("en") else "it"


def say(it: str, en: str, cfg: sys_config.Config | None = None) -> str:
    """The sentence in the reader's language."""
    return en if reader(cfg) == "en" else it

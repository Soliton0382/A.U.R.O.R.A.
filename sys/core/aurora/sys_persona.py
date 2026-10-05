# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Who the assistant is for each user (owner, 2026-10-05): her name, her character, her gender — chosen at install and
in each user's settings; the owner's Aurora stays as she is.

prompts/persona/base.md holds what every character shares (honesty about the vault, the logs, acting); a character
(prompts/persona/<id>.md) is the "who you are" paragraph: aurora (the many-souled scientist), philosopher, empathic,
practical. %NAME% is AURORA_ASSISTANT_NAME; {feminine|masculine} words follow AURORA_ASSISTANT_GENDER; %OWNER% stays
for sys_config.personal, which every model client applies (before the masking, C132).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import sys_config

DIR = Path(__file__).resolve().parents[1] / "prompts" / "persona"
CHARACTERS = ("aurora", "philosopher", "empathic", "practical")
GENDER = re.compile(r"\{([^{}|]*)\|([^{}|]*)\}")


def name(cfg: sys_config.Config | None = None) -> str:
    return str((cfg or sys_config.get())["AURORA_ASSISTANT_NAME"] or "Aurora").strip()[:40] or "Aurora"


def identity(cfg: sys_config.Config | None = None) -> str:
    cfg = cfg or sys_config.get()
    who = str(cfg["AURORA_PERSONALITY"])
    who = who if who in CHARACTERS else "aurora"
    text = (DIR / "base.md").read_text(encoding="utf-8").replace("{CHARACTER}", (DIR / f"{who}.md").read_text(encoding="utf-8").strip())
    male = str(cfg["AURORA_ASSISTANT_GENDER"]) == "male"
    text = GENDER.sub(lambda m: m.group(2) if male else m.group(1), text)
    return text.replace("%NAME%", name(cfg))

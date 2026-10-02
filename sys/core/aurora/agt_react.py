# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Reacting at once to a failure the owner met: a request of his that failed is diagnosed now, not at the next daily
self-review.

When a run the owner started fails (a chat request, an action he approved, a routine of his), `should_react` decides
whether an immediate repair runs: once per kind of error every REPEAT_H hours, at most PER_DAY a day (a failure that
repeats never turns into a loop of repairs), never for a repair itself. The repair is an ordinary agent run (agt_loop):
it reads the logs and the code; a defect of the code is fixed in a sandbox, tested and proposed (the owner approves, as
for every change); a cause outside the code (a setting, an account, a credit, a permission) is explained in a few
lines, with what the owner must do. Its report becomes a reflection and a notification.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import sys_config

OWNER_ORIGINS = {"webui", "openai", "approval", "routine"}
REPEAT_H, PER_DAY = 6, 6
GOAL = ("Riparazione immediata: una richiesta del proprietario è fallita pochi istanti fa (dettagli nel CONTEXT). "
        "Trova la causa: leggi i log del componente e dell'orario indicati e il codice coinvolto. "
        "Se è un difetto del codice di Aurora: correggilo in una sandbox, esegui i test e proponi la modifica "
        "(aspetterà l'approvazione del proprietario). Se la causa è fuori dal codice (un'impostazione, un account "
        "esterno non collegato, un credito esaurito, un permesso mancante, un servizio esterno giù): non toccare il "
        "codice e spiega in poche righe cosa deve fare il proprietario. Parti dall'errore e dal contesto: bastano di "
        "solito poche letture (al massimo 15 chiamate). Finisci con un resoconto breve in italiano.")


def signature(error: str) -> str:
    """The kind of an error, without the parts that change each time (ids, numbers, times, paths)."""
    s = re.sub(r"[0-9a-f]{8,}|\d+", "#", str(error).lower())
    return re.sub(r"\s+", " ", s)[:160]


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "react.json"


def should_react(cfg: sys_config.Config, origin: str, error: str, now: float | None = None) -> bool:
    """Decide, and record the decision (the file is the memory of what was already looked at)."""
    if origin not in OWNER_ORIGINS or not str(error).strip():
        return False
    now = now or time.time()
    f = _file(cfg)
    try:
        seen = json.loads(f.read_text()) if f.exists() else {}
    except ValueError:
        seen = {}
    seen = {k: v for k, v in seen.items() if now - v < 86400}
    sig = signature(error)
    if now - seen.get(sig, 0) < REPEAT_H * 3600 or len(seen) >= PER_DAY:
        return False
    seen[sig] = now
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen))
    tmp.replace(f)
    return True


def context(cfg: sys_config.Config, origin: str, title: str, error: str, run_id: str) -> str:
    """What the repair needs to start from: what failed, when, the warnings and errors of the last minutes."""
    from . import sys_logread
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"FAILED: {title}", f"ORIGIN: {origin} (run {run_id})", f"TIME: {stamp}", f"ERROR: {str(error)[:1500]}",
             "", "WARNINGS AND ERRORS OF THE LAST MINUTES (api):"]
    lines += sys_logread.tail("api", 40, "WARNING", cfg)[-25:]
    plugins = sorted(p.parent.name for p in cfg.path("AURORA_PLUGINS_DIR").glob("*/plugin.json"))
    lines += ["", f"PLUGINS INSTALLED: {', '.join(plugins)}"]
    return "\n".join(lines)

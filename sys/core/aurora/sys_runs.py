# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The events of a run (api/core.start_run), kept apart so that they can be tested without a configuration.

Only the run's own end ends it (C166, 6 October 2026): a pipeline working inside a run — the abstention before a search
Aurora does by herself, the answer before a recheck — sends its own "run.end", which the chat took for the end of
everything; those are held, and the run sends one "run.end" when it is really over.
"""
from __future__ import annotations

import time


def emit(run: dict, event: str, payload: dict) -> None:
    if event == "run.end":
        return
    with run["cond"]:
        run["events"].append({"seq": len(run["events"]) + 1, "ts": time.time(), "event": event, "payload": payload})
        run["cond"].notify_all()


def end(run: dict) -> None:
    with run["cond"]:
        run["events"].append({"seq": len(run["events"]) + 1, "ts": time.time(), "event": "run.end",
                              "payload": {"seconds": round(time.time() - run["started"], 1)}})
        run["done"] = True
        run["cond"].notify_all()

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Whose work this is: the user of the request being served (multi-user, U3), carried by a context variable.

The API's authentication sets it; `sys_config.get()` then answers with that user's configuration (their settings,
their folders), so every module, also one that does not receive a configuration, works for the right user; the
trace records it, so a purge can remove a user's lines. A thread started for a request carries it with `start`.
Background work (aurora-rem, the harvester) has none: it is the admin's.
"""
from __future__ import annotations

import contextvars
import threading

CURRENT: contextvars.ContextVar[str | None] = contextvars.ContextVar("aurora_user", default=None)


def user() -> str | None:
    return CURRENT.get()


def start(target, *args, name: str | None = None) -> threading.Thread:
    """A daemon thread that keeps the user (and every context variable) of the code that starts it."""
    ctx = contextvars.copy_context()
    t = threading.Thread(target=ctx.run, args=(target, *args), name=name, daemon=True)
    t.start()
    return t


class acting_as:
    """`with acting_as(name):` — work done for `name` (a routine of theirs, their nightly dreams)."""

    def __init__(self, name: str | None):
        self.name, self._token = name, None

    def __enter__(self):
        self._token = CURRENT.set(self.name)
        return self

    def __exit__(self, *exc):
        CURRENT.reset(self._token)
        return False

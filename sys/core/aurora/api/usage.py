# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📊 The usage page (sys_usage): counts and durations of questions, agent runs, model and tool calls, per day and
per user. The admin sees everyone's and Aurora's own work (user="" alone: Aurora's; a name: that user's); a user
only their own, whatever they ask."""
from __future__ import annotations

from aurora import sys_usage
from fastapi import APIRouter, Depends

from .core import BASE, _admin, auth, me

router = APIRouter()


@router.get("/v1/aurora/usage", dependencies=[Depends(auth)])
def usage(days: int = 7, user: str | None = None) -> dict:
    who, admin = me(), _admin()
    everyone = admin is None or who == admin
    only = ({user} if user is not None else None) if everyone else {who or ""}
    names = sorted(sys_usage.names(BASE, days)) if everyone else [who or ""]
    return {**sys_usage.report(BASE, days, only), "everyone": everyone, "admin": admin, "names": names}

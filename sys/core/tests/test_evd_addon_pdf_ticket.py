# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
# C726: in the Android app Evidentia's 📄 PDF did nothing (a blob: address
# the app's download manager cannot take): the PDF is handed over once, by a short-lived address of Aurora's own.
from __future__ import annotations
import importlib

import pytest

from aurora import sys_addons


def _api(cfg, monkeypatch):
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)   # api.core reads the config at import
    for name in ("oai", "runs"):                        # the app's own import order (svc_api)
        importlib.import_module(f"aurora.api.{name}")
    sys_addons.module("evidentia")                    # the add-on's package, as Aurora loads it
    api_evidentia = importlib.import_module("aurora_addon_evidentia.api_evidentia")
    return api_evidentia


def test_a_ticket_gives_the_pdf_once_and_then_nothing(cfg, monkeypatch):
    from fastapi import HTTPException
    A = _api(cfg, monkeypatch)
    tok = A._ticket("Caso inventato", b"%PDF-1.4 invented")
    r = A.pdf_ticket(tok)
    assert r.body == b"%PDF-1.4 invented" and r.media_type == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="Caso inventato.pdf"'
    with pytest.raises(HTTPException):
        A.pdf_ticket(tok)                                   # once only
    with pytest.raises(HTTPException):
        A.pdf_ticket("../../etc")


def test_old_tickets_expire_and_few_are_kept(cfg, monkeypatch):
    import time
    from fastapi import HTTPException
    A = _api(cfg, monkeypatch)
    A._TICKETS.clear()
    toks = [A._ticket(f"c{i}", b"x") for i in range(A.TICKETS_MAX + 3)]
    assert len(A._TICKETS) == A.TICKETS_MAX and toks[0] not in A._TICKETS
    late = A._ticket("tardi", b"y")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + A.TICKET_S + 1)
    with pytest.raises(HTTPException):
        A.pdf_ticket(late)

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C512: a network denied by mistake is taken back by the owner — off the list, its ways out legitimate."""
import asyncio
import importlib
import sys

import pytest

from aurora import sec_egress as E, sec_egress_watch as W, sys_config


def test_remove_deny_keeps_the_others():
    class C(dict):
        def __getitem__(self, k): return dict.get(self, k)
    cfg = C(AURORA_EGRESS_DENY_ASNS=["45102", "48851"])
    assert E.remove_deny(cfg, 48851) == ["45102"] and E.remove_deny(cfg, 1) == ["45102", "48851"]


def test_the_route_takes_a_network_back(cfg, monkeypatch):
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "security"):
        importlib.import_module(f"aurora.api.{name}")
    from aurora.api import security
    from fastapi import HTTPException
    cfg.values["AURORA_EGRESS_DENY_ASNS"] = ["45102", "48851"]
    W.decide(cfg, "aurora-api.service", "AS48851", "denied")
    written = {}
    monkeypatch.setattr(sys_config, "write_env", lambda path, kv: written.update(kv))
    monkeypatch.setattr(E, "refresh", lambda c, f=None, force=False: {"prefixes": ["1.2.3.0/24"]})

    class Req:
        def __init__(self, body): self.body = body
        async def json(self): return self.body
    out = asyncio.run(security.egress_allow(Req({"asn": "AS48851"})))
    assert out["asns"] == ["45102"] and written == {"AURORA_EGRESS_DENY_ASNS": "45102"}
    assert W.decisions(cfg)["aurora-api.service"]["AS48851"] == "legit"
    with pytest.raises(HTTPException) as e:                       # not on the list: said, nothing written
        asyncio.run(security.egress_allow(Req({"asn": 48851})))
    assert e.value.status_code == 404

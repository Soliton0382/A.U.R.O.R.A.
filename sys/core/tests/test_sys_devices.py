# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json
import stat

from aurora.sys_devices import Devices


def test_register_check_revoke(cfg):
    dev = Devices(cfg)
    token, rec = dev.register("Android · Chrome", "UA")
    assert "token_sha256" not in rec and dev.check(token)["id"] == rec["id"]
    assert dev.check("wrong") is None and dev.check("") is None
    raw = dev.file.read_text()
    assert token not in raw and json.loads(raw)[0]["token_sha256"]           # only the hash on disk
    assert stat.S_IMODE(dev.file.stat().st_mode) == 0o600
    assert [d["id"] for d in dev.list()] == [rec["id"]]
    assert dev.revoke(rec["id"]) and dev.check(token) is None and not dev.revoke(rec["id"])

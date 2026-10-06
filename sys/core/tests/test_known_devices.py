# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The sentinel knows the owner's devices (owner, 2026-10-06: 117 of 118 incidents came from them, 15 distinct)."""
from aurora import sec_incidents as S


def test_a_known_device_is_not_an_intruder_and_a_repeat_is_counted(cfg):
    base = {"kind": "rule:scanning_firewall_rules", "source": "192.0.2.21", "count": 40, "internal": True}
    assert S.severity(base) in ("medium", "high")                         # an unknown host inside: it matters
    assert S.severity({**base, "known": "i7_8700K"}) == "low"
    assert S.severity({"kind": "ips_alert", "source": "192.0.2.30", "internal": True, "known": "Poco-x8"}) == "medium"
    assert S.severity({"kind": "ips_alert", "source": "192.0.2.30", "internal": True}) == "high"
    inc = S.Incidents(cfg)
    first = inc.add({**base, "known": "i7_8700K"})
    again = inc.add({**base, "count": 10, "known": "i7_8700K"})
    assert again.get("merged") and again["id"] == first["id"]
    kept = inc.list("open")
    assert len(kept) == 1 and kept[0]["repeats"] == 1 and kept[0]["count"] == 50
    other = inc.add({**base, "source": "192.0.2.22"})
    assert not other.get("merged") and len(inc.list("open")) == 2

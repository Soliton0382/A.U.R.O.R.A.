# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import pytest

from aurora import sys_consoles


def test_add_change_delete_and_only_web_addresses(cfg):
    a = sys_consoles.put(cfg, {"name": "Firewall", "url": "https://10.0.0.1:4444", "group": "Rete", "icon": "🔥"})
    b = sys_consoles.put(cfg, {"name": "NAS", "url": "10.0.0.9:5443"})                  # no scheme: https
    assert b["url"] == "https://10.0.0.9:5443" and [x["name"] for x in sys_consoles.load(cfg)] == ["Firewall", "NAS"]
    sys_consoles.put(cfg, {"name": "NAS 2", "url": "http://10.0.0.9:8181"}, b["id"])
    assert sys_consoles.load(cfg)[1]["name"] == "NAS 2" and sys_consoles.delete(cfg, a["id"])
    assert [x["name"] for x in sys_consoles.load(cfg)] == ["NAS 2"] and not sys_consoles.delete(cfg, a["id"])
    for bad in ({"name": "x", "url": "javascript:alert(1)"}, {"name": "x", "url": "file:///etc/passwd"}, {"name": "", "url": "https://a"}):
        with pytest.raises(ValueError):
            sys_consoles.put(cfg, bad)
    with pytest.raises(KeyError):
        sys_consoles.put(cfg, {"name": "y", "url": "https://b"}, "nope")

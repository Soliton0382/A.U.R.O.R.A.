# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C584: the baseline tells a device's novelties at a person's pace — five an hour one by one, the rest in one burst
incident — and follows a bounded number of devices."""
from aurora import sec_baseline as B


def _line(port, mac="AA:BB:CC:00:00:01", ip="10.0.0.9"):
    return {"log_type": "Firewall", "src_zone": "LAN", "src_mac": mac, "src_ip": ip, "dst_port": str(port),
            "dst_country": "", "app_name": "", "bytes_sent": 0}


def test_a_device_trying_many_ports_is_one_burst_after_five(cfg):
    b = B.Baseline(cfg, days=0)
    b.state["since"] = 0
    b.feed(_line(22), now=1000.0)                                     # the device is known
    b.state["devices"]["AA:BB:CC:00:00:01"]["first"] = 0
    b.paced.clear()
    b.all.clear()
    out = []
    for p in range(10000, 10200):                                     # 200 new ports in a minute (as measured)
        out += b.feed(_line(p), now=1000.0 + (p - 10000) * 0.3)
    kinds = [o["kind"] for o in out]
    assert kinds.count("behaviour:new_port") == B.PER_DEVICE
    assert set(kinds[B.PER_DEVICE:]) == {"behaviour:burst"}           # one kind and source: merged into one incident
    assert out[-1]["detail"]["why"].startswith(f"{200 - B.PER_DEVICE} ")
    assert len(b.state["devices"]["AA:BB:CC:00:00:01"]["ports"]) == 201   # still learnt


def test_no_device_beyond_the_ceiling_is_followed(cfg, monkeypatch):
    monkeypatch.setattr(B, "MAX_DEVICES", 3)
    b = B.Baseline(cfg, days=0)
    for i in range(6):
        b.feed(_line(443, mac=f"AA:BB:CC:00:00:{i:02d}"), now=1000.0)
    assert len(b.state["devices"]) == 3

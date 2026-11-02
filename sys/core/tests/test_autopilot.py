# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🤖 Security at 🚀: what she decides by herself from the owner's verdicts, and what stays loud whatever the history."""
import time

from aurora import sec_autopilot as A


def _inc(kind="behaviour:new_port", verdict=None, known="Telefono", internal=True, **kw):
    return {"id": kw.pop("id", "x"), "kind": kind, "internal": internal, "known": known, "source": "192.0.2.20", "samples": [],
            "detail": {"title": "Nuova porta: 40000"}, "severity": "medium", "verdict": verdict, "verdict_at": time.time(), **kw}


def _history(fa, right=0, kind="behaviour:new_port"):
    return [_inc(kind, "false_alarm") for _ in range(fa)] + [_inc(kind, "right") for _ in range(right)]


def test_a_known_device_s_alert_of_a_kind_always_judged_false_needs_nobody():
    assert A.judged_false(_inc(), _history(A.MIN_JUDGED)) == "behaviour:new_port: 10 of 10 judged not right"
    assert A.judged_false(_inc(), _history(A.MIN_JUDGED - 1)) is None             # too few verdicts yet
    assert A.judged_false(_inc(), _history(7, 3)) is None                         # 30 % right: the owner's
    assert A.judged_false(_inc(), _history(8, 2))                                 # 20 %: at the limit


def test_what_stays_loud_whatever_the_history():
    many = _history(50) + _history(50, kind="behaviour:new_device") + _history(50, kind="honeypot")
    assert A.judged_false(_inc(known=None), many) is None                         # an unknown device
    assert A.judged_false(_inc(known="Telefono (di solito 192.0.2.5)"), many) is None   # not at its own address
    assert A.judged_false(_inc("behaviour:new_device"), many) is None
    assert A.judged_false(_inc("honeypot"), many) is None
    assert A.judged_false(_inc(severity="high"), many) is None
    assert A.judged_false(_inc(destination_lists=["x"], kind="ips_alert"), many + _history(50, kind="ips_alert")) is None
    assert A.judged_false(_inc(internal=False), many) is None


def test_a_kind_learnt_only_from_the_verdicts_on_known_devices_in_the_window():
    old = [_inc(verdict="false_alarm", verdict_at=time.time() - 40 * 86400) for _ in range(20)]
    assert A.judged_false(_inc(), old) is None
    unknown = [_inc(verdict="false_alarm", known=None) for _ in range(20)]
    assert A.judged_false(_inc(), unknown) is None


def test_the_digest_says_each_decision_once_and_what_was_left(cfg):
    now = time.time()
    items = [_inc(id="a", settled="blocked", settled_at=now), _inc(id="b", settled="quiet", settled_at=now),
             _inc(id="c", settled="behaviour:new_port: 10 of 10 judged not right", settled_at=now),
             _inc(id="d", status="open", received_ts=now), _inc(id="e", settled="blocked", settled_at=now - 3 * 86400)]
    d = A.digest(cfg, items, now + 1)
    assert (d["blocked"], d["quiet"], d["judged"], d["left"]) == (1, 1, 1, 1) and sorted(d["ids"]) == ["a", "b", "c"]
    assert "1 attacchi bloccati" in A.said(d) and "2 allarmi di casa chiusi" in A.said(d) and "1 lasciati a te" in A.said(d)
    assert A.digest(cfg, items, now + 2) is None                                  # said once

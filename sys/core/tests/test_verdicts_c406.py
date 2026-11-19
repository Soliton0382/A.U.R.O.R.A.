# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C406: the owner's verdicts outlive the incidents they were given on (sec_verdicts), a «false alarm» answer never
hides a serious alert nor another kind's, and a «right» raises the next alert of the same pattern. Invented devices."""
import time

from aurora import sec_autopilot as A
from aurora import sec_quiet as Q
from aurora import sec_verdicts as V

DNS = 'log_type="ATP" dst_port=53 src_ip="192.0.2.20"'
WEB = 'log_type="ATP" dst_port=443 src_ip="192.0.2.20"'
PHONE, TV = "02:00:00:00:00:01", "02:00:00:00:00:02"


def _inc(n, kind="behaviour:new_port", verdict=None, mac=PHONE, sample="", severity="medium", at=None, **kw):
    t = time.time() if at is None else at
    return {"id": f"i{n}", "kind": kind, "internal": True, "known": "Telefono", "source": "192.0.2.20",
            "samples": [sample] if sample else [], "detail": {"title": "Nuova porta: 40000", "mac": mac},
            "severity": severity, "received_ts": t, "verdict": verdict, "verdict_at": t if verdict else None, **kw}


def test_the_verdicts_stay_when_their_incidents_leave_the_file(cfg):
    judged = [_inc(n, verdict="false_alarm") for n in range(A.MIN_JUDGED)]
    V.keep(cfg, judged)                                         # seen once, as the API sees them
    fresh = [_inc(100 + n) for n in range(5)]                   # the file has rolled over: only new incidents
    items = V.merged(cfg, fresh)
    assert len(items) == 5 + A.MIN_JUDGED
    assert A.judged_false(_inc(999), items)                     # her judgement holds on the owner's old verdicts
    assert A.judged_false(_inc(999), fresh) is None             # without the ledger it was lost (9–13 Nov: 62, after: 0)
    p = Q.pattern(judged[0])
    assert Q.tally(items)[p]["false_alarm"] == A.MIN_JUDGED     # the patterns count them too


def test_a_verdict_changed_is_brought_up_to_date_and_old_ones_go(cfg):
    V.keep(cfg, [_inc(1, verdict="false_alarm")])
    V.keep(cfg, [_inc(1, verdict="right")])
    assert [r["verdict"] for r in V.load(cfg)] == ["right"]
    old = time.time() - (V.KEEP_DAYS + 1) * 86400
    rows = V.keep(cfg, [_inc(2, verdict="false_alarm", at=old)])
    assert [r["id"] for r in rows] == ["i1"]


def test_a_quiet_pattern_never_hides_a_serious_alert_nor_another_device_or_kind(cfg):
    items = [_inc(n, "ips_alert", "false_alarm", sample=DNS) for n in range(Q.PROPOSE_FA)]
    p = Q.pattern(items[0])
    Q.answer(cfg, p, "quiet", Q.tally(items)[p])
    assert Q.is_quiet(cfg, _inc(10, "ips_alert", sample=DNS)) == p
    assert Q.is_quiet(cfg, _inc(11, "ips_alert", sample=DNS, severity="high")) is None      # serious: loud
    assert Q.is_quiet(cfg, _inc(12, "ips_alert", sample=DNS, severity="critical")) is None
    assert Q.is_quiet(cfg, _inc(13, "ips_alert", sample=WEB)) is None                       # another port
    assert Q.is_quiet(cfg, _inc(14, "ips_alert", sample=DNS, mac=TV)) is None               # another device
    assert Q.is_quiet(cfg, _inc(15, "behaviour:new_country", mac=PHONE)) is None            # another kind


def test_her_judgement_is_per_signature_not_per_kind():
    dns = [_inc(n, "ips_alert", "false_alarm", sample=DNS) for n in range(A.MIN_JUDGED)]
    assert A.judged_false(_inc(50, "ips_alert", sample=DNS), dns)
    assert A.judged_false(_inc(51, "ips_alert", sample=WEB), dns) is None   # verdicts on port 53 say nothing of 443
    assert A.judged_false(_inc(52, "ips_alert", sample=DNS, severity="high"), dns) is None


def test_a_right_raises_the_next_alert_of_that_pattern_only():
    right = [_inc(1, "deny_burst", "right", severity="low", internal=False, known=None, source="203.0.113.9",
                  detail={})]
    again = _inc(2, "deny_burst", severity="low", internal=False, known=None, source="203.0.113.9", detail={})
    assert Q.raised(again, right) == "medium"
    assert Q.raised({**again, "severity": "medium"}, right) == "high"
    assert Q.raised({**again, "severity": "high"}, right) is None                    # already at the top
    assert Q.raised({**again, "source": "203.0.113.10"}, right) is None              # another address
    assert Q.raised({**again, "kind": "behaviour:burst"}, right) is None             # another kind
    assert Q.raised(again, [_inc(1, "deny_burst", "false_alarm", severity="low", internal=False, known=None,
                                 source="203.0.113.9", detail={})]) is None
    old = time.time() - (Q.WINDOW_DAYS + 1) * 86400
    assert Q.raised(again, [{**right[0], "verdict_at": old}]) is None                 # the window, as for false alarms
    assert Q.raised(right[0], right) is None                                         # not by its own verdict


def test_a_right_counts_after_its_incident_left_the_file(cfg):
    right = _inc(1, "ips_alert", "right", sample=DNS)
    V.keep(cfg, [right])
    assert Q.raised(_inc(2, "ips_alert", sample=DNS), V.merged(cfg, [])) == "high"

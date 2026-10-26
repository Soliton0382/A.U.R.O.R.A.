# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's verdicts put to use (sec_quiet; owner, 2026-10-27): a kind of alert judged false again and again is
proposed for quiet once; a quiet kind is woken by a «right»; what is never quieted stays loud."""
import time

from aurora import sec_quiet as Q

IN_DNS = 'log_type="ATP" threatfeed="GreyNoise" dst_port=53 src_ip="192.0.2.20"'
OUT_PLEX = 'log_type="ATP" threatfeed="GreyNoise" dst_port=32400 src_ip="198.51.100.7"'


def _inc(kind, verdict=None, internal=True, sample="", title="", **kw):
    return {"kind": kind, "internal": internal, "samples": [sample] if sample else [],
            "detail": {"title": title}, "verdict": verdict, "verdict_at": time.time(), **kw}


def test_a_pattern_is_what_the_incident_is_without_who():
    assert Q.pattern(_inc("ips_alert", sample=IN_DNS)) == "ips_alert|in|53"
    assert Q.pattern(_inc("ips_alert", internal=False, sample=OUT_PLEX)) == "ips_alert|out|32400"
    assert Q.pattern(_inc("behaviour:new_port", title="Nuova porta: 35056")) == "behaviour:new_port|high"
    assert Q.pattern(_inc("behaviour:new_port", title="Nuova porta: 22")) == "behaviour:new_port|low"
    assert Q.pattern(_inc("behaviour:new_country", source="192.0.2.30")) == "behaviour:new_country"
    # never quieted: a decoy, a known attacker, a device reaching a listed address
    assert Q.pattern(_inc("honeypot")) is None
    assert Q.pattern(_inc("ips_alert", internal=False, sample=OUT_PLEX, intel_lists=["x"])) is None
    assert Q.pattern(_inc("ips_alert", sample=IN_DNS, destination_lists=["x"])) is None


def test_five_false_alarms_and_few_right_make_one_proposal(cfg):
    items = [_inc("ips_alert", "false_alarm", sample=IN_DNS) for _ in range(4)]
    assert Q.proposals(cfg, items) == []
    items.append(_inc("ips_alert", "false_alarm", sample=IN_DNS))
    [p] = Q.proposals(cfg, items)
    assert (p["pattern"], p["false_alarm"], p["right"]) == ("ips_alert|in|53", 5, 0) and "53" in p["label"]
    assert Q.after_verdict(cfg, items, items[-1])["propose"]["pattern"] == "ips_alert|in|53"
    assert Q.after_verdict(cfg, items, items[-1]) is None                  # proposed once, not at every verdict
    # mostly right: never proposed (the Internet's scanners on an open port, M261: 64 right of 68)
    plex = [_inc("ips_alert", "right", internal=False, sample=OUT_PLEX) for _ in range(4)] + \
           [_inc("ips_alert", "false_alarm", internal=False, sample=OUT_PLEX) for _ in range(5)]
    assert all(x["pattern"] != "ips_alert|out|32400" for x in Q.proposals(cfg, plex))


def test_quiet_until_judged_right_and_old_verdicts_do_not_count(cfg):
    items = [_inc("behaviour:new_country", "false_alarm") for _ in range(6)]
    Q.answer(cfg, "behaviour:new_country", "quiet", Q.tally(items)["behaviour:new_country"])
    assert Q.is_quiet(cfg, _inc("behaviour:new_country")) == "behaviour:new_country"
    assert Q.quiet_list(cfg)[0]["fa"] == 6 and Q.proposals(cfg, items) == []
    woke = Q.after_verdict(cfg, items, _inc("behaviour:new_country", "right"))
    assert woke["woke"] == "behaviour:new_country" and not Q.is_quiet(cfg, _inc("behaviour:new_country"))
    old = [_inc("rule:invalid_traffic_spike", "false_alarm", verdict_at=time.time() - 40 * 86400) for _ in range(9)]
    assert Q.proposals(cfg, old) == []                                     # past WINDOW_DAYS
    Q.answer(cfg, "rule:invalid_traffic_spike", "declined")
    recent = [_inc("rule:invalid_traffic_spike", "false_alarm") for _ in range(9)]
    assert Q.proposals(cfg, recent) == []                                  # the owner said no: not asked again

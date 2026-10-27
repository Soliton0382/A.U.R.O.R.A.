# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's verdicts put to use (sec_quiet; owner, 2026-10-27): a kind of alert judged false again and again on one
device is proposed for quiet once — that device only (C407); a quiet pattern is woken by a «right»; what is never
quieted stays loud."""
import time

from aurora import sec_quiet as Q

IN_DNS = 'log_type="ATP" threatfeed="GreyNoise" dst_port=53 src_ip="192.0.2.20"'
OUT_PLEX = 'log_type="ATP" threatfeed="GreyNoise" dst_port=32400 src_ip="198.51.100.7"'
PHONE, TV = "02:00:00:00:00:01", "02:00:00:00:00:02"


def _inc(kind, verdict=None, internal=True, sample="", title="", mac=PHONE, **kw):
    return {"kind": kind, "internal": internal, "samples": [sample] if sample else [], "source": "192.0.2.20",
            "detail": {"title": title, "mac": mac}, "verdict": verdict, "verdict_at": time.time(), **kw}


def test_a_pattern_is_what_the_incident_is_and_on_which_device():
    assert Q.pattern(_inc("ips_alert", sample=IN_DNS)) == f"ips_alert|in|53|{PHONE}"
    assert Q.pattern(_inc("ips_alert", sample=IN_DNS, mac=TV)) == f"ips_alert|in|53|{TV}"
    assert Q.pattern(_inc("ips_alert", internal=False, sample=OUT_PLEX, mac="")) == "ips_alert|out|32400|192.0.2.20"
    assert Q.pattern(_inc("behaviour:new_port", title="Nuova porta: 35056")) == f"behaviour:new_port|high|{PHONE}"
    assert Q.pattern(_inc("behaviour:new_port", title="Nuova porta: 22")) == f"behaviour:new_port|low|{PHONE}"
    assert Q.label(f"ips_alert|in|53|{PHONE}", "it", "Telefono") == "allarme IPS da Telefono verso la porta 53"
    # never quieted: a decoy, a known attacker, a device reaching a listed address
    assert Q.pattern(_inc("honeypot")) is None
    assert Q.pattern(_inc("ips_alert", internal=False, sample=OUT_PLEX, intel_lists=["x"])) is None
    assert Q.pattern(_inc("ips_alert", sample=IN_DNS, destination_lists=["x"])) is None


def test_false_alarms_on_one_device_quiet_that_device_only(cfg):
    items = [_inc("ips_alert", "false_alarm", sample=IN_DNS, known="Telefono") for _ in range(Q.PROPOSE_FA - 1)]
    assert Q.proposals(cfg, items) == []
    items.append(_inc("ips_alert", "false_alarm", sample=IN_DNS, known="Telefono"))
    [p] = Q.proposals(cfg, items)
    assert (p["pattern"], p["false_alarm"], p["right"], p["name"]) == (f"ips_alert|in|53|{PHONE}", Q.PROPOSE_FA, 0, "Telefono")
    assert Q.after_verdict(cfg, items, items[-1])["propose"]["pattern"] == p["pattern"]
    assert Q.after_verdict(cfg, items, items[-1]) is None                  # proposed once, not at every verdict
    Q.answer(cfg, p["pattern"], "quiet", Q.tally(items)[p["pattern"]], p["name"])
    assert Q.is_quiet(cfg, _inc("ips_alert", sample=IN_DNS))
    assert not Q.is_quiet(cfg, _inc("ips_alert", sample=IN_DNS, mac=TV))     # another device: still loud (C407)
    # mostly right: never proposed (the Internet's scanners on an open port, M261: 64 right of 68)
    plex = [_inc("ips_alert", "right", internal=False, sample=OUT_PLEX) for _ in range(4)] + \
           [_inc("ips_alert", "false_alarm", internal=False, sample=OUT_PLEX) for _ in range(5)]
    assert all("32400" not in x["pattern"] for x in Q.proposals(cfg, plex))


def test_quiet_until_judged_right_and_old_verdicts_do_not_count(cfg):
    items = [_inc("behaviour:new_country", "false_alarm") for _ in range(6)]
    p = f"behaviour:new_country|{PHONE}"
    Q.answer(cfg, p, "quiet", Q.tally(items)[p])
    assert Q.is_quiet(cfg, _inc("behaviour:new_country")) == p
    assert Q.quiet_list(cfg)[0]["fa"] == 6 and Q.proposals(cfg, items) == []
    woke = Q.after_verdict(cfg, items, _inc("behaviour:new_country", "right"))
    assert woke["woke"] == p and not Q.is_quiet(cfg, _inc("behaviour:new_country"))
    old = [_inc("rule:invalid_traffic_spike", "false_alarm", verdict_at=time.time() - 40 * 86400) for _ in range(9)]
    assert Q.proposals(cfg, old) == []                                     # past WINDOW_DAYS
    Q.answer(cfg, f"rule:invalid_traffic_spike|{PHONE}", "declined")
    recent = [_inc("rule:invalid_traffic_spike", "false_alarm") for _ in range(9)]
    assert Q.proposals(cfg, recent) == []                                  # the owner said no: not asked again


def test_an_answer_given_to_a_kind_alone_is_made_again_per_device(cfg):
    """C407: «ips_alert|in|53» quieted for every device becomes the devices that meet the rule; a kind declined is
    forgotten, so its devices may be proposed."""
    Q.answer(cfg, "ips_alert|in|53", "quiet")
    Q.answer(cfg, "behaviour:new_country", "declined")
    items = [_inc("ips_alert", "false_alarm", sample=IN_DNS) for _ in range(4)] + \
            [_inc("ips_alert", "false_alarm", sample=IN_DNS, mac=TV)] + \
            [_inc("behaviour:new_country", "false_alarm", mac=TV) for _ in range(3)]
    assert Q.by_kind(cfg, items) == [f"ips_alert|in|53|{PHONE}"]
    st = Q.load(cfg)
    assert "ips_alert|in|53" not in st and "behaviour:new_country" not in st
    assert not Q.is_quiet(cfg, _inc("ips_alert", sample=IN_DNS, mac=TV))   # one false alarm only: loud
    assert [x["pattern"] for x in Q.proposals(cfg, items)] == [f"behaviour:new_country|{TV}"]
    assert Q.by_kind(cfg, items) == []                                     # once

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Any change on the firewall asked in words (owner, 2026-10-08): the local model plans, the code checks (M135)."""
import json
from types import SimpleNamespace

import pytest

from aurora import sec_fwapi, sec_fwplan, sec_fwwrite


def _rule(name, src, dst, action="Accept"):
    return {"Name": name, "Status": "Enable", "NetworkPolicy": {"Action": action, "SourceZones": {"Zone": src},
                                                                "DestinationZones": {"Zone": dst}}}


CONF = {"FirewallRule": [_rule("Aurora_Block_List", [], [], "Reject"), _rule("PassThrough", ["LAN"], ["WAN"]),
                         _rule("#Default", ["LAN"], ["WAN"])],
        "Services": [{"Name": "HTTPS"}], "Zone": [{"Name": "LAN", "Type": "LAN"}, {"Name": "WiFi", "Type": "LAN"}],
        "_errors": {}}

DROP = ("<FirewallRule><Name>{n}</Name><Position>{pos}</Position>{after}<PolicyType>Network</PolicyType><UserPolicy>"
        "<Action>Drop</Action><SourceZones><Zone>LAN</Zone></SourceZones><SourceNetworks><Network>any</Network>"
        "</SourceNetworks><DestinationZones><Zone>WAN</Zone></DestinationZones><Exclusions><Services><Service>HTTPS"
        "</Service></Services></Exclusions></UserPolicy></FirewallRule>")


class Model:
    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def complete(self, system, user, max_tokens, think=False):
        self.asked.append(user)
        return SimpleNamespace(answer=self.answers.pop(0))


def _plan(*steps, **more):
    return json.dumps({"title": "t", "why": "w", "steps": list(steps), "notes": [], **more})


@pytest.fixture
def firewall(cfg, monkeypatch):
    cfg.values.update(AURORA_FIREWALL_API_URL="https://192.0.2.1:4444", AURORA_FIREWALL_BLOCK_GROUP="Aurora-Blocklist")
    monkeypatch.setattr(sec_fwapi, "_own_addresses", lambda: {"10.0.0.5"})
    monkeypatch.setattr(sec_fwplan, "_docs", lambda cfg, request: "")
    return cfg


def test_a_shadowed_block_goes_back_to_the_model_and_the_second_plan_is_tidied(firewall):
    late = {"op": "add", "entity": "FirewallRule", "name": "Aurora_No_Out",
            "xml": DROP.format(n="Aurora_No_Out", pos="before", after="<Before><Name>#Default</Name></Before>")}
    top = {"op": "add", "entity": "FirewallRule", "name": "Aurora_No_Out", "xml": DROP.format(n="Aurora_No_Out", pos="top", after="")}
    m = Model(_plan(late), _plan(top))
    p = sec_fwplan.plan(firewall, "nega Internet tranne la 443", model=m, conf=CONF)
    assert "«PassThrough»" in m.asked[1] and "shadowed" in m.asked[1]
    st = p["steps"][0]
    assert st["name"] == "Aurora-No_Out" and "<Name>Aurora-No_Out</Name>" in st["xml"]      # renamed: a new object
    assert "<NetworkPolicy>" in st["xml"] and "any" not in st["xml"] and st["undo"].startswith("<Remove>")


def test_an_accept_from_the_internet_with_no_service_is_refused():
    xml = ("<FirewallRule><Name>Aurora-Italy</Name><PolicyType>Network</PolicyType><NetworkPolicy><Action>Accept</Action>"
           "<SourceZones><Zone>WAN</Zone></SourceZones><SourceNetworks><Network>Italy</Network></SourceNetworks>"
           "<DestinationZones><Zone>Any</Zone></DestinationZones></NetworkPolicy></FirewallRule>")
    steps, problems = sec_fwplan.check(None, [{"op": "add", "entity": "FirewallRule", "name": "Aurora-Italy", "xml": xml}], CONF)
    assert steps == [] and "opens the network" in problems[0]


@pytest.mark.parametrize("step, why", [
    ({"op": "add", "entity": "AdminSettings", "name": "Aurora-X", "xml": "<AdminSettings><Name>Aurora-X</Name></AdminSettings>"}, "not allowed"),
    ({"op": "add", "entity": "IPHost", "name": "Mine", "xml": "<IPHost><Name>Mine</Name></IPHost>"}, "must start"),
    ({"op": "remove", "entity": "FirewallRule", "name": "PassThrough", "xml": ""}, "only her own"),
    ({"op": "add", "entity": "IPHost", "name": "Aurora-X", "xml": "<IPHost><Name>Other</Name></IPHost>"}, "whose <Name>"),
    ({"op": "add", "entity": "IPHost", "name": "Aurora-X", "xml": '<!DOCTYPE a [<!ENTITY b "c">]><IPHost/>'}, "DOCTYPE"),
    ({"op": "update", "entity": "IPHost", "name": "Aurora-Nope", "xml": "<IPHost><Name>Aurora-Nope</Name></IPHost>"}, "to update"),
])
def test_what_the_code_never_lets_through(step, why):
    steps, problems = sec_fwplan.check(None, [step], CONF, reader=lambda cfg, e, n: None)
    assert steps == [] and why in problems[0]


def test_the_owner_s_rule_named_aurora_underscore_is_never_taken_for_aurora_s():
    steps = [{"op": "update", "entity": "FirewallRule", "name": "Aurora_Block_List",
              "xml": "<FirewallRule><Name>Aurora_Block_List</Name></FirewallRule>"}]
    assert sec_fwplan.renamed(steps, CONF)[0]["name"] == "Aurora_Block_List"
    out, problems = sec_fwplan.check(None, steps, CONF, reader=lambda cfg, e, n: "<FirewallRule><Name>Aurora_Block_List</Name></FirewallRule>")
    assert problems == [] and out[0]["owner_object"] and out[0]["undo"].startswith('<Set operation="update">')


def test_an_unclear_request_comes_back_as_questions_and_two_bad_plans_are_an_error(firewall):
    m = Model(json.dumps({"steps": [], "questions": ["In entrata o in uscita?"]}))
    assert sec_fwplan.plan(firewall, "blocca gli IP esteri", model=m, conf=CONF)["questions"] == ["In entrata o in uscita?"]
    with pytest.raises(sec_fwwrite.WriteError):
        sec_fwplan.plan(firewall, "blocca gli IP esteri", model=Model("not json", "still not"), conf=CONF)

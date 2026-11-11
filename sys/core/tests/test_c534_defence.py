# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C534: the defence never turns on the house — a decoy touched from inside is told, not blocked; one bad page of a
site of many authors lists that page, not the site; the owner's block outlives Aurora's own on the same address; and
taking a site off the honeypot's list is the owner's alone."""
import json
import time
from pathlib import Path

import pytest

from aurora import hom_safety, plg_contract, sec_defence, sec_detonate, sec_fwapi, sec_linkcheck, sys_ethics
from aurora.sec_incidents import Incidents
from test_sec_detonate import TRAP, Decoy

OUTSIDE = "45.33.32.156"        # a public address meant for tests (scanme.nmap.org): documentation ranges are not global


@pytest.fixture
def firewall(cfg, monkeypatch):
    calls = []
    cfg.values.update(AURORA_DEFENCE_MODE="auto", AURORA_DEFENCE_HOURS=24, AURORA_DEFENCE_MIN_SEVERITY="high",
                      AURORA_DEFENCE_MAX_PER_DAY=5, AURORA_DEFENCE_PROTECTED="",
                      AURORA_FIREWALL_API_URL="https://192.0.2.1:4444", AURORA_FIREWALL_API_USER="aurora",
                      AURORA_FIREWALL_API_PASSWORD="secret-password")
    monkeypatch.setattr(sys_ethics, "exempt", lambda cfg=None: True)
    monkeypatch.setattr(sec_fwapi, "block", lambda cfg, ip, reason="": calls.append(("block", ip)) or {"blocked": ip})
    monkeypatch.setattr(sec_fwapi, "unblock", lambda cfg, ip: calls.append(("unblock", ip)) or {"unblocked": ip})
    return calls


def test_a_decoy_touched_from_inside_is_told_never_blocked(cfg):
    store = Incidents(cfg)
    phone = store.add({"kind": "honeypot", "source": "10.0.0.25", "count": 1, "internal": True})
    assert phone["severity"] == "high"                                   # still a loud incident
    assert not sec_defence.decoy_blocks(cfg, phone)
    assert store.list()[0]["hostfw"].startswith("not blocked: an address of the local network")
    for inside in ("192.168.1.7", "172.16.0.9", "169.254.3.3", "fe80::1", "fd00::5", "not an address", ""):
        assert not sec_defence.decoy_blocks(cfg, {"kind": "honeypot", "source": inside, "internal": False}), inside
    lied = {"kind": "honeypot", "source": OUTSIDE, "internal": True}     # the report's own word is enough to hold back
    assert not sec_defence.decoy_blocks(cfg, lied)
    out = store.add({"kind": "honeypot", "source": OUTSIDE, "count": 1, "internal": False})
    assert sec_defence.decoy_blocks(cfg, out) and "hostfw" not in store.list()[0]


def test_the_api_asks_before_a_decoy_s_block():
    src = (Path(sec_defence.__file__).parent / "api" / "incidents.py").read_text(encoding="utf-8")
    assert src.count('if item["kind"] == "honeypot" and sec_defence.decoy_blocks(cfg, item):') == 1
    assert src.count("sec_hostfw.block(") == 1                            # the only block there, behind that question


def test_the_owner_s_block_replaces_her_own_and_does_not_expire_with_it(cfg, firewall, monkeypatch):
    attack = {"id": "i1", "kind": "ips_alert", "source": OUTSIDE, "severity": "high"}
    sec_defence.act(cfg, attack)                                          # hers, for 24 hours
    sec_defence.record_manual(cfg, OUTSIDE, "the owner's click", "i1")    # then the owner blocks the same address
    sec_defence.record_manual(cfg, OUTSIDE, "a second click")             # once (C174)
    now = [b for b in sec_defence._load(cfg) if not b.get("released")]
    assert len(now) == 1 and now[0]["kind"] == "manual" and not now[0]["auto"]
    assert [b["released_by"] for b in sec_defence._load(cfg) if b.get("released")] == ["replaced by the owner's block"]
    later = time.time() + 30 * 86400
    monkeypatch.setattr(time, "time", lambda: later)
    assert sec_defence.release_due(cfg) == [] and ("unblock", OUTSIDE) not in firewall
    assert sec_defence.blocked(cfg, OUTSIDE)
    sec_defence.release(cfg, OUTSIDE, "owner")                            # the owner's «undo» still lifts it
    assert firewall[-1] == ("unblock", OUTSIDE) and not sec_defence.blocked(cfg, OUTSIDE)


def test_records_made_before_the_fix_do_not_undo_the_owner_s_block(cfg, firewall):
    """What the state file may hold already: her record overdue, the owner's block on the same address beside it."""
    now = time.time()
    sec_defence._save(cfg, [
        {"ip": OUTSIDE, "at": now - 90000, "until": now - 3600, "day": "2026-01-01", "auto": True, "released": None},
        {"ip": OUTSIDE, "at": now - 80000, "until": now + 9e8, "day": "2026-01-01", "kind": "manual", "auto": False,
         "released": None},
        {"ip": "45.33.32.200", "at": now - 90000, "until": now - 3600, "day": "2026-01-01", "auto": True, "released": None}])
    assert sec_defence.release_due(cfg) == ["45.33.32.200"]               # hers alone: lifted as before
    assert firewall == [("unblock", "45.33.32.200")] and sec_defence.blocked(cfg, OUTSIDE)
    assert sec_defence.release_due(cfg) == []                             # and her overdue record is closed, once


def test_one_bad_page_of_a_shared_site_lists_that_page_only(cfg):
    bad = "https://github.com/someone/project/issues/7?tab=comments#c1"
    v = sec_detonate.guard(cfg, Decoy("call"), bad, TRAP, mode="all")
    assert v["exploded"] and "this page is listed" in sec_detonate.refusal(bad, v)
    d = sec_detonate._load(cfg)
    assert d["sites"] == {} and list(d["pages"]) == ["github.com/someone/project/issues/7?tab=comments"]
    assert sec_linkcheck.check("https://www.github.com/someone/project/issues/7?tab=comments", cfg)["blocked"]
    cfg.values["AURORA_LINKCHECK"] = False
    for fine in ("https://github.com/", "https://github.com/someone/project", "https://github.com/other/repo/issues/7",
                 "https://gist.github.com/someone/1"):
        assert sec_detonate.listed(cfg, fine) is None, fine
    again = sec_detonate.guard(cfg, Decoy("none"), "https://github.com/a/mirror", TRAP, mode="all")
    assert again["exploded"] and again["cached"]                          # the same content elsewhere: still refused
    assert sec_detonate.shared_host("en.wikipedia.org") and sec_detonate.shared_host("old.reddit.com")
    assert not sec_detonate.shared_host("someone.github.io") and not sec_detonate.shared_host("notgithub.com")


def test_a_site_of_one_author_is_still_listed_whole(cfg):
    sec_detonate.guard(cfg, Decoy("call"), "https://evil.example.org/p", TRAP, mode="all")
    assert sec_detonate.listed(cfg, "https://evil.example.org/any/other?page=1")
    assert sec_detonate._load(cfg)["pages"] == {}


def test_a_shared_site_listed_whole_before_the_fix_holds_for_its_page_only(cfg):
    f = sec_detonate._file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"verdicts": {}, "sites": {"reddit.com": {"url": "https://www.reddit.com/r/x/comments/1/",
                                                                         "why": "l'esca ha chiamato uno strumento"}}}))
    assert sec_detonate.listed(cfg, "https://reddit.com/r/x/comments/1")
    assert sec_detonate.listed(cfg, "https://www.reddit.com/r/python/") is None
    assert sec_detonate.unlist(cfg, "reddit.com") and sec_detonate.listed(cfg, "https://reddit.com/r/x/comments/1") is None


def test_unlisting_takes_a_page_by_its_link_and_is_the_owner_s_alone(cfg):
    bad = "https://en.wikipedia.org/wiki/Some_page"
    sec_detonate.guard(cfg, Decoy("call"), bad, TRAP, mode="all")
    assert not sec_detonate.unlist(cfg, "https://en.wikipedia.org/wiki/Another") and sec_detonate.listed(cfg, bad)
    assert sec_detonate.unlist(cfg, bad) and sec_detonate.listed(cfg, bad) is None
    folder = Path(sec_defence.__file__).resolve().parents[2] / "plugins" / "linkcheck"
    m = json.loads((folder / "plugin.json").read_text(encoding="utf-8"))
    assert m["owner_only"] == ["honeypot_unlist"] and plg_contract.check(m, "linkcheck") == []
    assert hom_safety.call_lowers(m, "honeypot_unlist", {"site": "evil.example.org"})   # always the owner's approval
    assert not hom_safety.call_lowers(m, "check_link", {"url": bad})

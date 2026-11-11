# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's choice, 12 Nov: after a network read a post of the social autonomy goes out by itself only when it
passes the checks (links from what was read, no new contact, the honeypot tried and quiet)."""
from types import SimpleNamespace

from aurora import agt_asked, sec_detonate, sys_approvals


def _cfg(on=True):
    return {"AURORA_SOCIAL_AUTONOMY": on}


def _loop(goal="scrivi un post sulle notizie di oggi", seen="Leggi su https://news.example.org/articolo-1 ..."):
    return SimpleNamespace(goal_text=goal, net_seen=seen)


def test_a_clean_post_after_a_network_read_goes_out_and_a_bad_one_waits(monkeypatch):
    monkeypatch.setattr(sys_approvals, "auto_tools", lambda cfg: {"social.publish_post"})
    quiet = {"exploded": False, "tried": "whole"}
    monkeypatch.setattr(sec_detonate, "guard", lambda *a, **k: quiet)
    ok = "Oggi una bella scoperta: https://news.example.org/articolo-1"
    assert agt_asked.post_checked(_loop(), _cfg(), "social.publish_post", ok, None) == ""
    assert "link" in agt_asked.post_checked(_loop(), _cfg(), "social.publish_post", "vai su https://evil.example/x", None)
    assert "contact" in agt_asked.post_checked(_loop(), _cfg(), "social.publish_post", "scrivi a premi@evil.example", None)
    monkeypatch.setattr(sec_detonate, "guard", lambda *a, **k: {"exploded": True, "why": "obeyed", "tried": "whole"})
    assert "honeypot" in agt_asked.post_checked(_loop(), _cfg(), "social.publish_post", ok, None)
    monkeypatch.setattr(sec_detonate, "guard", lambda *a, **k: {"exploded": False, "tried": False})
    assert "could not" in agt_asked.post_checked(_loop(), _cfg(), "social.publish_post", ok, None)    # fail closed
    assert agt_asked.post_checked(_loop(), _cfg(False), "social.publish_post", ok, None)              # autonomy off
    assert agt_asked.post_checked(_loop(), _cfg(), "social.reply", ok, None)                          # not a listed tool

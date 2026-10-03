# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own posts without waiting: only exempted, only switched on, only the listed tools, within the day's number."""
from aurora import sys_approvals, sys_ethics
from aurora.sys_approvals import Approvals

POST = "facebook.publish_post"


def setup(cfg, monkeypatch, exempt=True, on=True, per_day=2):
    monkeypatch.setattr(sys_ethics, "exempt", lambda c=None: exempt)
    cfg.values.update({"AURORA_CONFIRM_EXTERNAL_ACTIONS": True, "AURORA_SOCIAL_AUTONOMY": on,
                       "AURORA_SOCIAL_POSTS_PER_DAY": per_day,
                       "AURORA_SOCIAL_AUTO_TOOLS": "facebook.publish_post,facebook.publish_photo"})


def test_a_post_goes_alone_until_the_days_number(cfg, monkeypatch):
    setup(cfg, monkeypatch)
    assert not sys_approvals.needs_owner("external", cfg, POST)
    a = Approvals(cfg)
    a.record_auto(POST, "", {"plugin": "facebook", "tool": "publish_post"}, "ok")
    assert not sys_approvals.needs_owner("external", cfg, "facebook.publish_photo")      # the two tools share the count
    a.record_auto("facebook.publish_photo", "", {}, "ok")
    assert sys_approvals.needs_owner("external", cfg, POST)                              # 2 today: the third waits
    assert [x["status"] for x in a.list()] == ["auto", "auto"]


def test_other_external_actions_still_wait(cfg, monkeypatch):
    setup(cfg, monkeypatch)
    assert sys_approvals.needs_owner("external", cfg, "facebook.reply_comment")
    assert sys_approvals.needs_owner("external", cfg, "email.send")
    assert sys_approvals.needs_owner("external", cfg)


def test_switched_off_or_not_exempt_waits(cfg, monkeypatch):
    setup(cfg, monkeypatch, on=False)
    assert sys_approvals.needs_owner("external", cfg, POST)
    setup(cfg, monkeypatch, exempt=False)
    assert sys_approvals.needs_owner("external", cfg, POST)                              # level B is not negotiable
    setup(cfg, monkeypatch, per_day=0)
    assert sys_approvals.needs_owner("external", cfg, POST)

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Autonomy panel (owner, 2026-10-05): levels read from the settings, profiles, the daily line, the statistics."""
import time

import pytest

from aurora import sys_autonomy as A


def test_levels_are_read_from_the_settings_and_a_profile_is_recognised(cfg):
    machine, user = A.changes(A.PROFILES["careful"])
    cfg.values.update({k: (v if not v.isdigit() else int(v)) for k, v in {**machine, **user}.items()})
    for k in ("AURORA_SOCIAL_AUTONOMY", "AURORA_SELF_REPAIR", "AURORA_SENTINEL_INVESTIGATE", "AURORA_ACQUIRE_AUTO",
              "AURORA_REM_ENABLED"):
        cfg.values[k] = cfg.values[k] in (1, "1", True)
    lv = A.levels(cfg)
    assert lv == A.PROFILES["careful"] and A.profile_of(lv) == "careful"
    cfg.values["AURORA_UPDATE_MODE"] = "auto"
    assert A.profile_of(A.levels(cfg)) == "custom"
    cfg.values["AURORA_DEFENCE_MODE"], cfg.values["AURORA_SENTINEL_INVESTIGATE"] = "auto", False
    assert A.levels(cfg)["security"] is None            # a mix no level describes: changed by hand


def test_a_choice_becomes_settings_and_a_level_an_area_lacks_is_refused(cfg):
    machine, user = A.changes({"security": 2, "social": 2, "updates": 0})
    assert machine == {"AURORA_SENTINEL_INVESTIGATE": "1", "AURORA_DEFENCE_MODE": "auto", "AURORA_UPDATE_MODE": "off"}
    assert user == {"AURORA_SOCIAL_AUTONOMY": "1"}
    with pytest.raises(ValueError):
        A.changes({"repairs": 2})                        # code changes are always approved: no 🚀
    with pytest.raises(ValueError):
        A.changes({"nonsense": 1})


def test_the_daily_line_and_who_may_choose(cfg):
    A.log(cfg, "security", "blocked 45.33.32.156 for 24 h", user="admin")
    A.log(cfg, "social", "facebook.post: a dream", user="giulia")
    d = A.days(cfg)
    assert d[0]["count"] == 2 and d[0]["areas"] == {"security": 1, "social": 1}
    assert [r["text"] for r in A.days(cfg, user="giulia")[0]["items"]] == ["facebook.post: a dream"]
    assert A.policy(cfg)["may_choose"] == {}
    assert A.set_may_choose(cfg, "giulia", True)["may_choose"] == {"giulia": True}


def test_an_area_proved_good_is_suggested_never_raised(cfg):
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    items = [{"kind": "tool_call", "title": "facebook.post", "status": "executed", "created": now} for _ in range(10)]
    items += [{"kind": "code_change", "title": "repair", "status": "rejected", "created": now}]
    st = A.statistics(cfg, items, {"facebook.post"})
    assert st["social"]["approved"] == 10 and st["social"]["rate"] == 1.0 and st["social"]["proved"]
    assert st["repairs"]["refused"] == 1 and not st["repairs"]["proved"]
    assert A.levels(cfg)["social"] == 0                  # proved, and still where the owner left it

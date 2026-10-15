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


def test_an_area_is_shown_only_while_what_it_governs_is_there():
    """Owner, 12 Oct: «deve mostrare solo ciò che è attivo e funzionante»; and the areas that were missing."""
    from aurora import sys_autonomy as A
    assert {"deduce", "synapses", "review", "harvest"} <= set(A.AREAS)
    assert not A.available("social", set(), False) and A.available("social", {"facebook"}, True)
    assert not A.available("devices", {"weather"}, False) and A.available("devices", {"homeassistant"}, False)
    assert A.available("synapses", set(), False)
    for p in A.PROFILES.values():                                     # every profile says every area
        assert set(p) == set(A.AREAS)
    lv = {a: n for a, n in A.PROFILES["balanced"].items()}
    lv["social"] = 2                                                   # a hidden area does not make it «custom»
    assert A.profile_of(lv) == "custom" and A.profile_of(lv, set(A.AREAS) - {"social"}) == "balanced"


def test_every_area_is_in_one_group_and_cloudflare_blocks_have_their_own(cfg):
    """Owner, 15 Oct: the page in the Models' style, and «verificherei che lì ci sia davvero tutto»: the blocks at
    Cloudflare were done alone with no area and counted nowhere."""
    import json
    from pathlib import Path
    grouped = [a for ids in A.GROUPS.values() for a in ids]
    assert sorted(grouped) == sorted(A.AREAS) and len(grouped) == len(set(grouped))
    assert A.AREAS["edge"][1][2] == {"AURORA_CLOUDFLARE_AUTOBLOCK": "1"} and "edge" in A.EXTERNAL
    assert A.NEEDS_PLUGIN["edge"] == "cloudflare"
    A.log(cfg, "security", "blocked 1 scanners at Cloudflare: 192.0.2.1", user="admin")     # written before the area
    A.log(cfg, "edge", "blocked 1 scanners at Cloudflare: 192.0.2.2", user="admin")
    assert A.statistics(cfg, [], set())["edge"]["alone"] == 2
    web = Path(__file__).resolve().parents[1] / "webui"
    for lang in ("it_IT", "en_US"):
        s = json.loads((web / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for a, (_, lv) in A.AREAS.items():
            assert f"auto.area.{a}" in s and all(f"auto.what.{a}.{n}" in s for n in lv)
        assert all(f"auto.group.{g}" in s and f"auto.group_hint.{g}" in s for g in A.GROUPS)
        assert all(f"auto.always.{k}" in s for k in A.ALWAYS)

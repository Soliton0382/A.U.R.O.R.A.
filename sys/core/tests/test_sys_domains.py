# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The installers' question on the domains (owner, 9 Oct: «chi scarica ha qualcosa in più per ciò che sceglie»)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))


def test_the_areas_cover_every_harvested_domain_once(cfg):
    import sys_domains as D
    from aurora import kno_sources
    listed = [d for _, _, ds in D.AREAS for d in ds]
    assert len(listed) == len(set(listed))
    assert set(listed) | {"general"} == set(kno_sources.modes(cfg))


def test_chosen_areas_are_harvested_and_the_rest_switched_off(cfg):
    import sys_domains as D
    from aurora import kno_sources
    before = kno_sources.modes(cfg)
    assert D.apply(cfg, "") == before                                      # Enter: the defaults
    modes = D.apply(cfg, "4, 8")
    on = {d for d, m in modes.items() if m != "off"}
    assert on == set(D.AREAS[3][2]) | {"law_it", "general"}
    assert D.apply(cfg, "tutte") and all(m != "off" for m in kno_sources.modes(cfg).values())
    with pytest.raises(ValueError):
        D.chosen_domains("9")

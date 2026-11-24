# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C738: what the owner's own account runs is root's signed copy, never the repo's code the service can write."""
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "script"


def test_c738_the_seed_is_in_root_s_copy():
    sys.path.insert(0, str(SCRIPT))
    import sys_root
    assert "shadow_seed.py" in sys_root.LIB_SCRIPTS


def test_c738_the_seed_s_unit_runs_root_s_copy_isolated_and_says_when_it_cannot():
    text = (SCRIPT / "shadow_seed.py").read_text(encoding="utf-8")
    assert 'py, script = "/usr/bin/python3 -I", lib' in text
    assert "lib.stat().st_uid == 0" in text                       # a copy root owns, not one planted by the service
    assert "C738" in text and "warning: no root's copy" in text
    # the seed's data folder is the installation's, so root's copy (code only) still finds and writes it
    assert 'CONFIG = sys_config.CODE_ROOT / "sys" / "core" / "config"' in text

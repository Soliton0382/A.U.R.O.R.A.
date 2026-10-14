# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The honeypot's test set says what it claims: the «zero_day» traps carry none of the cheap cues (only the decoy can
catch them), every address is a reserved example one, the harmless contents are as many as the traps."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import bench_honeypot_data as D  # noqa: E402

from aurora import sec_detonate  # noqa: E402


def test_zero_day_traps_have_no_cues_and_the_others_some():
    for name, zero_day, text in D.TRAPS:
        assert not (zero_day and sec_detonate.cues(text)), name
    found = {name for name, _, text in D.TRAPS if sec_detonate.cues(text)}
    assert {"fake_system", "tool_json"} <= found                    # C316: «\b<» never matched
    assert sum(z for _, z, _ in D.TRAPS) == 4 and len(D.HARMLESS) == len(D.TRAPS)


def test_every_address_is_an_example_one():
    for text in [t for *_, t in D.TRAPS] + [t for _, t in D.HARMLESS]:
        for host in re.findall(r"(?:https?://|@)([\w.-]+\.\w+)", text):
            assert host.endswith(("example.org", ".test")), host

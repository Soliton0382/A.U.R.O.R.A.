# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""No time of day in the public documents (doc_times): a time stamped on an event goes, the date and the duration stay;
a time Aurora is set to stays (a routine, a timer, a line marked <!-- schedule -->)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import doc_times as D  # noqa: E402


def test_stamps_go_dates_and_durations_stay():
    assert D.fix("Seen (14 Oct, 13:52–14:11): four alerts") == "Seen (14 Oct): four alerts"
    assert D.fix("`bench_agi.py --full` (12:44, 41.7 min), then") == "`bench_agi.py --full` (41.7 min), then"
    assert D.fix("found by Aurora at 14:54, 0 agents") == "found by Aurora, 0 agents"
    assert D.fix("| C302 | 14 Oct 01:43-06:03, Home Assistant") == "| C302 | 14 Oct, Home Assistant"
    assert D.fix("ready, 10.34 s, 12.23 GB") == "ready, 10.34 s, 12.23 GB"             # decimals are no time


def test_times_aurora_is_set_to_stay():
    for line in ("the morning routine (09:30) on a day with a dream", "to the NAS every night at 03:30: encrypted",
                 "posts 08:30, 09:30, 15:00 <!-- schedule -->", "the good morning at 9:30 to look at"):
        assert D.fix(line) == line and not D.left(line), line
    assert D.left("the run of 12 Oct 13:15 for x") == [] or D.fix("the run of 12 Oct 13:15 for x") != "the run of 12 Oct 13:15 for x"

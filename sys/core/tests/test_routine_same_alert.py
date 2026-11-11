# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""12 Nov: the weather alert went out every hour, its numbers moving with each forecast: an alert whose only change is
its numbers is the same alert, said again only after 12 hours."""
import time

from aurora import sys_routines as R


def test_an_alert_whose_numbers_move_is_not_new_until_twelve_hours_pass():
    r = {"notify": "if_new", "last_notified": "💨 raffiche fino a 62 km/h verso le 14:00", "last_notified_at": time.time()}
    assert not R.should_notify(r, "💨 raffiche fino a 67 km/h verso le 15:00", True)
    assert R.should_notify(r, "⛈️ temporale previsto verso le 18:00", True)
    r["last_notified_at"] = time.time() - R.REPEAT_AFTER_S - 1
    assert R.should_notify(r, "💨 raffiche fino a 67 km/h verso le 15:00", True)
    assert not R.should_notify(r, "", True)

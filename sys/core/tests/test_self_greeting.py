# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Owner, 30 Oct: «mi ha salutata 2 volte consecutivamente… anche se… mi stava rispondendo al proseguo»: a
conversation going on (a last turn under 30 min old) tells her not to greet again."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as N

from aurora.kno_self import SelfTalk


def test_a_conversation_going_on_is_told_apart_from_a_new_one():
    now = datetime.now(timezone.utc)
    turn = lambda minutes: N(created_at=(now - timedelta(minutes=minutes)).isoformat())   # noqa: E731
    assert SelfTalk._going_on(SelfTalk, [turn(90), turn(3)])
    assert not SelfTalk._going_on(SelfTalk, [turn(45)])
    assert not SelfTalk._going_on(SelfTalk, [])
    assert not SelfTalk._going_on(SelfTalk, [N(created_at="not a date")])

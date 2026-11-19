# SPDX-License-Identifier: Apache-2.0
"""C610: the audit line of a restart names who asked for it."""
from aurora.sys_fresh import restart_origin


def test_page_is_the_default():
    assert restart_origin({"services": ["aurora-api"]}) == "the WebUI"


def test_morning_restart_is_named():
    assert restart_origin({"services": ["aurora-api"], "origin": "morning"}) == "the morning restart (aurora-rem)"


def test_unknown_origin_never_reaches_the_log():
    assert restart_origin({"origin": "x\nforged line"}) == "the WebUI"
    assert restart_origin({"origin": ["morning"]}) == "the WebUI"

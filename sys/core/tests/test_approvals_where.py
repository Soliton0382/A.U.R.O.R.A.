# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Owner, 9 Oct: «un alert che lampeggia nella barra in alto che mi porta nella pagina corretta (è un post, icona
specifica che mi manda sui social)» and «la pagina approvazioni racchiude … statistica e log»."""
from aurora import sys_approvals as A


def test_each_request_says_where_it_is_decided_and_its_icon(cfg):
    from pathlib import Path
    social = A.social_plugins(cfg, Path(__file__).resolve().parents[2] / "plugins")      # the plugins Aurora ships
    assert {"mastodon", "facebook"} <= social
    post = {"kind": "tool_call", "action": {"plugin": "mastodon", "tool": "post_status"}}
    reel = {"kind": "tool_call", "action": {"plugin": "tiktok", "tool": "tiktok_post_video"}}
    assert A.destination(post, social) == {"view": "social", "icon": "📣"}
    assert A.destination(reel, social) == {"view": "social", "icon": "🎬"}
    assert A.destination({"kind": "tool_call", "action": {"plugin": "security", "tool": "block"}}, social)["view"] == "security"
    assert A.destination({"kind": "update"}, social) == {"view": "updates", "icon": "🔄"}
    assert A.destination({"kind": "plugin_install"}, social)["view"] == "plugins"
    assert A.destination({"kind": "code_change"}, social) == {"view": "approvals", "icon": "🧬"}
    assert A.destination({"kind": "tool_call", "action": {"plugin": "email", "tool": "send"}}, social)["view"] == "approvals"


def test_the_numbers_of_each_kind(cfg):
    items = [{"kind": "tool_call", "status": "executed", "created": "2026-10-09T10:00:00+0200", "decided": "2026-10-09T10:04:00+0200"},
             {"kind": "tool_call", "status": "rejected", "created": "2026-10-09T10:00:00+0200", "decided": "2026-10-09T10:10:00+0200"},
             {"kind": "tool_call", "status": "pending", "created": "2026-10-09T11:00:00+0200", "decided": None},
             {"kind": "update", "status": "executed", "created": "2026-10-09T09:00:00+0200", "decided": "2026-10-09T09:01:00+0200"}]
    s = A.stats(items)
    assert s["tool_call"] == {"requested": 3, "approved": 1, "rejected": 1, "pending": 1, "median_minutes": 10.0}
    assert s["update"]["approved"] == 1 and s["update"]["median_minutes"] == 1.0

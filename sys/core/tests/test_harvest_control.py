# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from aurora import kno_harvest


def test_arxiv_ids_and_links_are_recognised():
    ids, other = kno_harvest.parse_items("2104.09864\narXiv:1706.03762v5\nhttps://arxiv.org/pdf/2402.01234v2.pdf\n"
                                         "hep-th/9711200\n2104.09864\nhttps://example.com/x.pdf\nsolitoni")
    assert ids == ["2104.09864", "1706.03762", "2402.01234", "hep-th/9711200"]
    assert other == ["https://example.com/x.pdf", "solitoni"]


def test_commands_queue_in_order_and_are_taken_once(cfg):
    a = kno_harvest.send(cfg, "now")
    b = kno_harvest.send(cfg, "batch", ids=["2104.09864"])
    assert kno_harvest.pending(cfg) == 2
    got = kno_harvest.take(cfg)
    assert [c["id"] for c in got] == [a["id"], b["id"]] and got[1]["ids"] == ["2104.09864"]
    assert kno_harvest.pending(cfg) == 0 and kno_harvest.take(cfg) == []


def test_status_is_merged(cfg):
    assert kno_harvest.status(cfg) == {"state": "unknown"}
    kno_harvest.set_status(cfg, state="idle", next_round=1.0)
    st = kno_harvest.set_status(cfg, last_round=2.0)
    assert st["state"] == "idle" and st["next_round"] == 1.0 and st["last_round"] == 2.0

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


def test_a_host_that_says_slow_down_is_asked_again_then_left_alone(cfg, monkeypatch):
    """C214: a 429 is retried after a pause; a host that keeps refusing is skipped, not knocked every 3 s."""
    import importlib
    import sys
    from pathlib import Path

    import httpx
    import pytest
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda: cfg)            # the test's installation, never this machine's
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "script"))
    monkeypatch.delitem(sys.modules, "svc_harvester", raising=False)
    svc = importlib.import_module("svc_harvester")
    monkeypatch.delitem(sys.modules, "svc_harvester")
    monkeypatch.setattr(svc, "BACKOFF_S", (1, 1))
    pauses, hits = [], []
    answers = iter([429, 200, 429, 429, 429])

    def reply(request):
        hits.append(request.url.host)
        return httpx.Response(next(answers), headers={"Retry-After": "2"} if len(hits) == 1 else {})
    h = svc.Harvester.__new__(svc.Harvester)
    h.web, h._tls, h._last, h._cool = httpx.Client(transport=httpx.MockTransport(reply)), {}, {}, {}
    monkeypatch.setattr(h, "_pause", pauses.append)
    assert h._get("https://export.arxiv.org/api/query").status_code == 200
    assert pauses == [2]                                          # Retry-After honoured
    with pytest.raises(httpx.HTTPStatusError):
        h._get("https://export.arxiv.org/api/query")              # 429, 429, 429: given up
    assert pauses == [2, 1, 1] and len(hits) == 5
    with pytest.raises(httpx.HTTPError, match="slow down"):
        h._get("https://export.arxiv.org/api/query")              # left alone: no request at all
    assert len(hits) == 5

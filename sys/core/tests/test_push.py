# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import base64
from types import SimpleNamespace

import pytest

from aurora import sys_push
from conftest import private  # noqa: E402 — who may read a file, asked of this system

SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}


def test_vapid_key_is_made_once_private_and_well_formed(cfg):
    k1, k2 = sys_push.public_key(cfg), sys_push.public_key(cfg)
    raw = base64.urlsafe_b64decode(k1 + "=" * (-len(k1) % 4))
    assert k1 == k2 and len(raw) == 65 and raw[0] == 4                # uncompressed P-256 point
    assert private(cfg.path("AURORA_STATUS_DIR") / "push" / "vapid_private.pem")


def test_subscriptions_are_validated_and_deduplicated(cfg):
    with pytest.raises(ValueError):
        sys_push.subscribe({"endpoint": "http://plain/x", "keys": {}}, None, cfg)
    assert sys_push.subscribe(SUB, "pc", cfg) == 1 and sys_push.subscribe(SUB, "pc", cfg) == 1
    assert sys_push.unsubscribe(SUB["endpoint"], cfg) == 0


def test_only_the_events_the_owner_chose_notify(cfg):
    cfg.values["AURORA_PUSH_EVENTS"] = "incident,dream"
    assert sys_push.message("rem.dream", {"text": "x" * 400}, cfg)["body"].endswith("…")
    assert sys_push.message("rem.thought", {"text": "t"}, cfg) is None
    assert sys_push.message("run.end", {}, cfg) is None
    assert sys_push.message("incident", {"title": "ips_alert · 1.2.3.4"}, cfg)["view"] == "security"


def test_gone_subscriptions_are_dropped(cfg, monkeypatch):
    import pywebpush
    sys_push.subscribe(SUB, None, cfg)
    sys_push.subscribe({**SUB, "endpoint": "https://push.example/ok"}, None, cfg)

    def fake(info, data, **kw):
        if info["endpoint"].endswith("abc"):
            raise pywebpush.WebPushException("gone", response=SimpleNamespace(status_code=410))
    monkeypatch.setattr(pywebpush, "webpush", fake)
    out = sys_push.send(sys_push.message("test", {}, cfg), cfg)
    assert out == {"sent": 1, "dropped": 1, "failed": 0} and sys_push.count(cfg) == 1


def test_each_channel_follows_the_owners_choice(cfg):
    p = sys_push.set_prefs(cfg, {"push": ["update", "nonsense"], "webui": sys_push.PRESETS["all"]})
    assert p["push"] == ["update"] and set(p["webui"]) == set(sys_push.KINDS)
    assert sys_push.message("update.available", {"text": "3 novità"}, cfg, "push")["view"] == "approvals"
    assert sys_push.message("rem.dream", {"text": "x"}, cfg, "push") is None
    assert sys_push.message("rem.dream", {"text": "x"}, cfg, "webui")["title"]
    sys_push.set_prefs(cfg, {"push": [], "webui": []})
    assert sys_push.message("incident", {"title": "t"}, cfg, "webui") is None


def test_a_device_confirms_a_push_once_and_only_a_real_one(cfg, monkeypatch):
    import json
    import time
    import pywebpush
    sys_push.subscribe(SUB, None, cfg)
    sys_push.subscribe({**SUB, "endpoint": "https://push.example/two"}, None, cfg)
    payloads = []
    monkeypatch.setattr(pywebpush, "webpush", lambda info, data, **kw: payloads.append(json.loads(data)))
    sys_push.send(sys_push.message("test", {}, cfg), cfg)
    pid = payloads[0]["id"]
    assert len(pid) == 16 and payloads[1]["id"] == pid                 # one id per push, the same on every device
    assert not sys_push.ack("0" * 16, SUB["endpoint"], cfg)              # an id never sent
    assert sys_push.ack(pid, SUB["endpoint"], cfg) and not sys_push.ack(pid, SUB["endpoint"], cfg)
    assert not sys_push.ack("../../etc", SUB["endpoint"], cfg)
    monkeypatch.setattr(time, "time", lambda real=time.time(): real + 120)      # past the one minute still on its way
    assert sys_push.delivery(cfg) == {"days": 7, "pushes": 1, "accepted": 2, "confirmed": 1, "rate": 0.5}

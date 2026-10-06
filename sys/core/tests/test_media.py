# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Pictures, edits and videos from a cloud provider (owner, 2026-10-06): chosen, masked, refused for photos without the
exemption, counted. The providers' answers are simulated: a real call is billed (the owner's first use is N86)."""
import base64
import io
import json

import pytest

from aurora import mdl_media as M

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class R:
    def __init__(self, data, content=b""):
        self.data, self.content, self.status_code = data, content, 200

    def json(self):
        return self.data

    def raise_for_status(self):
        return None


def test_chosen_only_where_it_can_and_with_a_key(cfg):
    cfg.values.update(AURORA_OPENAI_API_KEY="k", AURORA_XAI_API_KEY="")
    assert M.assignments(cfg)["image"]["provider"] == "local"
    M.set_assignments(cfg, {"image": {"provider": "openai"}})
    assert M.provider(cfg, "image") == ("openai", "gpt-image-1")
    with pytest.raises(ValueError):
        M.set_assignments(cfg, {"video": {"provider": "openai"}})          # OpenAI makes no videos here
    with pytest.raises(ValueError):
        M.set_assignments(cfg, {"image": {"provider": "xai"}})             # no key
    assert [c["provider"] for c in M.choices(cfg)["edit"]] == ["local", "openai", "google"]


def test_a_picture_masked_counted_and_a_photo_refused_without_exemption(cfg, monkeypatch):
    cfg.values.update(AURORA_OPENAI_API_KEY="k", AURORA_GOOGLE_API_KEY="g")
    M.set_assignments(cfg, {"image": {"provider": "openai"}, "edit": {"provider": "google"}})
    sent, traces = {}, []
    monkeypatch.setattr(M.httpx, "post", lambda url, **kw: sent.update(url=url, **kw) or R({"data": [{"b64_json": base64.b64encode(PNG).decode()}]}))
    monkeypatch.setattr(M.sys_log, "trace", lambda comp, ev, payload: traces.append((ev, payload)))
    data, st = M.picture(cfg, "image", "Un ritratto di Mario Rossi al mare, mario.rossi@example.com")
    assert data == PNG and st["provider"] == "openai" and sent["url"].endswith("/images/generations")
    assert "mario.rossi@example.com" not in json.dumps(sent["json"])                     # masked before it left
    assert [e for e, _ in traces] == ["cloud.mask", "cloud.call"]
    from aurora import sys_ethics
    monkeypatch.setattr(sys_ethics, "exempt", lambda cfg=None: False)
    with pytest.raises(PermissionError):
        M.picture(cfg, "edit", "mettici la neve", PNG)                                  # a photo is not maskable
    monkeypatch.setattr(sys_ethics, "exempt", lambda cfg=None: True)
    monkeypatch.setattr(M.httpx, "post", lambda url, **kw: R({"candidates": [{"content": {"parts": [
        {"text": "ecco"}, {"inline_data": {"data": base64.b64encode(PNG).decode()}}]}}]}))
    assert M.picture(cfg, "edit", "mettici la neve", PNG)[0] == PNG


def test_a_video_polled_until_done(cfg, monkeypatch):
    cfg.values.update(AURORA_GOOGLE_API_KEY="g")
    M.set_assignments(cfg, {"video": {"provider": "google"}})
    polls = iter([{"done": False}, {"done": True, "response": {"generateVideoResponse": {"generatedSamples": [
        {"video": {"uri": "https://example.com/v.mp4"}}]}}}])
    monkeypatch.setattr(M.httpx, "post", lambda url, **kw: R({"name": "operations/abc"}))
    monkeypatch.setattr(M.httpx, "get", lambda url, **kw: R(next(polls)) if "operations" in url else R({}, b"MP4"))
    monkeypatch.setattr(M.time, "sleep", lambda s: None)
    data, st = M.video(cfg, "un gattino nella neve")
    assert data == b"MP4" and st["model"].startswith("veo")


def test_the_local_painting_is_untouched_when_nothing_is_chosen(cfg):
    from aurora import mdl_image
    import logging
    assert mdl_image._cloud(cfg, "image", "x", None, logging.getLogger("t")) is None

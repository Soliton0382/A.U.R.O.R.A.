# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's voice and dictation from a cloud provider (owner, 9 Oct: «aurora full cloud può usare modelli on line … la
voce … ovviamente mascheramento dei dati sensibili è prioritario e vale su ogni cosa va verso l'api»). The providers are
answered here: no call leaves the test."""
import base64
import json

import numpy as np
import pytest

from aurora import mdl_media, mdl_tts, sys_ethics


class Answer:
    def __init__(self, content=b"", data=None):
        self.content, self._data = content, data

    def raise_for_status(self):
        return self

    def json(self):
        return self._data


@pytest.fixture
def cloud(cfg, monkeypatch):
    cfg.values.update(AURORA_OPENAI_API_KEY="sk-test", AURORA_GOOGLE_API_KEY="g-test", AURORA_OWNER_NAME="Mario Rossi")
    sent = []

    def post(url, **k):
        sent.append({"url": url, **k})
        if url.endswith("/audio/speech"):
            return Answer(content=b"RIFF-openai")
        if url.endswith("/audio/transcriptions"):
            return Answer(data={"text": " ciao  Aurora "})
        if "tts" in url:
            pcm = base64.b64encode(b"\0\0" * 100).decode()
            return Answer(data={"candidates": [{"content": {"parts": [{"inlineData": {"data": pcm}}]}}]})
        return Answer(data={"candidates": [{"content": {"parts": [{"text": "buongiorno"}]}}]})
    monkeypatch.setattr(mdl_media.httpx, "post", post)
    return cfg, sent


def test_the_voice_never_carries_private_data_and_says_it_by_kind(cloud):
    cfg, sent = cloud
    mdl_media.set_assignments(cfg, {"voice": {"provider": "openai", "model": ""}})
    data = mdl_tts.speak(cfg, "Scrivi a mario@example.com, Mario Rossi, al 333 1234567.", "it")
    assert data == b"RIFF-openai"
    said = sent[-1]["json"]["input"]
    assert "mario@example.com" not in said and "Mario Rossi" not in said and "1234567" not in said
    assert "un indirizzo email" in said and "[" not in said                  # spoken by kind, no «[EMAIL_1]» read aloud
    mdl_media.set_assignments(cfg, {"voice": {"provider": "google", "model": ""}})
    wav = mdl_media.spoken(cfg, "Hello", "en")
    assert wav[:4] == b"RIFF" and "Kore" in json.dumps(sent[-1]["json"])     # Gemini's PCM wrapped as WAV, a female voice


def test_dictation_goes_to_the_cloud_only_on_an_exempted_installation(cloud, monkeypatch):
    cfg, sent = cloud
    mdl_media.set_assignments(cfg, {"speech": {"provider": "openai", "model": ""}})
    audio = np.zeros(16000 * 2, dtype=np.float32)
    monkeypatch.setattr(sys_ethics, "exempt", lambda c: False)
    with pytest.raises(PermissionError, match="cannot be masked"):
        mdl_media.heard(cfg, audio, "it")
    assert not sent
    monkeypatch.setattr(sys_ethics, "exempt", lambda c: True)
    out = mdl_media.heard(cfg, audio, "it")
    assert out["text"] == "ciao Aurora" and out["audio_s"] == 2.0 and sent[-1]["data"]["language"] == "it"
    segs = mdl_media.heard_segments(cfg, np.zeros(16000 * 70, dtype=np.float32), "it")
    assert [(a, b) for a, b, _ in segs] == [(0.0, 30.0), (30.0, 60.0), (60.0, 70.0)]


def test_a_cloud_voice_or_dictation_opens_the_feature_without_local_models(cloud, monkeypatch):
    from aurora import sys_features
    cfg, _ = cloud
    mdl_media.set_assignments(cfg, {"voice": {"provider": "openai", "model": ""}, "speech": {"provider": "google", "model": ""}})
    assert sys_features.check(cfg, "voice_out")["ok"]
    monkeypatch.setattr(sys_ethics, "exempt", lambda c: False)
    assert not sys_features.check(cfg, "speech")["ok"]                     # a voice to the cloud needs the exemption

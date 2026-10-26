# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📞 The call (N45, aurora-app F3): it rings on the line, a declined or missed call leaves its reason, the voice coming
in is cut at the pauses, the voice going out is in the call's format."""
import io
import re
import wave
from pathlib import Path

import numpy as np

from aurora import sys_call, sys_line

ROOT = Path(__file__).resolve().parents[1]
R = sys_call.RATE


def pcm(seconds, amp=0.0, hz=220.0):
    t = np.arange(int(seconds * R)) / R
    noise = np.random.default_rng(1).normal(0, 30, t.size)                 # the line's own hiss
    return (amp * 32767 * np.sin(2 * np.pi * hz * t) + noise).astype("<i2").tobytes()


def test_a_sentence_is_cut_at_its_pause_and_a_click_is_not_one():
    seg = sys_call.Segmenter()
    out = seg.feed(pcm(1.0) + pcm(1.5, 0.3) + pcm(1.0))
    assert len(out) == 1 and 1.4 <= out[0].size / R <= 2.5 and out[0].dtype == np.float32
    assert np.abs(out[0]).max() <= 1.0
    assert seg.feed(pcm(0.5) + pcm(0.1, 0.5) + pcm(1.2)) == []          # 0.1 s: a click, not a sentence
    two = seg.feed(pcm(1.0, 0.3) + pcm(1.0) + pcm(0.8, 0.3) + pcm(1.0))
    assert len(two) == 2


def test_the_answer_is_said_in_sentences_without_markdown():
    s = sys_call.sentences("**Ciao!** Il [sito](https://x.example) è su.\n- Domani piove? Sì… https://y.example")
    assert s == ["Ciao!", "Il sito è su.", "- Domani piove?", "Sì…"]
    assert sys_call.sentences("  \n ** ") == []


def test_her_voice_is_sent_at_16_khz_mono():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(22050)
        w.writeframes(np.zeros(22050 * 2, dtype="<i2").tobytes())       # 1 s of stereo at 22.05 kHz
    out = sys_call.pcm16k(buf.getvalue())
    assert len(out) == 2 * R


def test_a_call_rings_on_the_line_and_a_declined_one_keeps_its_reason(cfg, monkeypatch):
    monkeypatch.setattr(sys_call.threading, "Timer", lambda *a: type("T", (), {"start": lambda self: None})())
    start = sys_line.last(cfg)
    c = sys_call.ring("Il backup non è riuscito", cfg, "anna")
    ev = sys_line.since(start, cfg)
    assert ev[-1]["kind"] == "call" and ev[-1]["call"] == c["id"] and ev[-1]["ring"] == sys_call.RING_S
    assert sys_call.decline(c["id"], cfg) and not sys_call.decline(c["id"], cfg)      # once
    end = sys_line.since(ev[-1]["id"], cfg)[-1]
    assert end["kind"] == "call_end" and end["body"] == "Il backup non è riuscito" and "rifiutata" in end["title"]
    m = sys_call.ring("", cfg, "anna")
    assert m["reason"] == "Prova di chiamata"
    sys_call._missed(m["id"], cfg)
    assert sys_call.calls[m["id"]]["state"] == "missed" and "persa" in sys_line.since("0", cfg)[-1]["title"]
    sys_call.set_state(m["id"], "answered")
    sys_call._missed(m["id"], cfg)                                       # answered meanwhile: not missed
    assert sys_call.calls[m["id"]]["state"] == "answered"


def test_the_routes_need_a_login_and_the_audio_checks_whose_call():
    src = (ROOT / "aurora" / "api" / "call.py").read_text()
    posts = re.findall(r'@router\.post\("([^"]+)", dependencies=\[Depends\((\w+)\)\]\)', src)
    assert posts == [("/v1/aurora/call", "auth"), ("/v1/aurora/call/dial", "auth"), ("/v1/aurora/call/{call_id}/decline", "auth")]
    body = src.split("async def call_audio(")[1].split("await ws.accept()")[0]
    assert 'user is False or not c or c["user"] != user' in body and "ws.close(code=4404)" in body
    assert '"kind": "call_answered"' in src                            # answered: the other phones stop ringing
    assert "'call'" in (ROOT / "aurora" / "api" / "__init__.py").read_text()


def test_the_owner_s_own_call_rings_nowhere_and_opens_once(cfg):
    start = sys_line.last(cfg)
    c = sys_call.dial("anna")
    assert c["state"] == "dialing" and c["by"] == "owner" and sys_line.since(start, cfg) == []    # no phone rings
    assert sys_call.set_state(c["id"], "answered", only_from="dialing")
    assert not sys_call.set_state(c["id"], "answered", only_from="dialing")
    src = (ROOT / "aurora" / "api" / "call.py").read_text()
    assert '"dialing"):' in src and 'c.get("by") == "owner"' in src     # the audio takes it; she does not say a reason

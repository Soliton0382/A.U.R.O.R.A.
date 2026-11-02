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


def test_a_plain_phone_command_in_a_call_is_done_by_the_app_at_once(cfg, monkeypatch):
    """N68: «apri YouTube» said in a call (the assistant's way in) goes to the app with no model; she says it is done.
    An app that does not answer (a version without phone actions): Aurora answers as before."""
    import asyncio
    import json as _json
    import logging

    from aurora import sys_call as C

    class WS:
        def __init__(self, answer):
            self.sent, self.answer, self.voice = [], answer, None

        async def send_text(self, t):
            self.sent.append(_json.loads(t))
            j = self.sent[-1]
            if j["type"] == "phone" and self.answer:
                self.voice.phone[j["action"]["id"]].set_result(self.answer)

    class Voice:
        def __init__(self):
            self.phone, self.said = {}, []

        async def say(self, text, turn=None):
            self.said.append(text)

    async def run(answer, text):
        ws, v = WS(answer), Voice()
        ws.voice = v
        done = await C.phone_now(ws, v, text, "it", 0, logging.getLogger("t"))
        return done, ws.sent, v.said

    done, sent, said = asyncio.run(run("ok", "Apri YouTube."))
    assert done and sent[0]["action"]["action"] == "open_app" and sent[0]["action"]["app"] == "YouTube"
    assert said == ["Fatto."] and sent[-1]["type"] == "said"
    done, _, said = asyncio.run(run("no_app", "apri Pippo"))
    assert done and said == ["Sul telefono non c'è un'app per farlo."]
    wait_for = C.asyncio.wait_for
    monkeypatch.setattr(C.asyncio, "wait_for", lambda f, t: (_ for _ in ()).throw(C.asyncio.TimeoutError()))
    done, _, said = asyncio.run(run("", "Apri YouTube"))
    assert not done and not said                                        # an old app: the question goes on to Aurora
    assert asyncio.run(run("ok", "Che tempo fa domani?"))[0] is False   # not a command: Aurora answers
    monkeypatch.setattr(C.asyncio, "wait_for", wait_for)

    class Model:                                                        # what the patterns miss: the reasoner (M273)
        def complete(self, system, user, n, think=False):
            return type("C", (), {"answer": '{"action":"open_app","app":"Spotify"}' if "musica" in user else "NONE"})

    async def run2(text):
        ws, v = WS("ok"), Voice()
        ws.voice = v
        return await C.phone_now(ws, v, text, "it", 0, logging.getLogger("t"), Model()), ws.sent

    done, sent = asyncio.run(run2("vorrei ascoltare un po' di musica su Spotify"))
    assert done and sent[0]["action"]["app"] == "Spotify"
    assert asyncio.run(run2("Che tempo fa domani?"))[0] is False


def _pcm(voice_s, quiet_s, rate=16000):
    import numpy as np
    n, q = int(voice_s * rate), int(quiet_s * rate)
    return (np.sin(np.arange(n) * 0.2) * 12000).astype("<i2").tobytes() + b"\0\0" * q


def test_the_first_pause_of_a_sentence_is_a_guess_and_going_on_is_not_the_end():
    """🔮 The voice so far offered at PAUSE_S of quiet; once the answer is ready the end comes sooner; the owner going on
    gives the whole wait back."""
    from aurora.sys_call import Segmenter as S
    s = S()
    s.feed(b"\0\0" * 3200)
    assert s.feed(_pcm(1.0, S.PAUSE_S + 0.04)) == [] and s.maybe is not None     # at the pause, not ended
    first = len(s.maybe)
    s.maybe, s.end_s = None, 0.6
    s.feed(_pcm(0.5, 0))                                                          # goes on
    assert s.end_s == S.END_S
    assert s.feed(b"\0\0" * int(0.6 * 16000)) == [] and s.maybe is not None and len(s.maybe) > first
    assert len(s.feed(b"\0\0" * int(0.3 * 16000))) == 1 and s.end_s == S.END_S    # at END_S only
    s.feed(_pcm(1.0, S.PAUSE_S + 0.04))
    s.end_s = 0.6
    assert len(s.feed(b"\0\0" * int(0.3 * 16000))) == 1                           # ready: ended sooner


def test_a_guess_is_taken_only_for_the_same_voice_and_acts_on_nothing(monkeypatch):
    import asyncio
    import numpy as np
    from aurora import agt_phone, kno_talk, sns_av, sys_call, sys_call_ahead as A
    said = []
    monkeypatch.setattr(sns_av, "transcribe", lambda a, l, c: {"clear": True, "text": "Apri YouTube adesso per favore."})
    monkeypatch.setattr(agt_phone, "understand", lambda m, t: {"id": "x", "action": "open_app", "app": "YouTube"})
    monkeypatch.setattr(agt_phone, "quick", lambda t: None)

    class P:
        llm = object()

    async def run():
        seg = sys_call.Segmenter()
        a = A.Ahead(P(), None, "it", seg, lambda *x: said.append(x))
        voice = np.zeros(16000, dtype=np.float32)
        a.pause(voice)
        got = await a.take(np.zeros(16000 + 8000, dtype=np.float32))              # only quiet added
        assert got.act["app"] == "YouTube" and got.done and seg.end_s == A.READY_END_S
        a.pause(voice)
        assert await a.take(np.zeros(16000 * 4, dtype=np.float32)) is None        # the owner went on: dropped
        assert await a.take(voice) is None                                        # no guess
    asyncio.run(run())
    assert not said and kno_talk._ready == {}


def test_an_answer_prepared_is_said_once_with_no_second_generation():
    from aurora import kno_talk as K
    calls = []

    class M:
        def decide(self, s, u, o):
            calls.append("route")
            return {"TALK": 1.0, "SEARCH": 0.0}

        def stream(self, *a, **k):
            calls.append("stream")
            return iter([("answer", "Sto "), ("answer", "bene.")])

    class P:
        llm = M()
    orig = K.system
    K.system = lambda *a: "S"
    try:
        assert K.prepare(P(), None, "Come stai?", []) == ("Sto bene.", False)
        ev = []
        assert K.quick(P(), None, " Come  stai?", [], lambda n, d: ev.append(d["text"])) == ("Sto bene.", False)
        assert ev == ["Sto bene."] and calls == ["route", "stream"]
        K.quick(P(), None, "Come stai?", [], lambda n, d: ev.append(d["text"]))
        assert calls.count("stream") == 2                                         # taken once
        assert K.prepare(P(), None, "Altro", [], stop=lambda: True) == ("", False) and "Altro" not in K._ready
    finally:
        K.system = orig


def test_the_chat_s_hands_free_sentence_takes_a_call_s_quick_path():
    """🗣️ The chat's conversation asks with talk: true, the words so far prepared (kno_talk.prepare) while it listens."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    chat = (root / "webui/js/modules/chat.js").read_text()
    media = (root / "webui/js/modules/chat_media.js").read_text()
    assert "talking && !attachments.length" in chat and "{ talk: true }" in chat and 'name === "talk.delta"' in chat
    assert "conversation: conversing()" in media
    assert 'body.get("talk") is True' in (root / "aurora/api/runs.py").read_text()
    assert "_prepare_talk(" in (root / "aurora/api/knowledge.py").read_text()

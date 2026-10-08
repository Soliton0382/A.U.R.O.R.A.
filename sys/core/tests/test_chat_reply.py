# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""↩️ A reply to one of Aurora's messages, 📋 copy, the composer's menus and the voice played inside the tap (owner,
2026-10-08)."""
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from aurora import kno_followup as F
from aurora import sol_schema as S
from aurora.sol_reader import VaultReader
from aurora.sol_writer import VaultWriter

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "webui" / "js"


def _turn(text, role, run_id, when):
    return S.Soliton.new(text, "conversation", "conversation", "it", f"run:{run_id}",
                         extra={"role": role, "run_id": run_id,
                                **({"source_list": [{"source": "wiki:laser", "domain": "physics", "title": "Laser"}]}
                                   if role == "assistant" else {})}, created_at=when)


def test_the_quoted_answer_is_read_as_aurora_kept_it_and_a_quote_from_the_page_otherwise(cfg):
    old = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    VaultWriter(cfg).add_many([_turn("Come funziona un laser?", "user", "abc123def456", old),
                               _turn("Un laser amplifica la luce per emissione stimolata.", "assistant", "abc123def456", old)])
    r = VaultReader(cfg)
    q = F.quoted(r, {"run_id": "abc123def456", "text": "something else the page said"})
    assert q.text.startswith("Un laser amplifica") and q.extra["source_list"][0]["source"] == "wiki:laser"
    page = F.quoted(r, {"run_id": "ffffffffffff", "text": "Buongiorno! Stanotte ho studiato."})
    assert page.text == "Buongiorno! Stanotte ho studiato." and page.extra["role"] == "assistant"
    assert F.quoted(r, {"run_id": "../../etc", "text": ""}) is None and F.quoted(r, "x") is None
    assert len(F.quoted(r, {"text": "a" * 10000}).text) == F.QUOTE_CUT


def test_a_reply_is_read_against_the_quote_however_old():
    old = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    quote = _turn("Un laser amplifica la luce per emissione stimolata.", "assistant", "abc123def456", old)
    recent = [_turn("Che tempo fa?", "user", "aaa111", old), _turn("Sereno.", "assistant", "aaa111", old)]
    turns = F.with_quote(recent + [quote], quote)
    assert turns[-1] is quote and len(turns) == 3                       # the quote last, never twice
    seen = {}

    def complete(system, user, n):
        seen["user"] = user
        return SimpleNamespace(answer="Quanto è potente un laser a emissione stimolata?")
    p = SimpleNamespace(cfg={"AURORA_PIPELINE_STANDALONE": True, "AURORA_REM_SESSION_GAP_MIN": 30, "AURORA_TIMEZONE": "UTC"},
                        _turns=lambda rs, n, cut: "\n".join(t.text for t in rs), _for=lambda role: SimpleNamespace(complete=complete))
    q, focus = F.standalone(p, "quanto è potente?", turns, lambda *a: None, quote)
    assert q.startswith("Quanto è potente un laser") and focus == [{"source": "wiki:laser", "domain": "physics"}]
    assert "LAST ANSWER (whole):\nUn laser amplifica" in seen["user"]
    assert F.standalone(p, "quanto è potente?", recent, lambda *a: None) == ("quanto è potente?", [])   # no quote: too old


def test_the_reply_goes_from_the_page_to_the_answer_and_back_into_the_history():
    runs = (ROOT / "aurora" / "api" / "runs.py").read_text()
    assert 'kno_followup.quoted(pipeline().reader, body.get("reply_to"))' in runs
    assert runs.count("quote=quote") == 2                                # the vault pipeline and the default job
    assert '"reply_to": t.extra.get("reply_to")' in (ROOT / "aurora" / "api" / "knowledge.py").read_text()
    chat = (JS / "modules" / "chat.js").read_text()
    assert "reply_to: reply" in chat and "turn.reply_to" in chat


def test_the_composer_has_the_clip_the_microphone_and_the_gear_only():
    chat = (JS / "modules" / "chat.js").read_text()
    form = re.search(r'<form class="ask">(.*?)</form>', chat, re.S).group(1)
    buttons = re.findall(r'<button type="button" class="icon (\w+)', form)
    assert buttons == ["attach", "mic", "gear", "hush"]
    menu = (JS / "modules" / "chat_menu.js").read_text()
    think = (JS / "modules" / "chat_think.js").read_text()
    assert '"": "🧠"' in think and "⚙️" not in re.search(r"THINK_ICON = \{.*?\}", think).group(0)


def test_every_word_of_the_chat_exists_in_both_languages_and_no_key_is_written_twice():
    src = "".join((JS / "modules" / f).read_text() for f in ("chat.js", "chat_menu.js", "chat_actions.js", "chat_media.js"))
    keys = set(re.findall(r'\bt\("([\w.]+)"', src)) | set(re.findall(r'data-i18n(?:-title|-placeholder)?="([\w.]+)"', src))
    dynamic = {f"chat.menu.think.{m}" for m in ("setting", "auto", "light", "medium", "deep")} \
        | {f"chat.think.{m}" for m in ("setting", "auto", "light", "medium", "deep")} \
        | {f"chat.menu.src.{s}" for s in ("device", "pc")} | {f"chat.menu.voice.{m}" for m in ("voice", "always", "off")} \
        | {"chat.voice.blocked", "chat.voice.offline", "chat.voice.novoice.online", "chat.voice.novoice.none"}
    for f in ("it_IT.json", "en_US.json"):
        raw = (ROOT / "webui" / "i18n" / f).read_text()
        pairs = json.loads(raw, object_pairs_hook=lambda p: p)
        assert [k for k, n in Counter(k for k, _ in pairs).items() if n > 1] == []
        missing = (keys | dynamic) - set(json.loads(raw))
        assert not missing, (f, missing)


def test_a_voice_already_made_is_played_inside_the_tap():
    v = (JS / "voice.js").read_text()
    speak = v[v.index("export async function speak"):]
    assert speak.index("if (ready) return playClip(ready);") < speak.index("await")      # nothing waited before play()
    play = v[v.index("function playClip"):v.index("export let unplayable")]
    assert "await" not in play and "audio.play()" in play
    assert '"NotAllowedError") return "blocked"' in play                   # the other refusals say their own name
    media = (JS / "modules" / "chat_media.js").read_text()
    assert "voice.prepare(said" in media                                  # the good morning made before the tap


def test_a_reply_that_works_on_the_quote_is_hers_with_the_quote_in_front_of_her():
    from aurora.kno_self import SYS_ROUTE_QUOTE, SelfTalk
    asked = []

    def complete(system, user, n):
        asked.append(system)
        return SimpleNamespace(answer="ON" if "due righe" in user else "NEW")
    me = SelfTalk()
    me._for = lambda role: SimpleNamespace(complete=lambda s, u, n: complete(s, u, n) if s == SYS_ROUTE_QUOTE
                                          else SimpleNamespace(answer="KNOWLEDGE"))
    quote = S.Soliton.new("La rete nelle ultime 24 ore: quattro cose da controllare.", "conversation", "conversation", "it", "quote")
    me._turns = lambda rs, n, cut=500: ""
    assert me._route("spiegamelo in due righe", [quote], quote) == "self"
    assert me._route("chi ha inventato il firewall?", [quote], quote) == "knowledge"
    assert me._route("spiegamelo in due righe", [quote]) == "knowledge"       # no quote: the usual router


def test_the_page_may_play_the_voice_it_makes():
    # C200: the CSP had no media-src, so default-src 'self' refused every blob: and data: audio — Aurora's voice and the
    # silence that unlocks the player; every play() failed, on every device, and was said as «the browser blocked it»
    src = (ROOT / "aurora" / "net_https.py").read_text()                 # the Caddyfile's template
    csp = re.search(r'Content-Security-Policy "([^"]+)"', src).group(1)
    media = next(d for d in csp.split("; ") if d.startswith("media-src"))
    assert "blob:" in media and "data:" in media

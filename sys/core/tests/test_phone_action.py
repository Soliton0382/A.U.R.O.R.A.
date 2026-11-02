# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N68: the agent's actions on the owner's phone, checked before they reach the app."""
from datetime import datetime

from aurora import agt_phone


def test_each_action_in_the_app_s_form():
    a = agt_phone.prepare({"action": "alarm", "hour": 7, "minute": 30})
    assert a["action"] == "alarm" and a["hour"] == 7 and a["minute"] == 30 and len(a["id"]) == 12
    assert agt_phone.said(a) == "⏰ sveglia alle 07:30"
    t = agt_phone.prepare({"action": "timer", "seconds": 600})
    assert agt_phone.said(t) == "⏱️ timer di 10 min"
    c = agt_phone.prepare({"action": "calendar", "title": "Cena", "start": "2026-11-08T20:00"})
    assert c["begin_ms"] == int(datetime(2026, 11, 8, 20, 0).timestamp() * 1000)
    assert c["end_ms"] - c["begin_ms"] == 3600_000
    m = agt_phone.prepare({"action": "message", "contact": "Marco", "text": "arrivo", "via": "whatsapp"})
    assert m["via"] == "whatsapp" and m["number"] == "" and m["contact"] == "Marco"
    assert agt_phone.prepare({"action": "call", "number": "+39 333 12 34"})["number"] == "+393331234"


def test_what_the_phone_must_not_get():
    assert agt_phone.prepare({"action": "format_disk"}).startswith("ERROR")
    assert agt_phone.prepare({"action": "open_url", "url": "javascript:alert(1)"}).startswith("ERROR")
    assert agt_phone.prepare({"action": "alarm", "hour": 25}).startswith("ERROR")
    assert agt_phone.prepare({"action": "timer", "seconds": 0}).startswith("ERROR")
    assert agt_phone.prepare({"action": "call"}).startswith("ERROR")
    assert agt_phone.prepare({"action": "web_search", "query": " "}).startswith("ERROR")
    assert agt_phone.prepare({"action": "calendar", "title": "x", "start": "sabato"}).startswith("ERROR")


def test_the_phone_acts_only_when_the_owner_asked(cfg):
    from aurora.agt_loop import Agent

    class P:
        pass
    a = Agent.__new__(Agent)
    a.cfg, a.asked, a.host = cfg, False, None
    sent = []
    import aurora.sys_anon as anon
    orig = anon.refusal
    anon.refusal = lambda *x: ""
    try:
        out = a._call("phone_action", {"action": "alarm", "hour": 7}, {}, lambda e, p: sent.append(e), "r")
        assert out.startswith("ERROR") and not sent
        a.asked = True
        out = a._call("phone_action", {"action": "alarm", "hour": 7}, {}, lambda e, p: sent.append((e, p)), "r")
        assert out.startswith("SENT") and sent[0][0] == "phone.action" and sent[0][1]["hour"] == 7
    finally:
        anon.refusal = orig


def test_the_plain_commands_are_understood_at_once_and_the_rest_goes_to_aurora():
    """⚡ agt_phone.quick(), the call's way in: no model for «apri YouTube» (the agent took 15–92 s to choose the tool, 1 Nov)."""
    cases = {"Apri YouTube.": {"action": "open_app", "app": "YouTube"},
             "Puoi aprire YouTube?": {"action": "open_app", "app": "YouTube"},
             "Metti un timer di 5 minuti.": {"action": "timer", "seconds": 300, "label": "Aurora"},
             "timer di un'ora": {"action": "timer", "seconds": 3600, "label": "Aurora"},
             "Svegliami domani alle 6 e mezza": {"action": "alarm", "hour": 6, "minute": 30, "label": "Aurora"},
             "sveglia alle 7:45": {"action": "alarm", "hour": 7, "minute": 45, "label": "Aurora"},
             "Portami in via Roma 3 a Lodi.": {"action": "navigate", "destination": "via Roma 3 a Lodi"},
             "Chiama il 3331234567": {"action": "call", "number": "3331234567"},
             "Scrivi a Marco su WhatsApp che arrivo tra 10 minuti":
                 {"action": "message", "contact": "Marco", "text": "arrivo tra 10 minuti", "via": "whatsapp"},
             "Cerca su internet orari museo": {"action": "web_search", "query": "orari museo"},
             "apri il cancello": None, "Accendi la luce": None, "Che tempo fa domani?": None,
             "Spiegami la relatività": None}
    out = {s: agt_phone.quick(s) for s in cases}
    assert {s: (a and {k: v for k, v in a.items() if k != "id"}) for s, a in out.items()} == cases
    assert all(len(a["id"]) == 12 for a in out.values() if a)


class _Said:
    def __init__(self, text):
        self.answer = text


class _Model:
    """The local reasoner, answering as it was measured (M273), or failing."""
    def __init__(self, out):
        self.out, self.asked = out, []

    def complete(self, system, user, max_tokens, think=False):
        self.asked.append(user)
        if isinstance(self.out, Exception):
            raise self.out
        return _Said(self.out)


def test_what_the_patterns_miss_is_read_by_the_model_and_checked():
    """The owner, 2 Nov: a WhatsApp message said in their own words went to the agent and nothing opened."""
    m = agt_phone.understand(_Model('{"action":"message","contact":"Lia","text":"Arrivo tra dieci minuti",'
                                    '"via":"whatsapp"}'), "manda un whatsapp a Lia dicendole che arrivo tra dieci minuti")
    assert m["action"] == "message" and m["via"] == "whatsapp" and m["contact"] == "Lia" and len(m["id"]) == 12
    assert agt_phone.understand(_Model("NONE"), "come stai?") is None
    assert agt_phone.understand(_Model('{"action":"timer","seconds":0}'), "x") is None          # checked: refused
    assert agt_phone.understand(_Model('{"action":"calendar","title":"x","start":"2026-11-05T10:00"}'), "x") is None
    assert agt_phone.understand(_Model("{not json"), "x") is None
    assert agt_phone.understand(_Model(RuntimeError("off")), "x") is None                     # the reasoner off


def test_a_long_answer_is_said_as_its_gist_and_a_short_one_as_it_is():
    from aurora import sys_call
    m = _Model("Timer impostato per 60 secondi.")
    long = "✅ Fatto!\n\n**Riepilogo:**\n- strumento: timer\n- 18,9 s, 2 passi\n\nSe vuoi posso fare altro!"
    assert sys_call.spoken(m, long) == "Timer impostato per 60 secondi." and m.asked == [long]
    m = _Model("unused")
    assert sys_call.spoken(m, "Il cancello è aperto.") == "Il cancello è aperto." and m.asked == []
    assert sys_call.spoken(_Model(RuntimeError("off")), "Uno. Due. Tre. Quattro.") == "Uno. Due."

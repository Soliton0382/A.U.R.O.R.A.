# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C526: a sentence the server builds is in the language of whoever reads it (their choice in the WebUI), not in the
machine's AURORA_LANG_DEFAULT, and never in one language only."""
import dataclasses
import json
import re
from pathlib import Path

import pytest

from aurora import sec_audit, sec_playbook, sys_config, sys_lang

AURORA = Path(sys_lang.__file__).parent


@pytest.fixture
def readers(cfg):
    """An Italian machine with two people: «anna» chose English, «luca» chose nothing."""
    cfg.values["AURORA_LANG_DEFAULT"] = "it_IT"
    cfg.path("AURORA_STATUS_DIR").mkdir(parents=True, exist_ok=True)
    (cfg.path("AURORA_STATUS_DIR") / "ui_prefs.json").write_text(json.dumps({"anna": {"lang": "en_US"}}))
    return dataclasses.replace(cfg, user="anna", base=cfg), dataclasses.replace(cfg, user="luca", base=cfg)


def serving(monkeypatch, who):
    """The process serves `who`: what sys_config.get() answers inside their request."""
    monkeypatch.setattr(sys_config, "_cached", who)


def test_the_reader_s_choice_wins_over_the_machine_s_language(readers):
    anna, luca = readers
    assert sys_lang.reader(anna) == "en" and sys_lang.reader(luca) == "it"
    assert sys_lang.say("ciao", "hello", anna) == "hello" and sys_lang.say("ciao", "hello", luca) == "ciao"
    luca.base.values["AURORA_LANG_DEFAULT"] = "en_US"           # an English machine: who chose nothing reads English
    luca.values["AURORA_LANG_DEFAULT"] = "en_US"
    assert sys_lang.reader(luca) == "en"


def test_a_choice_made_later_is_read_at_once(readers):
    anna, luca = readers
    assert sys_lang.reader(luca) == "it"
    f = luca.base.path("AURORA_STATUS_DIR") / "ui_prefs.json"
    f.write_text(json.dumps({"anna": {"lang": "en_US"}, "luca": {"lang": "en_US", "theme": "dark"}}))
    assert sys_lang.reader(luca) == "en"
    f.write_text("not json")                                    # a broken file: the machine's language, never a crash
    assert sys_lang.reader(anna) == "it"


def test_choosing_a_word_never_loads_a_configuration(monkeypatch):
    monkeypatch.setattr(sys_config, "_cached", None)
    monkeypatch.setattr(sys_config, "load", lambda *a, **k: pytest.fail("a configuration was loaded to choose a word"))
    assert sys_lang.reader() == "it" and sys_lang.say("sì", "yes") == "sì"


CONF = {"kind": "test", "rules": [], "nat": [], "wan_admin": ["HTTPS"], "wan_services": [], "ips_policies": [],
        "threat": {"what": "IPS", "state": "off"}, "login": {"lockout": False}, "syslog": []}


def test_the_firewall_audit_is_written_for_who_reads_it(readers, monkeypatch):
    anna, luca = readers
    monkeypatch.setattr(sec_audit.sec_fwmodel, "is_model", lambda x: True)
    serving(monkeypatch, luca)
    it = sec_audit.zones(CONF) + sec_audit.threat(CONF)
    serving(monkeypatch, anna)
    en = sec_audit.zones(CONF) + sec_audit.threat(CONF)
    assert [f["id"] for f in it] == [f["id"] for f in en] == ["admin_wan", "ids", "login"]   # the same findings
    assert "raggiungibile da Internet" in it[0]["title"] and "togliere HTTPS" in it[0]["fix"]
    assert "reached from the Internet" in en[0]["title"] and "remove HTTPS" in en[0]["fix"]
    italian = re.compile(r"\b(il|la|non|del|della|che|dalla|attivare|spenta)\b")
    assert not any(italian.search(f[k]) for f in en for k in ("title", "why", "fix"))        # no page half in each
    assert sec_audit.text({"findings": en, "counts": {"high": 2, "medium": 1, "low": 0}}).startswith("🛡️ Firewall audit")
    serving(monkeypatch, luca)
    assert sec_audit.text({"findings": it, "counts": {"high": 2, "medium": 1, "low": 0}}).startswith("🛡️ Audit del firewall")


def test_a_playbook_has_the_same_steps_in_both_languages(readers, monkeypatch):
    anna, luca = readers
    assert sec_playbook.PLAYBOOKS_IT.keys() == sec_playbook.PLAYBOOKS_EN.keys()
    for k, pb in sec_playbook.PLAYBOOKS_IT.items():
        assert len(pb["steps"]) == len(sec_playbook.PLAYBOOKS_EN[k]["steps"])
    group = {"who": "10.0.0.7", "scenario": "compromised", "severity": "high", "signals": []}
    serving(monkeypatch, anna)
    assert sec_playbook.playbooks()["admin"]["title"] == "The firewall's administration was touched"
    assert "What to do:" in sec_playbook.text([group], []) and "quarantine" in sec_playbook.register(None, [group])[0]["fix"]
    serving(monkeypatch, luca)
    assert "Cosa fare:" in sec_playbook.text([group], []) and "quarantena" in sec_playbook.register(None, [group])[0]["fix"]


def test_a_user_told_by_another_reads_their_own_language(readers, monkeypatch):
    """The administrator (Italian) enters anna's account: the notice is hers, in English."""
    from aurora import sys_context
    anna, luca = readers
    monkeypatch.setattr(sys_config, "_cached", luca)
    monkeypatch.setattr(sys_config, "get", lambda: anna if sys_context.user() == "anna" else luca)
    assert sys_lang.say("uscito", "left") == "uscito"
    with sys_context.acting_as("anna"):
        assert sys_lang.say("uscito", "left") == "left"


def test_the_api_asks_the_reader_never_the_machine():
    """What a page shows is chosen by sys_lang; AURORA_LANG_DEFAULT is left to what the machine itself does."""
    machine = {"kno_sources.py", "kno_shadow.py", "kno_morning.py", "sys_lang.py", "sys_push.py"}
    left = [str(f.relative_to(AURORA)) for f in sorted(AURORA.rglob("*.py"))
            if "AURORA_LANG_DEFAULT" in f.read_text(encoding="utf-8") and f.name not in machine and "local" not in f.parts]
    assert left == []


def test_a_collimation_s_steps_keep_their_codes_in_both_languages(readers, monkeypatch):
    from aurora import ast_ocal
    anna, luca = readers
    o = {"secondary": {"x": 500, "y": 500, "r": 200, "round": 0.9, "round_err": 0.0}, "shadow": {"x": 500, "y": 500, "r": 60}}
    serving(monkeypatch, luca)
    it = ast_ocal.verdict(o)
    serving(monkeypatch, anna)
    en = ast_ocal.verdict(o)
    assert [v["code"] for v in it] == [v["code"] for v in en] and [v["ok"] for v in it] == [v["ok"] for v in en]
    assert "secondario ovale" in it[0]["text"] and "the secondary is oval" in en[0]["text"]
    assert not any(re.search(r"\b(il|del|non|nella)\b", v["text"]) for v in en)


def test_an_error_of_the_api_has_its_sentence_in_both_tables():
    """The detail of an HTTP error is English, the API's own; the WebUI shows it in the reader's language when its
    tables know the sentence («err.<sentence>», i18n.said) — and a sentence listed there is one the API still says."""
    web = AURORA.parent / "webui"
    it = json.loads((web / "i18n/it_IT.json").read_text(encoding="utf-8"))
    en = json.loads((web / "i18n/en_US.json").read_text(encoding="utf-8"))
    errs = {k[4:] for k in it if k.startswith("err.")}
    assert errs and errs == {k[4:] for k in en if k.startswith("err.")}
    assert all(en["err." + e] == e and it["err." + e] != e for e in errs)
    api = "\n".join(f.read_text(encoding="utf-8") for f in sorted((AURORA / "api").glob("*.py")))
    js = (web / "js/api.js").read_text(encoding="utf-8")
    # a sentence built with values names their places ({key}): its longest fixed piece is still in the API's code
    piece = lambda e: max(re.split(r"\{\w+\}", e), key=len)
    assert sorted(e for e in errs - {"unauthorized"} if "{" not in e and f'"{e}"' not in api and f'"{e}"' not in js) == []
    assert sorted(e for e in errs if "{" in e and piece(e) not in api) == []
    assert all(set(re.findall(r"\{\w+\}", e)) == set(re.findall(r"\{\w+\}", it["err." + e])) for e in errs)
    assert "said(body.detail)" in js and "err.${detail}" in (web / "js/i18n.js").read_text(encoding="utf-8")


INVENTORY = {"rig": {"guiding": {"ratio": 7.0}}, "darks": [], "script": 2, "nina_errors": [],
             "phd2": {"logs": [], "latest_log": ""}, "links": {}}


def test_an_inventory_s_checks_are_told_apart_by_code_in_any_language(readers, monkeypatch):
    from aurora import ast_inventory
    anna, luca = readers
    serving(monkeypatch, luca)
    it = ast_inventory._checks(INVENTORY)
    serving(monkeypatch, anna)
    en = ast_inventory._checks(INVENTORY)
    codes = ["no_darks_folder", "no_guide_log", "guide_scale", "links_unread", "no_scale"]
    assert [c["code"] for c in it] == [c["code"] for c in en] == codes
    assert it[1]["what"] == ast_inventory.NO_GUIDE_LOG and en[1]["what"] == "No useful PHD2 guide log"
    assert not any(re.search(r"\b(il|la|del|non|nella|senza)\b", c["what"] + " " + c["why"]) for c in en)
    # what hides a check reads its code: the English reader's list loses the same line as the Italian one
    hide = lambda checks: [c["code"] for c in checks if c.get("code") != "no_guide_log"]
    assert hide(it) == hide(en) == [c for c in codes if c != "no_guide_log"]
    assert ast_inventory.text(None).startswith("No inventory")
    serving(monkeypatch, luca)
    assert ast_inventory.text(None).startswith("Nessun inventario")


def test_a_check_of_the_health_keeps_its_name_and_changes_only_its_words(readers, monkeypatch):
    """An alert is told from another by the check's name (health_change), so the words may follow the reader."""
    import time
    from aurora import sys_health
    anna, luca = readers
    for c in (anna, luca, luca.base):
        c.values["AURORA_SENTINEL_ALLOW"] = ["192.0.2.1"]
    log = luca.base.path("AURORA_LOG_DIR") / "firewall" / "firewall.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("x")
    later = time.time() + 3600
    serving(monkeypatch, luca)
    it = sys_health.syslog_silence(luca, later)
    serving(monkeypatch, anna)
    en = sys_health.syslog_silence(anna, later)
    assert "Aurora non vede la rete" in it[0] and "Aurora does not see the network" in en[0]
    assert "192.0.2.1" in it[1] and "192.0.2.1" in en[1]
    down_it = [{"name": "syslog firewall", "level": "down", "text": it[0]}]
    down_en = [{"name": "syslog firewall", "level": "down", "text": en[0]}]
    assert sys_health.health_change(down_it, set())[0] == "health.down"
    assert sys_health.health_change(down_en, {"syslog firewall"}) is None        # the same alert, said once

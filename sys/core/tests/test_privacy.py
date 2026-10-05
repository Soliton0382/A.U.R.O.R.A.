# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A post's privacy check (owner, 2026-10-05): private names, places and personal data found, the sure ones replaced."""
from types import SimpleNamespace

from aurora import sec_privacy

POST = "Stanotte ho sognato le stelle. Giulia mi ha chiesto perché brillano; Einstein diceva di immaginare, a Roma."


class Reader:
    """A local model that reads the names as the real one did (M104)."""
    def complete(self, system, user, max_tokens, think=False):
        return SimpleNamespace(answer='[{"name": "Giulia", "type": "private"}, {"name": "Einstein", "type": "public"},'
                                      ' {"name": "Roma", "type": "place"}]')


class Down:
    def complete(self, *a, **k):
        raise ConnectionError("the model is down")


def test_private_people_are_replaced_famous_ones_kept_places_proposed(cfg):
    found = {f["value"]: f for f in sec_privacy.findings(POST, cfg, "it", Reader())}
    assert found["Giulia"]["sure"] and found["Giulia"]["replacement"] == "una persona a me cara"
    assert "Einstein" not in found and not found["Roma"]["sure"]
    fixed = sec_privacy.propose(POST, [f for f in found.values() if f["sure"]])
    assert "Giulia" not in fixed and "Einstein" in fixed and "Roma" in fixed


def test_contacts_and_the_owners_own_words_are_always_found(cfg):
    cfg.values["AURORA_OWNER_NAME"] = "Ada"
    cfg.values["AURORA_CLOUD_MASK_WORDS"] = "Lovelace"
    text = "Ada Lovelace scrive a ada@example.org, telefono +39 333 123 4567."
    kinds = {f["value"]: f["kind"] for f in sec_privacy.findings(text, cfg, "it", Reader())}
    assert kinds["ada@example.org"] == "EMAIL" and kinds["+39 333 123 4567"] == "PHONE"
    assert kinds["Ada"] == "PERSON" and kinds["Lovelace"] == "PERSON"
    assert "Ada" not in sec_privacy.propose(text, sec_privacy.findings(text, cfg, "en", Reader()))


def test_without_the_model_a_rule_marks_possible_names_unticked(cfg):
    found = {f["value"]: f for f in sec_privacy.findings("Ho parlato con Zorbaxian della luce.", cfg, "it", Down())}
    assert found["Zorbaxian"]["kind"] == "NAME?" and not found["Zorbaxian"]["sure"]
    assert sec_privacy.findings("Aurora sogna la luce.", cfg, "it", Down()) == []

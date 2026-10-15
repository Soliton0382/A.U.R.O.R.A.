# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Who manages what (owner, 16 Oct: «alcune cose le controlla solo l'admin mentre altre può decidere se farle gestire
agli utenti o meno»)."""
from pathlib import Path

import pytest

from aurora import sys_users_perm as P

API = Path(__file__).resolve().parents[1] / "aurora" / "api"


def test_the_admin_always_a_user_by_the_admin_s_choice_or_the_area_s_default(cfg):
    assert P.may(cfg, "boss", "routines", "boss") and P.may(cfg, None, "settings", None)
    assert P.may(cfg, "alice", "routines", "boss") and not P.may(cfg, "alice", "autonomy", "boss")
    P.set_(cfg, "alice", "routines", False)
    assert not P.may(cfg, "alice", "routines", "boss") and P.may(cfg, "bob", "routines", "boss")
    P.set_(cfg, "alice", "autonomy", True)                        # kept where the autonomy keeps it
    assert P.may(cfg, "alice", "autonomy", "boss")
    t = P.table(cfg, ["boss", "alice"], "boss")
    assert list(t["users"]) == ["alice"] and t["users"]["alice"] == {"routines": False, "settings": True, "autonomy": True}
    with pytest.raises(KeyError):
        P.may(cfg, "alice", "firewalls", "boss")                     # the machine's: never delegated


def test_the_routes_ask_for_it():
    routines = (API / "routines.py").read_text(encoding="utf-8")
    assert routines.count('Depends(may_manage("routines"))') == 5
    assert 'sys_users_perm.may(cfg, user, "settings", admin)' in (API / "system.py").read_text(encoding="utf-8")


def test_her_character_and_the_name_are_always_the_person_s_own():
    """Owner, 16 Oct: the personality chosen at installation, made each user's — also on the first run."""
    import json
    schema = {s["key"]: s for s in json.loads((API.parents[1] / "config" / "settings_schema.json").read_text(encoding="utf-8"))["settings"]}
    assert all(schema[k].get("scope") == "user" for k in P.PERSONAL)
    assert "set(mine) - set(sys_users_perm.PERSONAL)" in (API / "system.py").read_text(encoding="utf-8")
    welcome = (API.parents[1] / "webui" / "js" / "welcome.js").read_text(encoding="utf-8")
    assert '["persona",' in welcome and "AURORA_PERSONALITY" in welcome
    choices = schema["AURORA_PERSONALITY"]["choices"]
    assert all(f'"{c}"' in welcome for c in choices)                 # the screen offers every character there is

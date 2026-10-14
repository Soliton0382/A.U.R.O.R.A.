# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Cloud accounts per installation or per user (ROADMAP 106): the admin's policy decides, a Claude subscription signs
in from the page (a fake `claude` here), nothing changes for an installation without accounts."""
import dataclasses
import os
import stat
import sys

import pytest

from aurora import mdl_accounts as A

FAKE = r'''#!{py}
import json, os, sys
d = os.environ["CLAUDE_CONFIG_DIR"]
f = os.path.join(d, "creds.json")
if sys.argv[1:3] == ["auth", "status"]:
    ok = os.path.exists(f)
    print(json.dumps({{"loggedIn": ok, "email": "anna@example.org" if ok else None, "subscriptionType": "pro" if ok else None}}))
elif sys.argv[1:3] == ["auth", "login"]:
    print("Opening browser to sign in…")
    print("If the browser didn't open, visit: \x1b]8;;https://claude.example/oauth/authorize?code=true&state=x\x07link\x1b]8;;\x07")
    print("Paste code here if prompted > ", end="", flush=True)
    code = sys.stdin.readline().strip()
    if code == "GOOD-CODE":
        open(f, "w").write("{{}}")
'''


def as_user(cfg, name, monkeypatch, admin="boss"):
    monkeypatch.setattr(A, "_admin", lambda c: admin)
    return dataclasses.replace(cfg, user=name, base=cfg)


def test_without_accounts_nothing_changes(cfg, monkeypatch):
    anna = as_user(cfg, "anna", monkeypatch)
    cfg.values["AURORA_OPENAI_API_KEY"] = "sk-machine-1234"
    assert A.pick(anna, "openai") is A.LEGACY and A.key_for(anna, "openai", "AURORA_OPENAI_API_KEY") == "sk-machine-1234"
    assert A.claude_env(anna) == {}                                     # the service user's own claude login


def test_the_policy_decides_whose_account_a_user_spends(cfg, monkeypatch):
    anna, boss = as_user(cfg, "anna", monkeypatch), dataclasses.replace(cfg, user="boss", base=cfg)
    shared = A.add(cfg, "openai", "shared", "boss", key="sk-shared-0001")
    own = A.add(cfg, "openai", "user", "anna", key="sk-anna-0002")
    assert A.key_for(anna, "openai", "X") == "sk-shared-0001"           # «shared»: one for all, as before
    A.set_policy(cfg, "own")
    assert A.key_for(anna, "openai", "X") == "sk-anna-0002" and A.key_for(boss, "openai", "X") == "sk-shared-0001"
    assert A.pick(as_user(cfg, "luca", monkeypatch), "openai") is None   # no account of his: the local model
    A.set_policy(cfg, "own_else_shared")
    assert A.pick(as_user(cfg, "luca", monkeypatch), "openai")["id"] == shared["id"]
    seen = A.visible(cfg, "luca", admin=False)
    assert [a["id"] for a in seen] == [shared["id"]] and seen[0]["key"] == "…0001"   # never another's, never whole
    assert {a["id"] for a in A.visible(cfg, "boss", admin=True)} == {shared["id"], own["id"]}
    assert stat.S_IMODE(os.stat(A._file(cfg)).st_mode) == 0o600
    with pytest.raises(ValueError):
        A.add(cfg, "openai", "user", "anna", key="")                    # a provider with a key needs it
    with pytest.raises(ValueError):
        A.set_policy(cfg, "everyone")


def test_the_router_gives_the_local_model_to_a_user_without_an_account(cfg, monkeypatch):
    from aurora import mdl_router
    A.add(cfg, "openai", "shared", "boss", key="sk-shared-0001")
    A.set_policy(cfg, "own")
    luca = as_user(cfg, "luca", monkeypatch)
    assert not mdl_router.configured("openai", luca) and mdl_router.cloud_client("openai", "gpt", luca) is None
    assert not mdl_router.configured("claude_code", luca)


@pytest.mark.skipif(sys.platform == "win32", reason="the sign-in runs the CLI in a terminal of its own (pty)")
def test_a_claude_subscription_signs_in_from_the_page(cfg, monkeypatch, tmp_path):
    fake = tmp_path / "claude"
    fake.write_text(FAKE.format(py=sys.executable), encoding="utf-8")
    fake.chmod(0o755)
    cfg.values["AURORA_CLAUDE_CODE_BIN"] = str(fake)
    a = A.add(cfg, "claude_code", "user", "anna")
    folder = A.claude_dir(cfg, a["id"])
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700 and not A.status(cfg, a["id"])["logged_in"]
    url = A.login_start(cfg, a["id"])
    assert url == "https://claude.example/oauth/authorize?code=true&state=x"
    st = A.login_finish(cfg, a["id"], "GOOD-CODE")
    assert st == {"logged_in": True, "email": "anna@example.org", "plan": "pro"}
    A.set_policy(cfg, "own")
    assert A.claude_env(as_user(cfg, "anna", monkeypatch)) == {"CLAUDE_CONFIG_DIR": str(folder)}
    with pytest.raises(RuntimeError, match="no login waiting"):
        A.login_finish(cfg, a["id"], "GOOD-CODE")
    A.remove(cfg, a["id"])
    assert not folder.exists()                                          # the credentials go with the account
    with pytest.raises(ValueError):
        A.claude_dir(cfg, "../../etc")

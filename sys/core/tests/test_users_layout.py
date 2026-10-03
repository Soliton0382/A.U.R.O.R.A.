# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""U2: the per-user layout (usr/<name>/ with today's tree; sys areas under users/<name>/), the migration, its rollback,
the purge of a user, and the owner's papers never touched (a fake installation in tmp)."""
import gzip
import json

import pytest

from aurora import sys_users_layout as L
from aurora.sys_devices import Devices
from aurora.sys_users import Users


def tree(cfg) -> dict:
    """Every file under usr/ and the personal sys areas, with its bytes."""
    out = {}
    for base in (cfg.root / "usr", cfg.path("AURORA_VAULT_DIR"), cfg.path("AURORA_STATUS_DIR")):
        for f in sorted(base.rglob("*")) if base.exists() else []:
            if f.is_file() and f.name not in ("users.db", "devices.json", L.STATE):
                out[str(f.relative_to(cfg.root))] = f.read_bytes()
    return out


def today_layout(cfg):
    for key in ("AURORA_UPLOADS_DIR", "AURORA_DOCUMENTS_DIR", "AURORA_IMAGE_DIR"):
        cfg.values[key] = f"usr/{key.split('_')[1].lower()}"
    usr = cfg.root / "usr"
    (usr / "uploads" / "2026-10").mkdir(parents=True)
    (usr / "uploads" / "2026-10" / "a-photo.png").write_bytes(b"png")
    (usr / "documents" / "papers").mkdir(parents=True)
    (usr / "documents" / "papers" / "brevetto.pdf").write_bytes(b"the owner's patent")
    (usr / "documents" / "report.pdf").write_bytes(b"pdf")
    (usr / "test_area").mkdir()
    (usr / "test_area" / "x.txt").write_text("owner's folder")
    mem = cfg.path("AURORA_VAULT_DIR") / "memory" / "conversation"
    mem.mkdir(parents=True)
    (mem / "0001.db").write_bytes(b"turns")
    (cfg.path("AURORA_VAULT_DIR") / "knowledge" / "physics").mkdir(parents=True)
    (cfg.path("AURORA_VAULT_DIR") / "knowledge" / "physics" / "0001.db").write_bytes(b"shared knowledge")
    st = cfg.path("AURORA_STATUS_DIR")
    (st / "push").mkdir(parents=True, exist_ok=True)
    (st / "routines.json").write_text("[]")
    (st / "push" / "subscriptions.json").write_text("[]")
    (st / "plugins.json").write_text("{}")                      # shared: never moves


def test_migrate_moves_today_s_tree_under_the_admin_and_rollback_gives_it_back(cfg):
    today_layout(cfg)
    before = tree(cfg)
    plan = L.migration_plan(cfg, "boss")
    froms = {s["from"].replace(str(cfg.root) + "/", "") for s in plan}
    assert "usr/uploads" in froms and "usr/test_area" in froms and "usr/documents/report.pdf" in froms
    assert not any("papers" in f or "knowledge" in f or "plugins.json" in f for f in froms)
    L.migrate(cfg, "boss")
    usr = cfg.root / "usr"
    assert (usr / "boss" / "uploads" / "2026-10" / "a-photo.png").read_bytes() == b"png"
    assert (usr / "boss" / "documents" / "report.pdf").exists() and (usr / "boss" / "test_area" / "x.txt").exists()
    assert (usr / "documents" / "papers" / "brevetto.pdf").read_bytes() == b"the owner's patent"     # never moved
    assert (cfg.path("AURORA_VAULT_DIR") / "memory" / "users" / "boss" / "conversation" / "0001.db").exists()
    assert (cfg.path("AURORA_STATUS_DIR") / "users" / "boss" / "push" / "subscriptions.json").exists()
    assert L.place(cfg, "uploads", "boss") == usr / "boss" / "uploads"
    assert L.migrate(cfg, "boss") == {"moved": 0, "files": 0}           # a second run moves nothing
    L.rollback(cfg, "boss")
    assert tree(cfg) == before                                            # byte for byte
    assert not (usr / "boss").exists() and not (cfg.path("AURORA_VAULT_DIR") / "memory" / "users").exists()
    assert L.migrated(cfg) is None and L.place(cfg, "uploads", "boss") == usr / "uploads"


def test_the_owner_s_papers_stop_the_rollback_and_the_purge(cfg):
    today_layout(cfg)
    L.migrate(cfg, "boss")
    mine = cfg.root / "usr" / "boss" / "documents" / "papers"
    mine.mkdir()                                                          # the owner moved them into his folder
    (mine / "brevetto.pdf").write_bytes(b"patent")
    with pytest.raises(RuntimeError, match="papers"):
        L.rollback(cfg, "boss")
    assert (mine / "brevetto.pdf").read_bytes() == b"patent"
    theirs = cfg.root / "usr" / "guest" / "documents" / "papers"
    theirs.mkdir(parents=True)
    (theirs / "x.pdf").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="papers"):
        L.purge(cfg, "guest", "boss")
    assert (theirs / "x.pdf").exists()


def test_purge_leaves_nothing_of_the_user(cfg):
    today_layout(cfg)
    users = Users(cfg)
    users.add("boss", "admin", "a long password")
    users.add("guest", "user")
    L.migrate(cfg, "boss")
    (cfg.root / "usr" / "guest" / "uploads").mkdir(parents=True)
    (cfg.root / "usr" / "guest" / "uploads" / "mine.png").write_bytes(b"guest")
    L.home(cfg, L.BY_NAME["memory"], "guest").mkdir(parents=True)
    (L.home(cfg, L.BY_NAME["memory"], "guest") / "0001.db").write_bytes(b"guest turns")
    trace = cfg.path("AURORA_LOG_DIR") / "trace"
    trace.mkdir(parents=True, exist_ok=True)
    (trace / "api.jsonl").write_text(json.dumps({"event": "a", "user": "guest"}) + "\n"
                                     + json.dumps({"event": "b", "user": "boss"}) + "\n")
    with gzip.open(trace / "api.1.jsonl.gz", "wt") as f:
        f.write(json.dumps({"event": "c", "user": "guest"}) + "\n")
    devices = Devices(cfg)
    devices.register("guest phone", "ua")
    items = json.loads(devices.file.read_text())
    items[0]["user"] = "guest"
    devices.file.write_text(json.dumps(items))
    assert {s["what"] for s in L.purge_plan(cfg, "guest")} == {"usr", "memory", "trace"}
    out = L.purge(cfg, "guest", "boss")
    assert out["devices"] == 1 and not any(u["name"] == "guest" for u in users.list())
    assert L.purge_plan(cfg, "guest") == [] and not (cfg.root / "usr" / "guest").exists()
    assert "guest" not in (trace / "api.jsonl").read_text() and "boss" in (trace / "api.jsonl").read_text()
    assert (cfg.root / "usr" / "boss" / "uploads").exists()             # the admin's data untouched
    with pytest.raises(ValueError):
        L.purge(cfg, "boss", "boss")
    users.add("guest2", "user")
    (cfg.root / "usr" / "guest2").mkdir()
    with pytest.raises(RuntimeError, match="other users"):
        L.rollback(cfg, "boss")


def test_names_are_folders_never_paths(cfg):
    cfg.values["AURORA_UPLOADS_DIR"] = "usr/uploads"
    for bad in ("", "../x", "a/b", ".", "..", ".hidden", "uploads", "users", "x" * 41):
        with pytest.raises(ValueError):
            L.usr_home(cfg, bad)
    assert L.usr_home(cfg, "mario.rossi").name == "mario.rossi"


def test_personal_settings_follow_the_admin_and_come_back(cfg):
    """The owner's design: personal settings in usr/<name>/.env; the system's .env keeps the machine's."""
    from aurora import sys_config, sys_user_config as U
    today_layout(cfg)
    sys_config.write_env(cfg.env_file, {"AURORA_TMDB_TOKEN": "tok-123", "AURORA_WEATHER_PLACE": "Casa"})
    cfg = sys_config.load(cfg.env_file, check_root=False)
    system_before = cfg.env_file.read_text()
    assert U.for_user(cfg, "boss") is cfg                                 # before the migration: the same values
    out = L.migrate(cfg, "boss")
    assert out["settings"] == len(U.user_keys(cfg))
    raw = cfg.env_file.read_text()
    assert "AURORA_TMDB_TOKEN" not in raw and "AURORA_LLM_MODEL" in raw  # personal out, the machine's stay
    own = U.env_path(cfg, "boss")
    assert own.stat().st_mode & 0o777 == 0o600 and "AURORA_TMDB_TOKEN=tok-123" in own.read_text()
    cfg = sys_config.load(cfg.env_file, check_root=False)                 # the system's .env still loads
    assert cfg["AURORA_TMDB_TOKEN"] == ""
    mine = U.for_user(cfg, "boss")
    assert mine["AURORA_TMDB_TOKEN"] == "tok-123" and mine["AURORA_WEATHER_PLACE"] == "Casa"
    assert mine.path("AURORA_UPLOADS_DIR") == cfg.root / "usr" / "boss" / "uploads"
    guest = U.for_user(cfg, "guest")
    assert guest["AURORA_TMDB_TOKEN"] == "" and guest.path("AURORA_UPLOADS_DIR") == cfg.root / "usr" / "guest" / "uploads"
    U.write(cfg, "guest", {"AURORA_TMDB_TOKEN": "guest-tok"})
    assert U.for_user(cfg, "guest")["AURORA_TMDB_TOKEN"] == "guest-tok" and U.for_user(cfg, "boss")["AURORA_TMDB_TOKEN"] == "tok-123"
    with pytest.raises(ValueError):
        U.write(cfg, "guest", {"AURORA_LLM_MODEL": "x"})                   # the machine's settings are not a user's
    (cfg.root / "usr" / "guest" / ".env").unlink()
    (cfg.root / "usr" / "guest").rmdir()
    L.rollback(cfg, "boss")
    assert sys_config.parse_env(cfg.env_file.read_text()) == sys_config.parse_env(system_before)
    assert not (cfg.root / "usr" / ".env").exists() and not (cfg.root / "usr" / "boss").exists()


def test_a_plugin_runs_with_the_settings_and_folders_of_its_user(cfg):
    """The plugins are everyone's; the environment a plugin process gets is its user's (sys_user_config.for_user)."""
    from aurora import sys_config, sys_user_config as U
    from aurora.plg_host import PluginHost
    today_layout(cfg)
    sys_config.write_env(cfg.env_file, {"AURORA_TMDB_TOKEN": "boss-token"})
    cfg = sys_config.load(cfg.env_file, check_root=False)
    L.migrate(cfg, "boss")
    cfg = sys_config.load(cfg.env_file, check_root=False)
    U.write(cfg, "guest", {"AURORA_TMDB_TOKEN": "guest-token"})
    from pathlib import Path
    cfg.values["AURORA_PLUGINS_DIR"] = str(Path(__file__).resolve().parents[2] / "plugins")   # the real ones, read only
    for who, token in (("boss", "boss-token"), ("guest", "guest-token")):
        host = PluginHost(U.for_user(cfg, who))
        p = next(x for x in host.plugins(with_tools=False) if x.name == "cinema")
        params = host._params(p)
        assert params.env.get("AURORA_TMDB_TOKEN") == token and params.env["AURORA_PLUGIN"] == "cinema"
        from aurora import plg_sandbox                                  # the .env the plugin reads: its user's
        e = plg_sandbox.env_file("expenses", {"env": [], "settings": []}, U.for_user(cfg, who))
        text = e.read_text()
        assert e.name == f"expenses.{who}.env" and f"AURORA_EXPENSES_DIR=usr/{who}/" in text
        assert "AURORA_TMDB_TOKEN=" in text and token not in text      # another plugin's secret: redacted


def test_a_setting_that_becomes_personal_moves_into_the_admin_s_env(cfg):
    """A key turned `"scope": "user"` after the migration: adopt() moves it, so nothing is left behind or reset."""
    from aurora import sys_config, sys_user_config as U
    today_layout(cfg)
    L.migrate(cfg, "boss")
    sys_config.write_env(U.env_path(cfg, "boss"), {}, drop={"AURORA_TMDB_TOKEN"})       # a key turned personal later:
    sys_config.write_env(cfg.env_file, {"AURORA_TMDB_TOKEN": "left-in-system"})        # not in the admin's .env yet
    cfg = sys_config.load(cfg.env_file, check_root=False)
    assert U.adopt(cfg, "boss") == ["AURORA_TMDB_TOKEN"]
    assert "AURORA_TMDB_TOKEN" not in cfg.env_file.read_text()
    assert U.for_user(sys_config.load(cfg.env_file, check_root=False), "boss")["AURORA_TMDB_TOKEN"] == "left-in-system"
    assert U.adopt(sys_config.load(cfg.env_file, check_root=False), "boss") == []                # nothing twice

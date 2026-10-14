# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Back to the factory (owner, 2026-10-06): settings to their recommended values, the installation's identity and the
keys kept; Aurora's mind moved aside, never usr/."""
from aurora import sys_config, sys_reset


def test_settings_back_keys_and_identity_kept(cfg):
    env = cfg.env_file
    assert "pytest" in str(env)                                                  # C158: never the real .env
    sys_config.write_env(env, {"AURORA_SHADOW_COS": "0.5", "AURORA_API_PORT": "9999"})
    out = sys_reset.settings(cfg, keep_keys=True)
    now = sys_config.parse_env(env.read_text())
    assert "AURORA_SHADOW_COS" in out["changed"] and now["AURORA_SHADOW_COS"] == "0.9"
    assert now["AURORA_API_PORT"] == "9999"                                      # the installation's own port stays
    assert sys_config.parse_env(open(out["backup"]).read())["AURORA_SHADOW_COS"] == "0.5"


def test_the_mind_moves_aside_never_usr(cfg):
    status = cfg.path("AURORA_STATUS_DIR")
    (status / "users" / "ada").mkdir(parents=True)
    (status / "users" / "ada" / "routines.json").write_text("[]")
    (status / "users" / "ada" / "keys").mkdir()
    (cfg.root / "usr" / "ada" / "documents").mkdir(parents=True)
    plan = sys_reset.mind_plan(cfg)
    assert any(p.endswith("users/ada/routines.json") for p in plan["places"])
    assert not any("keys" in p or p.startswith("usr") for p in plan["places"])
    sys_reset.mind(cfg, plan)
    assert not (status / "users" / "ada" / "routines.json").exists() and (status / "users" / "ada" / "keys").exists()
    assert (cfg.root / "usr" / "ada" / "documents").exists()


def test_back_to_the_installation_s_choices_not_the_recommended(cfg):
    # ROADMAP 102: «come appena installata con le configurazioni scelte»
    env = cfg.env_file
    sys_config.write_env(env, {"AURORA_SHADOW_COS": "0.95", "AURORA_TTS": "0"})       # the owner's choices at install
    assert sys_reset.remember_installed(cfg) and not sys_reset.remember_installed(cfg)   # kept once, never rewritten
    sys_config.write_env(env, {"AURORA_SHADOW_COS": "0.5", "AURORA_TTS": "1"})        # changed since
    out = sys_reset.settings(cfg)
    now = sys_config.parse_env(env.read_text())
    assert out["base"] == "installed" and now["AURORA_SHADOW_COS"] == "0.95" and now["AURORA_TTS"] == "0"
    out = sys_reset.settings(cfg, base="recommended")
    assert out["base"] == "recommended" and sys_config.parse_env(env.read_text())["AURORA_SHADOW_COS"] == "0.9"


def test_a_request_from_the_webui_is_taken_once_and_only_fresh(cfg):
    sys_reset.ask(cfg, with_knowledge=False, keep_keys=True, by="ada")
    req = sys_reset.take(cfg)
    assert req["by"] == "ada" and not req["with_knowledge"] and sys_reset.take(cfg) is None
    sys_reset.ask(cfg, True, True, "ada")
    assert sys_reset.take(cfg, max_age_s=-1) is None and not sys_reset.request_file(cfg).exists()   # stale: dropped

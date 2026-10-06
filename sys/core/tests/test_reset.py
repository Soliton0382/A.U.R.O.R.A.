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

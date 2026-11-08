# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C463 (ROADMAP N69 a): a plugin's filtered .env names its own secrets, the values travel in its environment only."""
from aurora import plg_sandbox, sys_config


def test_the_plugins_env_file_holds_no_secret_and_the_plugin_reads_it(cfg, monkeypatch):
    key = "AURORA_HA_TOKEN"                                                    # a secret of the schema
    assert {s["key"]: s for s in sys_config.load_schema()["settings"]}[key].get("secret")
    cfg.raw[key] = cfg.values[key] = "tok-Zanzibar-42"
    f = plg_sandbox.env_file("homeassistant", {"env": [key]}, cfg)
    text = f.read_text()
    assert "Zanzibar" not in text and f"{key}={sys_config.ENV_REF}{key}" in text
    assert "AURORA_TELEGRAM_BOT_TOKEN=redacted" in text or "AURORA_TELEGRAM_BOT_TOKEN=\n" in text   # not its own
    monkeypatch.setenv("AURORA_PLUGIN", "homeassistant")
    monkeypatch.setenv(sys_config.PLUGIN_SECRET + key, "tok-Zanzibar-42")
    inside = sys_config.load(f, check_root=False)
    assert inside[key] == "tok-Zanzibar-42"
    monkeypatch.delenv(sys_config.PLUGIN_SECRET + key)
    assert sys_config.load(f, check_root=False)[key] == ""                     # not given: empty, never the name

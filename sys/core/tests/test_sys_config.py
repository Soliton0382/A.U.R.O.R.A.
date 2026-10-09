# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import os
from pathlib import Path

import pytest

from aurora import sys_config
from conftest import write_env


def test_parse_env_comments_quotes_and_blank_lines():
    values = sys_config.parse_env('# comment\n\nA=1\nB="two words"\nC=\'x\'\n')
    assert values == {"A": "1", "B": "two words", "C": "x"}


@pytest.mark.parametrize("text", ["A=1\nA=2\n", "just text\n", "1BAD=3\n"])
def test_parse_env_refuses_malformed_files(text):
    with pytest.raises(sys_config.ConfigError):
        sys_config.parse_env(text)


def test_load_converts_types(cfg):
    assert cfg["AURORA_CHUNK_CHARS"] == 4000
    assert "AURORA_CLOUD_" + "MASK" not in cfg.values            # the masking is not a setting: always on
    assert cfg["AURORA_CONFIRM_EXTERNAL_ACTIONS"] is True
    assert sys_config.convert({"type": "list"}, " it_IT, en_US,") == ["it_IT", "en_US"]
    assert cfg.path("AURORA_VAULT_DIR") == (cfg.root / "sys" / "vault").resolve()


def test_query_prompt_newline_is_decoded_and_accents_survive(tmp_path):
    env = write_env(tmp_path, AURORA_EMBEDDER_QUERY_PROMPT="Istruzione: perché\\nDomanda:")
    cfg = sys_config.load(env, check_root=False)
    assert cfg["AURORA_EMBEDDER_QUERY_PROMPT"] == "Istruzione: perché\nDomanda:"


def test_every_problem_is_reported_at_once(tmp_path):
    env = write_env(tmp_path, AURORA_CHUNK_CHARS="many", AURORA_LOG_LEVEL="LOUD", AURORA_LOG_MAX_MB="0")
    text = env.read_text().replace("AURORA_FORGE_MODE=ask\n", "")
    env.write_text(text)
    with pytest.raises(sys_config.ConfigError) as err:
        sys_config.load(env, check_root=False)
    msg = str(err.value)
    for key in ("AURORA_CHUNK_CHARS", "AURORA_LOG_LEVEL", "AURORA_LOG_MAX_MB", "AURORA_FORGE_MODE"):
        assert key in msg


def test_relative_and_absolute_paths_are_enforced(tmp_path):
    with pytest.raises(sys_config.ConfigError, match="relative"):
        sys_config.load(write_env(tmp_path, AURORA_VAULT_DIR="/abs/vault"), check_root=False)
    with pytest.raises(sys_config.ConfigError, match="absolute"):
        sys_config.load(write_env(tmp_path, AURORA_ROOT="relative/root"), check_root=False)


def test_root_must_match_where_the_code_runs(tmp_path):
    with pytest.raises(sys_config.ConfigError, match="code runs from"):
        sys_config.load(write_env(tmp_path), check_root=True)


def test_unknown_keys_are_collected_not_fatal(tmp_path):
    env = write_env(tmp_path)
    env.write_text(env.read_text() + "OLD_THING=1\n")
    assert sys_config.load(env, check_root=False).unknown_keys == ["OLD_THING"]


def test_schema_recommended_values_are_valid(tmp_path):
    """The schema must never recommend a value its own rules refuse."""
    sys_config.load(write_env(tmp_path), check_root=False)


def test_real_env_file_is_in_sync_with_the_schema():
    """The installation's own .env must load. Skipped when the file is absent (fresh checkout)."""
    env = Path(sys_config.CODE_ROOT) / ".env"
    if not env.exists():
        pytest.skip("no .env in this checkout")
    sys_config.load(env)


def test_prompts_name_the_owner_from_the_settings(cfg):
    from aurora import sys_config
    cfg.values["AURORA_OWNER_NAME"] = "Ada"
    assert sys_config.personal("Sei l'amica di %OWNER%.", cfg) == "Sei l'amica di Ada."
    assert sys_config.personal("nessun segnaposto {label}", cfg) == "nessun segnaposto {label}"


@pytest.mark.skipif(os.name == "nt", reason="the folder's owner through pwd: Windows takes the installing user (rewrites.py)")
def test_the_service_user_is_the_setting_else_the_owner_of_the_folder(cfg):
    import pwd
    cfg.values["AURORA_SERVICE_USER"] = ""
    assert sys_config.service_user(cfg) == pwd.getpwuid(cfg.root.stat().st_uid).pw_name     # never root by accident
    cfg.values["AURORA_SERVICE_USER"] = "someone"
    assert sys_config.service_user(cfg) == "someone"


def test_a_plugin_process_takes_the_recommended_value_of_a_setting_just_added(cfg, monkeypatch):
    """C142: a key added to the schema before the .env made every plugin die at start ("Connection closed")."""
    from aurora import sys_config
    text = cfg.env_file.read_text()
    key = next(k for k in sys_config.load_schema()["settings"] if not k.get("optional") and k.get("scope") != "user"
               and k["key"] != "AURORA_ROOT")["key"]
    cfg.env_file.write_text("\n".join(l for l in text.splitlines() if not l.startswith(f"{key}=")) + "\n")
    with pytest.raises(sys_config.ConfigError):
        sys_config.load(cfg.env_file, check_root=False)                  # a service still stops: it must be seen
    monkeypatch.setenv("AURORA_PLUGIN", "weather")
    assert key in sys_config.load(cfg.env_file, check_root=False).values


def test_a_rooted_path_is_never_relative():
    """C223: on Windows «/x» is not absolute (Python 3.13+) but rooted — joined to AURORA_ROOT it leaves it."""
    spec = {"type": "path"}
    for raw in ("/etc/x", "\\x", "C:x", "C:/x"):
        with pytest.raises(ValueError, match="relative"):
            sys_config.convert(spec, raw)
    assert sys_config.convert(spec, "sys/vault") == "sys/vault"

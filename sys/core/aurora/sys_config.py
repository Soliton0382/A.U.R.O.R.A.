# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Configuration: the .env file is the only source of values.

- Values are read from the .env file only, never from the process environment,
  so that no second source (systemd drop-ins, shell exports) can silently
  override them. The one exception is AURORA_ENV_FILE, which points to the
  file to read (used by tests and by tools that manage the file).
- Every variable is described in sys/core/config/settings_schema.json. A
  missing variable, a value of the wrong type or a value out of range stops the
  program with a message that lists all the problems at once.
- Paths in .env are relative to AURORA_ROOT. If AURORA_ROOT does not match the
  place the code runs from, loading fails: running with the wrong paths is
  worse than not running.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CODE_ROOT = Path(__file__).resolve().parents[3]           # <root>/sys/core/aurora/sys_config.py
SCHEMA_FILE = CODE_ROOT / "sys" / "core" / "config" / "settings_schema.json"
TRUE_WORDS = {"1", "true", "yes", "on"}
FALSE_WORDS = {"0", "false", "no", "off"}


class ConfigError(Exception):
    """Raised when .env or the schema cannot be used. The message lists every problem."""


def env_file_path() -> Path:
    return Path(os.environ.get("AURORA_ENV_FILE") or CODE_ROOT / ".env")


def load_schema(path: Path = SCHEMA_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)
    keys = [s["key"] for s in schema["settings"]]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ConfigError(f"settings schema {path}: duplicated keys {duplicates}")
    if path == SCHEMA_FILE:                          # the plugins' own settings (a forged plugin's account, token…)
        schema["settings"] += plugin_settings(set(keys))
    return schema


PLUGIN_TYPES = {"str", "bool", "int", "float"}


def plugin_settings(taken: set[str], plugins_dir: Path | None = None) -> list[dict]:
    """The settings a plugin declares in its plugin.json («settings_spec»), as schema entries: each named
    AURORA_<PLUGIN>_…, so a plugin can never redefine a setting of Aurora's or another plugin's; a secret is marked
    and so masked in the pages and never passed to another plugin (owner, 2026-10-07: the forged cloudflare plugin's
    token and account were not configurable)."""
    out = []
    for f in sorted((plugins_dir or CODE_ROOT / "sys" / "plugins").glob("*/plugin.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        prefix = f"AURORA_{str(m.get('name', f.parent.name)).upper()}_"
        for s in m.get("settings_spec") or []:
            key = str(s.get("key", ""))
            if not key.startswith(prefix) or key in taken or not key.replace("_", "").isalnum() or not key.isupper():
                continue
            taken.add(key)
            out.append({"key": key, "type": s.get("type") if s.get("type") in PLUGIN_TYPES else "str",
                        "category": "plugins", "recommended": str(s.get("recommended", "")),
                        "evidence": f"plugin {m.get('name', f.parent.name)}",
                        "en": str(s.get("en") or s.get("it") or key), "it": str(s.get("it") or s.get("en") or key),
                        "services": ["aurora-api"], "optional": True, **({"secret": True} if s.get("secret") else {})})
    return out


def parse_env(text: str, origin: str = ".env") -> dict[str, str]:
    """Strict KEY=VALUE parser: comments, blank lines, optional quotes; no interpolation."""
    values: dict[str, str] = {}
    problems = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            problems.append(f"{origin}:{n}: not KEY=VALUE: {raw!r}")
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key.isidentifier():
            problems.append(f"{origin}:{n}: invalid key {key!r}")
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key in values:
            problems.append(f"{origin}:{n}: {key} defined twice")
            continue
        values[key] = value
    if problems:
        raise ConfigError("\n".join(problems))
    return values


def convert(spec: dict, raw: str) -> Any:
    """Convert one raw string according to its schema entry; raise ValueError with the reason."""
    kind = spec["type"]
    if spec.get("secret") and not raw and not spec.get("optional"):
        raise ValueError("empty secret: run sys/core/script/sys_env_sync.py to generate it")
    if kind in ("str", "path", "path_abs"):
        if kind == "path_abs" and not os.path.isabs(raw):
            raise ValueError("must be an absolute path")
        if kind == "path" and os.path.isabs(raw):
            raise ValueError("must be relative to AURORA_ROOT")
        # only the two escapes a one-line .env value needs; unicode_escape would break accents
        return raw.replace("\\n", "\n").replace("\\t", "\t") if kind == "str" else raw
    if kind == "int":
        value = int(raw)
    elif kind == "float":
        value = float(raw)
    elif kind == "bool":
        low = raw.lower()
        if low not in TRUE_WORDS | FALSE_WORDS:
            raise ValueError("must be 1/0, true/false, yes/no or on/off")
        return low in TRUE_WORDS
    elif kind == "enum":
        if raw not in spec["choices"]:
            raise ValueError(f"must be one of {spec['choices']}")
        return raw
    elif kind == "list":
        return [item.strip() for item in raw.split(",") if item.strip()]
    else:
        raise ValueError(f"unknown type {kind!r} in the schema")
    if "min" in spec and value < spec["min"]:
        raise ValueError(f"below the minimum {spec['min']}")
    if "max" in spec and value > spec["max"]:
        raise ValueError(f"above the maximum {spec['max']}")
    return value


@dataclass
class Config:
    values: dict[str, Any]
    specs: dict[str, dict]
    env_file: Path
    unknown_keys: list[str] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict, repr=False)      # the effective values as written in an .env
    base: "Config | None" = field(default=None, repr=False, compare=False)   # the machine's, under a user's view
    user: str | None = None                                             # whose view (multi-user, U3)

    @property
    def root(self) -> Path:
        return Path(self.values["AURORA_ROOT"])

    def __getitem__(self, key: str) -> Any:
        if key not in self.specs:
            raise KeyError(f"{key} is not declared in the settings schema")
        return self.values[key]

    def path(self, key: str) -> Path:
        """Absolute path for a 'path' setting, resolved against AURORA_ROOT."""
        if self.specs[key]["type"] not in ("path", "path_abs"):
            raise KeyError(f"{key} is not a path setting")
        return (self.root / self.values[key]).resolve()


def load(env_file: Path | None = None, schema_file: Path = SCHEMA_FILE, check_root: bool = True) -> Config:
    env_file = Path(env_file) if env_file else env_file_path()
    if not env_file.is_file():
        raise ConfigError(f"{env_file} not found")
    schema = load_schema(schema_file)
    specs = {s["key"]: s for s in schema["settings"]}
    raw = parse_env(env_file.read_text(encoding="utf-8"), str(env_file))
    if env_file.stat().st_mode & 0o077:              # secrets inside: nobody but the owner may read it
        try:
            env_file.chmod(0o600)
        except OSError:
            pass
    problems, values = [], {}
    for key, spec in specs.items():
        if key not in raw and (spec.get("optional") or spec.get("scope") == "user"):
            raw[key] = spec["recommended"]                 # optional, or a user's (their own .env holds it: U3)
        elif key not in raw and os.environ.get("AURORA_PLUGIN"):
            raw[key] = spec["recommended"]                 # a plugin never dies of a setting just added (C142)
        if key not in raw:
            problems.append(f"{key}: missing in {env_file}")
            continue
        try:
            values[key] = convert(spec, raw[key])
        except ValueError as e:
            problems.append(f"{key}={raw[key]!r}: {e}")
    if check_root and "AURORA_ROOT" in values and Path(values["AURORA_ROOT"]).resolve() != CODE_ROOT:
        problems.append(f"AURORA_ROOT={values['AURORA_ROOT']} but the code runs from {CODE_ROOT}")
    if problems:
        raise ConfigError(f"configuration problems in {env_file}:\n  " + "\n  ".join(problems))
    unknown = sorted(set(raw) - set(specs))
    return Config(values=values, specs=specs, env_file=env_file, unknown_keys=unknown,
                  raw={k: raw[k] for k in specs if k in raw})


_cached: Config | None = None


def write_env(env: Path, changes: dict[str, str], drop: set[str] = frozenset()) -> None:
    """Set `changes` and remove `drop` in an .env file, keeping its comments and order; atomic, mode 600."""
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    out, done = [], set()
    for line in lines:
        k = line.split("=", 1)[0].strip()
        if line.lstrip().startswith("#") or "=" not in line:
            out.append(line)
        elif k in drop:
            continue
        elif k in changes:
            out.append(f"{k}={changes[k]}")
            done.add(k)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in changes.items() if k not in done]
    env.parent.mkdir(parents=True, exist_ok=True)
    tmp = env.with_name(env.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)     # secrets inside: owner only
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, env)


def add_missing(env: Path | None = None, schema: Path = SCHEMA_FILE) -> list[str]:
    """Keys the schema declares and the .env lacks get their recommended value: an update that brings a new setting
    must not stop Aurora (C139). Returns the keys added."""
    env = env or env_file_path()
    current = parse_env(env.read_text(encoding="utf-8")) if env.exists() else {}
    missing = {s["key"]: s["recommended"] for s in load_schema(schema)["settings"]
               if s["key"] not in current and not s.get("optional") and s.get("scope") != "user"}   # a user's own (C141)
    if missing:
        write_env(env, missing)
    return list(missing)


def service_user(cfg: "Config") -> str:
    """The user the services run as: AURORA_SERVICE_USER, else the owner of Aurora's folder (the one who installed
    it). Never the user of the calling process: the NAS mount runs as root (C92)."""
    import pwd
    return str(cfg.values.get("AURORA_SERVICE_USER") or "").strip() or pwd.getpwuid(cfg.root.stat().st_uid).pw_name


def _plugin_user(cfg: Config) -> str | None:
    """The user a plugin's process works for, read from its folders (the filtered .env holds usr/<name>/…), or None."""
    usr = (cfg.root / "usr").resolve()
    for k in ("AURORA_UPLOADS_DIR", "AURORA_HEALTH_DIR", "AURORA_DOCUMENTS_DIR", "AURORA_PROJECTS_DIR"):
        try:
            p = (cfg.root / str(cfg.values.get(k) or "")).resolve()
            rel = p.relative_to(usr)
        except (ValueError, TypeError):
            continue
        if len(rel.parts) >= 2:                       # usr/<name>/<area>: a user's folder, not the shared usr/<area>
            return rel.parts[0]
    return None


def _view(cfg: Config) -> Config:
    """After the migration to the per-user layout a process works as the admin unless told otherwise (U3): their
    settings and folders. A plugin's own process never: its .env is already the filtered one of its user."""
    if os.environ.get("AURORA_PLUGIN"):
        # whose work: its folders are its user's (usr/<name>/…), so is its key — 6 October: a user's health data,
        # sealed with their key, did not open in the plugin, which used the admin's ("the sealed file does not open")
        cfg.user = cfg.user or _plugin_user(cfg)
        return cfg
    from . import sys_user_config, sys_users_layout
    m = sys_users_layout.migrated(cfg)
    return sys_user_config.for_user(cfg, m["admin"]) if m else cfg


def get() -> Config:
    """The configuration of this process (loaded once; the admin's view after the migration), as seen by the user
    whose request is being served (sys_context: their settings and folders)."""
    global _cached
    if _cached is None:
        _cached = _view(load())
    from . import sys_context
    who = sys_context.user()
    if who and who != _cached.user and not os.environ.get("AURORA_PLUGIN"):
        from . import sys_user_config
        return sys_user_config.for_user(_cached, who)
    return _cached


def reload() -> Config:
    global _cached
    _cached = _view(load())
    return _cached


OWNER_MARK = "%OWNER%"


def personal(text: str, cfg: Config | None = None) -> str:
    """Prompts name the owner through AURORA_OWNER_NAME: the code carries only %OWNER%, never a person's name."""
    return text.replace(OWNER_MARK, (cfg or get())["AURORA_OWNER_NAME"]) if OWNER_MARK in text else text

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The settings: the .env holds the values, sys/evidentia/config/settings_schema.json describes them (as Aurora). A key the
schema does not know is refused; a missing one takes the schema's recommended value. Paths relative to the project."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(os.environ.get("EVD_ROOT") or Path(__file__).resolve().parents[3])
SCHEMA = ROOT / "sys" / "evidentia" / "config" / "settings_schema.json"


class ConfigError(Exception):
    pass


def schema() -> dict[str, dict]:
    return {s["key"]: s for s in json.loads(SCHEMA.read_text(encoding="utf-8"))["settings"]}


def parse_env(text: str) -> dict[str, str]:
    out = {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f".env line {n}: KEY=VALUE expected")
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


@dataclass
class Config:
    values: dict[str, str] = field(default_factory=dict)
    root: Path = ROOT

    def __getitem__(self, key: str):
        spec = schema()[key]
        raw = self.values.get(key, spec.get("recommended", ""))
        return int(raw) if spec["type"] == "int" else raw

    def path(self, key: str) -> Path:
        if not str(self[key]).strip():                  # a machine's own folder, never a default in the repo (B23)
            raise ConfigError(f"{key} is not set: write it in the .env")
        p = Path(self[key])
        return p if p.is_absolute() else self.root / p


def load(env_file: Path | None = None) -> Config:
    f = env_file or Path(os.environ.get("EVD_ENV_FILE") or ROOT / ".env")
    values = parse_env(f.read_text(encoding="utf-8")) if f.is_file() else {}
    unknown = sorted(set(values) - set(schema()))
    if unknown:
        raise ConfigError(f"settings the schema does not describe: {', '.join(unknown)}")
    for k, spec in schema().items():
        if spec["type"] == "int" and k in values and not values[k].lstrip("-").isdigit():
            raise ConfigError(f"{k}: a whole number expected, not {values[k]!r}")
    if os.environ.get("EVD_DATA_OVERRIDE"):         # R15: an inventory started for a user writes that user's archive
        values["EVD_DATA_DIR"] = os.environ["EVD_DATA_OVERRIDE"]
    return Config(values)

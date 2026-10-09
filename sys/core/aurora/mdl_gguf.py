# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What a GGUF file says about its model, read from its header only (read only: the models are never written).

The facts a local model brings with it (owner, 9 Oct: «se uno lo vuole cambiare con un modello suo»): its
architecture, its name, whether it is a mixture of experts and how many experts it uses, its context, and the chat
template it was trained with — the one llama.cpp applies with --jinja. Large arrays (the vocabulary) are skipped.

    meta(path) -> {"architecture", "name", "experts", "experts_used", "context", "chat_template", "size_gb", ...}
"""
from __future__ import annotations

import struct
from pathlib import Path

MAGIC = b"GGUF"
SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
STRING, ARRAY = 8, 9
KEEP_ARRAY = 64                     # arrays longer than this (the vocabulary, its scores) are skipped, not read


class NotGGUF(ValueError):
    pass


def _read(f, fmt: str):
    size = struct.calcsize(fmt)
    data = f.read(size)
    if len(data) != size:
        raise Short("the header ends early")
    return struct.unpack(fmt, data)[0]


def _string(f) -> str:
    n = _read(f, "<Q")
    if n > 1 << 24:
        raise NotGGUF(f"a string of {n} bytes in the header")
    data = f.read(n)
    if len(data) != n:
        raise Short("the header ends early")
    return data.decode("utf-8", errors="replace")


def _value(f, kind: int):
    if kind in SCALAR:
        return _read(f, SCALAR[kind])
    if kind == STRING:
        return _string(f)
    if kind == ARRAY:
        sub, n = _read(f, "<I"), _read(f, "<Q")
        if n <= KEEP_ARRAY:
            return [_value(f, sub) for _ in range(n)]
        if sub in SCALAR:                                          # skipped at once
            f.seek(n * struct.calcsize(SCALAR[sub]), 1)
        else:
            for _ in range(n):
                _value(f, sub)
        return None
    raise NotGGUF(f"unknown value type {kind}")


class Short(NotGGUF):
    """The bytes end before the header does (a remote file read in part: ask for more)."""


def read_header(f, name: str = "the file") -> dict:
    """Every key of the header (the long arrays as None), from an open binary stream."""
    if f.read(4) != MAGIC:
        raise NotGGUF(f"{name} is not a GGUF file")
    version = _read(f, "<I")
    if version < 2:
        raise NotGGUF(f"GGUF version {version} is too old")
    _read(f, "<Q")                                                 # tensors
    kv = {}
    for _ in range(_read(f, "<Q")):
        key = _string(f)
        kv[key] = _value(f, _read(f, "<I"))
    return kv


def header(path: Path) -> dict:
    with open(path, "rb") as f:
        return read_header(f, Path(path).name)


def meta(path: Path) -> dict:
    """The facts Aurora decides on. A split model (…-00001-of-00003.gguf) is read from its first part."""
    path = Path(path)
    parts = sorted(path.parent.glob(path.name.replace("00001-of", "*-of"))) if "-00001-of-" in path.name else [path]
    return facts(header(path), path.stem, sum(p.stat().st_size for p in parts))


def facts(kv: dict, name: str, size: int) -> dict:
    """The facts from a header's keys (a local file, or the first megabytes of a remote one: mdl_custom)."""
    arch = str(kv.get("general.architecture", ""))

    def a(key: str):
        return kv.get(f"{arch}.{key}")
    return {"architecture": arch, "name": kv.get("general.name") or name,
            "experts": a("expert_count") or 0, "experts_used": a("expert_used_count") or 0,
            "context": a("context_length") or 0, "layers": a("block_count") or 0,
            "chat_template": kv.get("tokenizer.chat_template") or "",
            "size_gb": round(size / 2**30, 2)}

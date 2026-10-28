# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""An installation's own layer inside the backup's frames (sys_backup_crypto._layer): used when present, a file of
before still read, a file of a layer not here refused by name."""
from __future__ import annotations

import io
import os
from types import SimpleNamespace

import pytest

from aurora import sys_backup  # noqa: F401 - first: sys_backup_crypto is read back by it
from aurora import sys_backup_crypto as bc
from aurora.sys_backup import FRAME, BackupError

KEY = os.urandom(32)
TOY = SimpleNamespace(MAGIC=b"AURBT", NONCE=4, key=lambda k: k[::-1],
                      xor=lambda k, n, i, d: bytes(b ^ (k[0] ^ n[0] ^ i) & 0xFF for b in d))


def _enc(data):
    out = io.BytesIO()
    bc.encrypt_stream(io.BytesIO(data), out, KEY)
    return out.getvalue()


def _dec(blob):
    out = io.BytesIO()
    bc.decrypt_stream(io.BytesIO(blob), out, KEY)
    return out.getvalue()


@pytest.mark.parametrize("n", [0, 10, FRAME, FRAME + 3])
def test_a_layer_wraps_every_frame_and_comes_off_again(monkeypatch, n):
    monkeypatch.setattr(bc, "_layer", lambda: TOY)
    data = os.urandom(n)
    blob = _enc(data)
    assert blob.startswith(TOY.MAGIC) and _dec(blob) == data


def test_a_file_without_the_layer_still_reads_and_one_with_a_layer_not_here_is_refused(monkeypatch):
    monkeypatch.setattr(bc, "_layer", lambda: None)
    plain = _enc(b"before")
    assert plain.startswith(b"AURB1")
    monkeypatch.setattr(bc, "_layer", lambda: TOY)
    assert _dec(plain) == b"before"                     # a blob of before, read by an installation with the layer
    layered = _enc(b"after")
    monkeypatch.setattr(bc, "_layer", lambda: None)
    with pytest.raises(BackupError, match="layer this installation does not have"):
        _dec(layered)


def test_the_layer_s_nonce_is_bound_to_the_frames(monkeypatch):
    monkeypatch.setattr(bc, "_layer", lambda: TOY)
    blob = bytearray(_enc(b"x" * 100))
    blob[5 + 8] ^= 1                                    # the nonce, after MAGIC and the AES prefix
    with pytest.raises(BackupError):
        _dec(bytes(blob))

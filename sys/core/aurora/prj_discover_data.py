# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The discovery engine's tables (ROADMAP N147): a .csv with a header or a .npz of named arrays, read as float
columns of one length, and the table's canonical hash (prj_discover re-exports these names).

  - a .csv is parsed by numpy's C reader (C639, 20 Nov: genfromtxt took 455 MB of the API's memory for a 35 MB table;
    loadtxt 16 MB); a table with empty fields falls back to genfromtxt only when it is small (FALLBACK_BYTES), else it is
    refused with what to write instead (nan);
  - a .npz may hold .npy arrays only, each header read before anything is decompressed, their total size bounded
    (C639: a member that is not an .npy was decompressed whole — 2.3 GB from 292 KB);
  - canonical(): the SHA-256 of the numbers themselves — columns by name, rows in order, each value to 10 significant
    digits — so that the same data written with other bytes (a newline added, another format) is the same table for
    «each table and target is tried once» (C640).
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path

import numpy as np

MAX_ROWS = 200_000
MAX_INPUTS = 8
MAX_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 64                 # .npz arrays
MAX_NPZ_BYTES = 256 * 1024 * 1024  # their decompressed sizes together
FALLBACK_BYTES = 4 * 1024 * 1024   # a .csv with empty fields read by genfromtxt only up to this size


def _file(root: Path, rel: str) -> tuple[str, bytes, float]:
    """(path in the project, its bytes, its mtime): read ONCE, never through a link (C643: a long run could swap a
    folder for a link between a check and an open by name); what is parsed and hashed is what was read."""
    import os
    import stat as st_
    from . import prj_run, prj_safeio
    try:
        r = prj_safeio.norm(str(rel or "").strip(), root)
    except ValueError:
        raise ValueError(f"{rel}: not a file of the project") from None
    if not r.isprintable():                          # O8 (seventh review): a line break in a name reached the ledger
        raise ValueError(f"{ascii(rel)[:120]}: a file name of printable characters only")
    if r == "." or ".git" in r.split("/") or Path(r).suffix.lower() not in (".csv", ".npz"):
        raise ValueError(f"{rel}: a .csv or .npz file of the project")
    if set(r.split("/")[:-1]) & prj_run.SKIP:        # C632: the folders a command's record skips hold no table
        raise ValueError(f"{rel}: not a table of the project (under {', '.join(sorted(prj_run.SKIP))})")
    try:
        fd = prj_safeio.open_in(root, r, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        raise ValueError(f"{rel}: not a file of the project") from None
    with os.fdopen(fd, "rb") as fh:
        s = os.fstat(fh.fileno())
        if not st_.S_ISREG(s.st_mode):
            raise ValueError(f"{rel}: not a file of the project")
        if s.st_size > MAX_BYTES:
            raise ValueError(f"{rel}: larger than {MAX_BYTES // (1024 * 1024)} MB")
        raw = fh.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"{rel}: larger than {MAX_BYTES // (1024 * 1024)} MB")
    return r, raw, (s.st_mtime, s.st_ctime)


def _npz(raw: bytes) -> dict[str, np.ndarray]:
    """C621, C639: .npy members only, each one's shape read from its header before anything is decompressed, their
    total bounded (a small file can expand)."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        odd = [i.filename for i in infos if not i.filename.isprintable()]
        if odd:                                      # O8: a member «x\n## …» reached the frozen .md raw
            raise ValueError(f"a .npz whose array names are printable characters only (not {ascii(odd[0])[:80]})")
        other = [i.filename for i in infos if not i.filename.endswith(".npy")]
        if other:
            raise ValueError(f"a .npz of .npy arrays only (also holds: {', '.join(other)[:120]})")
        if not infos or len(infos) > MAX_MEMBERS:
            raise ValueError(f"a .npz of 1 to {MAX_MEMBERS} arrays")
        if sum(i.file_size for i in infos) > MAX_NPZ_BYTES:
            raise ValueError(f"a .npz of at most {MAX_NPZ_BYTES // (1024 * 1024)} MB once decompressed")
        for i in infos:
            with z.open(i) as fh:
                version = np.lib.format.read_magic(fh)
                head = {(1, 0): np.lib.format.read_array_header_1_0, (2, 0): np.lib.format.read_array_header_2_0}
                if version not in head:
                    raise ValueError(f"{i.filename}: an .npy format version 1 or 2")
                shape, _, dtype = head[version](fh)
            if dtype.hasobject or int(np.prod(shape)) > MAX_ROWS + 1 or i.file_size > 16 * (MAX_ROWS + 1) + 4096:
                raise ValueError(f"{i.filename}: at most {MAX_ROWS} numbers per array, no objects")
    with np.load(io.BytesIO(raw), allow_pickle=False) as z:
        return {k: np.asarray(z[k], dtype=float).ravel() for k in z.files}


def _csv(raw: bytes) -> dict[str, np.ndarray]:
    with io.StringIO(raw.decode("utf-8", errors="replace")) as fh:
        header = fh.readline()
        rows = sum(1 for ln in fh if ln.strip())
    if rows > MAX_ROWS:
        raise ValueError(f"at most {MAX_ROWS} rows")
    if not header.strip() or rows < 1:
        raise ValueError("a .csv with a header line of column names and rows of numbers")
    names = [h.strip() for h in next(csv.reader([header]))]   # C621: names as written, not rewritten
    if len(set(names)) != len(names) or not all(names) or not all(n.isprintable() for n in names):
        raise ValueError("a .csv with a header line of distinct column names, printable characters only")
    try:
        a = np.loadtxt(io.BytesIO(raw), delimiter=",", skiprows=1, ndmin=2, dtype=float, encoding="utf-8")
    except ValueError as e:
        if len(raw) > FALLBACK_BYTES:
            raise ValueError(f"a value that is not a number ({str(e)[:120]}); in a table above "
                             f"{FALLBACK_BYTES // (1024 * 1024)} MB write a missing value as nan") from None
        text = raw.decode("utf-8", errors="replace").splitlines()[1:]
        a = np.genfromtxt(io.StringIO("\n".join(ln for ln in text if ln.strip())), delimiter=",", dtype=float)
        a = a.reshape(-1, 1) if a.ndim == 1 and len(names) == 1 else np.atleast_2d(a)
    if a.shape[1] != len(names):
        raise ValueError("every row must have one value per column")
    return {k: a[:, i].astype(float) for i, k in enumerate(names)}


def load(raw: bytes, suffix: str) -> dict[str, np.ndarray]:
    """Columns by name, as float arrays of one length; a file of more than MAX_ROWS rows is refused, never cut (C621)."""
    cols = _npz(raw) if suffix.lower() == ".npz" else _csv(raw)
    if not cols or len({len(v) for v in cols.values()}) != 1:
        raise ValueError("the columns must have the same length")
    return cols


def canonical(cols: dict[str, np.ndarray]) -> str:
    """The numbers' own SHA-256 (C640): names sorted, each value to 10 significant digits (nan and inf as such)."""
    h = hashlib.sha256()
    for k in sorted(cols):
        v = np.asarray(cols[k], dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            e = np.where(np.isfinite(v) & (v != 0), np.floor(np.log10(np.abs(v))), 0.0)
            r = np.where(np.isfinite(v), np.round(v / 10.0 ** e, 9) * 10.0 ** e, v)
        h.update(k.encode() + b"\0")
        h.update(np.asarray(r, dtype="<f8").tobytes())
    return h.hexdigest()


def table(root: Path, data: str, target: str, inputs: list | None) -> dict:
    rel, raw, (mtime, ctime) = _file(root, data)
    cols = load(raw, Path(rel).suffix)
    target = str(target or "").strip()
    if target not in cols:
        raise ValueError(f"no column «{target}» (columns: {', '.join(cols)[:300]})")
    names = [str(n).strip() for n in (inputs or []) if str(n).strip()] or [k for k in cols if k != target]
    bad = [n for n in names if n not in cols or n == target]
    if bad or not names or len(names) > MAX_INPUTS:
        raise ValueError(f"1 to {MAX_INPUTS} input columns, other than the target" + (f"; unknown: {', '.join(bad)}" if bad else ""))
    x = np.column_stack([cols[n] for n in names])
    y = cols[target]
    ok = np.all(np.isfinite(x), axis=1) & np.isfinite(y)
    return {"rel": rel, "mtime": mtime, "ctime": ctime, "sha256": hashlib.sha256(raw).hexdigest(), "canonical": canonical(cols),
            "x": x[ok], "y": y[ok], "names": names, "target": target, "dropped": int((~ok).sum())}

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Vector index of the vault: one per (section, domain), rebuildable from the vault.

    <AURORA_INDEX_DIR>/<section>/<domain>/vectors.f16     float16 matrix, append-only, read through mmap
                                         /sids.bin        sid of row i = bytes [32i, 32i+32)
                                         /hnsw.faiss      HNSW graph, only above AURORA_INDEX_EXACT_MAX
                                         /manifest.json   encoder, dimension, count, vault position

Rules, each from a failure of the previous installation:
- The index belongs to one encoder. If the encoder changes, updating refuses to
  mix vector spaces and asks for a rebuild (a 768-d vs 1536-d mismatch there
  degraded retrieval silently for weeks).
- The manifest is rewritten atomically after every batch; rows past its count
  are leftovers of a crash and are cut before appending. An update resumes
  where the last one stopped.
- If the HNSW graph covers fewer rows than the matrix, the rows it does not
  cover are searched exactly: no soliton is ever invisible (the previous
  installation had 14,485 solitons that could never be retrieved, B35).
"""
from __future__ import annotations

import json
import os
import threading
import time
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

import numpy as np

from . import sol_vault, sys_config, sys_log
from .sol_reader import VaultReader

SID_BYTES = 32
BATCH = 256
# one writer per domain's index in this process: an import of the harvest and a run that acquires sources may index
# the same domain at once (C219: imports no longer wait for the answers' lock); two appends would interleave
_folder_locks: dict[Path, threading.Lock] = {}
_folder_locks_guard = threading.Lock()


def _writing(folder: Path) -> threading.Lock:
    with _folder_locks_guard:
        return _folder_locks.setdefault(folder, threading.Lock())


class Encoder(Protocol):
    name: str
    dim: int

    def encode_documents(self, texts: list[str]) -> np.ndarray: ...


class IndexMismatch(Exception):
    """The index on disk was built with another encoder or dimension."""


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class DomainFiles:
    folder: Path

    @property
    def vectors(self) -> Path: return self.folder / "vectors.f16"
    @property
    def sids(self) -> Path: return self.folder / "sids.bin"
    @property
    def hnsw(self) -> Path: return self.folder / "hnsw.faiss"
    @property
    def manifest(self) -> Path: return self.folder / "manifest.json"

    def read_manifest(self) -> dict | None:
        return json.loads(self.manifest.read_text(encoding="utf-8")) if self.manifest.exists() else None


def memory_index(cfg: sys_config.Config, user: str | None) -> Path:
    """The memory index of a user (multi-user, U3): today's index/memory until the migration."""
    from . import sys_users_layout
    return sys_users_layout.place(cfg, "memory_index", user)     # no user after the migration: the admin's


def _index_dirs(cfg: sys_config.Config, user: str | None = None) -> list[tuple[str, str, DomainFiles]]:
    root = cfg.path("AURORA_INDEX_DIR")
    out = []
    for section in sol_vault.SECTIONS:
        base = memory_index(cfg, user) if section == "memory" else root / section
        if base.is_dir():
            out += [(section, d.name, DomainFiles(d)) for d in sorted(base.iterdir()) if (d / "manifest.json").exists()]
    return out


class Indexer:
    """Writer side: brings the index of a domain up to date with the vault."""

    def __init__(self, encoder: Encoder, cfg: sys_config.Config | None = None, component: str = "index",
                 user: str | None = None):
        self.cfg = cfg or sys_config.get()
        self.encoder = encoder
        self.user = user
        self.reader = VaultReader(self.cfg, user=user)
        self.log = sys_log.get_logger(component)
        self.component = component

    def files(self, domain: str) -> DomainFiles:
        section = self.reader.layout.section_of(domain)
        base = memory_index(self.cfg, self.user) if section == "memory" else self.cfg.path("AURORA_INDEX_DIR") / section
        return DomainFiles(base / domain)

    def update(self, domain: str, extend_hnsw: bool = True, run_id: str | None = None) -> int:
        """Index the solitons of `domain` not indexed yet. Returns how many were added."""
        with _writing(self.files(domain).folder):
            return self._update(domain, extend_hnsw, run_id)

    def _update(self, domain: str, extend_hnsw: bool, run_id: str | None) -> int:
        f = self.files(domain)
        f.folder.mkdir(parents=True, exist_ok=True)
        dim = self.encoder.dim
        m = f.read_manifest() or {"encoder": self.encoder.name, "dim": dim, "count": 0,
                                  "position": None, "hnsw_count": 0}
        if m["encoder"] != self.encoder.name or m["dim"] != dim:
            raise IndexMismatch(f"index of {domain} was built with {m['encoder']} ({m['dim']}-d), the encoder is "
                                f"{self.encoder.name} ({dim}-d): rebuild it with rebuild('{domain}')")
        for path, width in ((f.vectors, dim * 2), (f.sids, SID_BYTES)):   # cut crash leftovers
            if path.exists() and path.stat().st_size > m["count"] * width:
                with open(path, "r+b") as fh:
                    fh.truncate(m["count"] * width)
                self.log.warning("%s: cut %s back to %d rows (leftover of an interrupted update)",
                                 domain, path.name, m["count"])
        t0, added = time.time(), 0
        batch: list = []

        def flush():
            nonlocal added
            vecs = self.encoder.encode_documents([s.text for _, _, s in batch])
            assert vecs.shape == (len(batch), dim), f"encoder returned {vecs.shape}"
            with open(f.vectors, "ab") as fv, open(f.sids, "ab") as fs:
                fv.write(np.ascontiguousarray(vecs, dtype=np.float16).tobytes())
                fs.write("".join(s.sid for _, _, s in batch).encode("ascii"))
            m["count"] += len(batch)
            m["position"] = [batch[-1][0], batch[-1][1]]
            m["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            _write_json_atomic(f.manifest, m)
            added += len(batch)
            batch.clear()

        after = tuple(m["position"]) if m["position"] else None
        for item in self.reader.iter_domain(domain, after=after):
            batch.append(item)
            if len(batch) >= BATCH:
                flush()
        if batch:
            flush()
        if extend_hnsw and m["count"] > self.cfg["AURORA_INDEX_EXACT_MAX"] and m["hnsw_count"] < m["count"]:
            self._extend_hnsw(f, m)
        secs = time.time() - t0
        if added:
            self.log.info("index %s: +%d solitons (%d total) in %.1f s, %.1f/s", domain, added, m["count"],
                          secs, added / max(secs, 1e-9))
        sys_log.trace(self.component, "index.update", {"domain": domain, "added": added, "total": m["count"],
                                                       "seconds": round(secs, 2)}, run_id=run_id)
        return added

    def _extend_hnsw(self, f: DomainFiles, m: dict) -> None:
        import faiss
        dim, start = m["dim"], m["hnsw_count"]
        if f.hnsw.exists() and start:
            index = faiss.read_index(str(f.hnsw))
        else:
            index = faiss.IndexHNSWSQ(dim, faiss.ScalarQuantizer.QT_fp16, self.cfg["AURORA_INDEX_HNSW_M"],
                                      faiss.METRIC_INNER_PRODUCT)
            index.hnsw.efConstruction = self.cfg["AURORA_INDEX_HNSW_EF_CONSTRUCTION"]
            start = 0
        vecs = np.memmap(f.vectors, dtype=np.float16, mode="r", shape=(m["count"], dim))
        t0 = time.time()
        if not index.is_trained:
            index.train(np.asarray(vecs[: min(m["count"], 100_000)], dtype=np.float32))
        for i in range(start, m["count"], 65536):
            index.add(np.asarray(vecs[i:min(i + 65536, m["count"])], dtype=np.float32))
        tmp = f.hnsw.with_suffix(".tmp")
        faiss.write_index(index, str(tmp))
        os.replace(tmp, f.hnsw)
        m["hnsw_count"] = m["count"]
        _write_json_atomic(f.manifest, m)
        self.log.info("hnsw %s: %d -> %d rows in %.1f s", f.folder.name, start, m["count"], time.time() - t0)

    def update_all(self, run_id: str | None = None) -> dict[str, int]:
        out = {}
        for section in sol_vault.SECTIONS:
            for domain in self.reader.layout.domains(section):
                out[domain] = self.update(domain, run_id=run_id)
        return out

    def drop(self, domain: str, sids: Iterable[str]) -> int:
        """Remove the vectors of `sids` from the index of `domain`, without encoding anything again.

        Vectors and sids are rewritten without those rows; the HNSW graph (which cannot delete)
        is built again from the kept vectors. Returns how many rows were removed."""
        with _writing(self.files(domain).folder):
            return self._drop(domain, sids)

    def _drop(self, domain: str, sids: Iterable[str]) -> int:
        f = self.files(domain)
        m = f.read_manifest()
        drop = set(sids)
        if not m or not drop:
            return 0
        dim, n = m["dim"], m["count"]
        raw = f.sids.read_bytes()[: n * SID_BYTES].decode("ascii")
        all_sids = [raw[i * SID_BYTES:(i + 1) * SID_BYTES] for i in range(n)]
        keep = np.array([x not in drop for x in all_sids], dtype=bool)
        removed = int((~keep).sum())
        if not removed:
            return 0
        vecs = np.memmap(f.vectors, dtype=np.float16, mode="r", shape=(n, dim))
        tmp_v, tmp_s = f.vectors.with_suffix(".tmp"), f.sids.with_suffix(".tmp")
        with open(tmp_v, "wb") as fv:
            for i in range(0, n, 65536):
                fv.write(np.ascontiguousarray(vecs[i:i + 65536][keep[i:i + 65536]]).tobytes())
        tmp_s.write_bytes("".join(x for x, k in zip(all_sids, keep) if k).encode("ascii"))
        del vecs
        os.replace(tmp_v, f.vectors)
        os.replace(tmp_s, f.sids)
        m["count"], m["hnsw_count"] = n - removed, 0
        m["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        if f.hnsw.exists():
            f.hnsw.unlink()
        _write_json_atomic(f.manifest, m)
        if m["count"] > self.cfg["AURORA_INDEX_EXACT_MAX"]:
            self._extend_hnsw(f, m)
        self.log.info("audit: index %s: dropped %d rows, %d left", domain, removed, m["count"])
        sys_log.trace(self.component, "index.drop", {"domain": domain, "removed": removed, "total": m["count"]})
        return removed

    def rebuild(self, domain: str) -> int:
        """Drop the index of `domain` and index it again from the vault."""
        f = self.files(domain)
        for p in (f.vectors, f.sids, f.hnsw, f.manifest):
            if p.exists():
                p.unlink()
        self.log.warning("index %s dropped for rebuild with %s", domain, self.encoder.name)
        return self.update(domain)


_sets: "weakref.WeakSet[IndexSet]" = weakref.WeakSet()


def forget(folder: Path) -> int:
    """Drop every loaded index of a domain under `folder` (its vectors are mapped in memory, its HNSW read): before the
    folder is deleted — Windows does not delete a mapped file (C207). The next search loads it again if it is back."""
    folder, n = Path(folder).resolve(), 0
    for s in list(_sets):
        for f in [f for f in list(s._loaded) if Path(f).resolve().is_relative_to(folder)]:
            s._loaded.pop(f, None)
            n += 1
    import gc
    gc.collect()                                     # a mapping is unmapped when its last view is gone
    return n


class IndexSet:
    """Reader side: searches every domain index of both sections; reloads a domain when it changes."""

    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.log = sys_log.get_logger("index")
        self._loaded: dict[Path, dict] = {}
        _sets.add(self)

    def _load(self, f: DomainFiles) -> dict | None:
        mtime = f.manifest.stat().st_mtime_ns
        cached = self._loaded.get(f.folder)
        if cached and cached["mtime"] == mtime:
            return cached
        m = f.read_manifest()
        if not m or not m["count"]:
            return None
        entry = {"mtime": mtime, "manifest": m,
                 "vectors": np.memmap(f.vectors, dtype=np.float16, mode="r", shape=(m["count"], m["dim"])),
                 "sids": np.memmap(f.sids, dtype=f"S{SID_BYTES}", mode="r", shape=(m["count"],)),
                 "hnsw": None}
        if m["hnsw_count"] and f.hnsw.exists():
            import faiss
            entry["hnsw"] = faiss.read_index(str(f.hnsw))
            entry["hnsw"].hnsw.efSearch = self.cfg["AURORA_INDEX_HNSW_EF_SEARCH"]
        self._loaded[f.folder] = entry
        return entry

    @staticmethod
    def _exact(vectors: np.ndarray, q: np.ndarray, start: int, k: int) -> tuple[np.ndarray, np.ndarray]:
        best_s, best_i = np.empty(0, np.float32), np.empty(0, np.int64)
        for i in range(start, vectors.shape[0], 65536):
            block = np.asarray(vectors[i:i + 65536], dtype=np.float32) @ q
            top = np.argpartition(-block, min(k, len(block)) - 1)[:k]
            best_s = np.concatenate([best_s, block[top]])
            best_i = np.concatenate([best_i, top + i])
        keep = np.argsort(-best_s)[:k]
        return best_s[keep], best_i[keep]

    def search(self, queries: np.ndarray, k: int, sections: set[str] | None = None,
               user: str | None = None) -> list[list[tuple[str, float, str, str]]]:
        """For each query vector: the k best (sid, cosine, section, domain) over every domain (of `sections`); the
        memory is `user`'s. One IndexSet serves every user: the knowledge stays loaded once."""
        queries = np.asarray(queries, dtype=np.float32)
        results: list[list[tuple[str, float, str, str]]] = [[] for _ in range(len(queries))]
        for section, domain, f in _index_dirs(self.cfg, user):
            if sections and section not in sections:
                continue
            e = self._load(f)
            if e is None:
                continue
            m, count = e["manifest"], e["manifest"]["count"]
            for qi, q in enumerate(queries):
                scores, rows = np.empty(0, np.float32), np.empty(0, np.int64)
                covered = m["hnsw_count"] if e["hnsw"] is not None else 0
                if covered:
                    s, r = e["hnsw"].search(q[None, :], min(k, covered))
                    ok = r[0] >= 0
                    scores, rows = s[0][ok].astype(np.float32), r[0][ok].astype(np.int64)
                if covered < count:
                    s2, r2 = self._exact(e["vectors"], q, covered, k)
                    scores, rows = np.concatenate([scores, s2]), np.concatenate([rows, r2])
                results[qi] += [(e["sids"][r].decode("ascii"), float(s), section, domain) for s, r in zip(scores, rows)]
        return [sorted(r, key=lambda x: -x[1])[:k] for r in results]

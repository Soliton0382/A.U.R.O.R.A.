# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import hashlib
import json
import re

import numpy as np
import pytest

from aurora import sol_schema as S
from aurora.sol_index import IndexMismatch, Indexer, IndexSet
from aurora.sol_reader import VaultReader
from aurora.sol_search import Searcher
from aurora.sol_writer import VaultWriter

FILLER = " The measurement was repeated several times under controlled laboratory conditions. " * 4
TOPICS = ["soliton waves in shallow water canals", "superconducting qubits and decoherence",
          "prime numbers and the zeta function", "protein folding energy landscapes",
          "black hole thermodynamics and entropy", "graph neural networks for molecules",
          "monetary policy and inflation expectations", "plate tectonics and earthquakes"]


class FakeEncoder:
    """Bag of hashed words: texts that share words get similar vectors. Counts what it encodes."""
    name, dim = "fake-bow", 64

    def __init__(self):
        self.encoded = 0

    def _vec(self, text):
        v = np.zeros(self.dim, np.float32)
        for w in re.findall(r"[a-z]{4,}", text.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1
        return v / (np.linalg.norm(v) or 1)

    def encode_documents(self, texts):
        self.encoded += len(texts)
        return np.stack([self._vec(t) for t in texts]).astype(np.float16) if texts else np.zeros((0, self.dim), np.float16)

    def encode_queries(self, texts):
        return self.encode_documents(texts)


class FakeReranker:
    """Word overlap; records the questions it was given."""
    def __init__(self):
        self.pairs = []

    def score(self, pairs):
        self.pairs += list(pairs)
        words = lambda t: set(re.findall(r"[a-zà-ù]{4,}", t.lower()))
        return np.array([len(words(q) & words(p)) for q, p in pairs], np.float32)


def doc(i, topic=None, domain="physics", lang="en"):
    topic = topic or TOPICS[i % len(TOPICS)]
    return S.Soliton.new(f"This study examines {topic}. Case {i}.{FILLER}", domain, "knowledge", lang, f"src:{i}")


def test_update_indexes_everything_and_search_finds_the_topic(cfg):
    VaultWriter(cfg).add_many([doc(i) for i in range(8)])
    enc = FakeEncoder()
    assert Indexer(enc, cfg).update("physics") == 8
    res = IndexSet(cfg).search(enc.encode_queries(["black hole thermodynamics entropy"]), 3)[0]
    best = VaultWriter(cfg).layout and res[0]
    assert best[3] == "physics" and len(res) == 3


def test_update_is_incremental(cfg):
    w, enc = VaultWriter(cfg), FakeEncoder()
    w.add_many([doc(i) for i in range(5)])
    ix = Indexer(enc, cfg)
    ix.update("physics")
    w.add_many([doc(i) for i in range(5, 9)])
    assert ix.update("physics") == 4 and enc.encoded == 9
    assert ix.update("physics") == 0


def test_two_updates_of_one_domain_at_once_index_each_passage_once(cfg):
    """C219: an import no longer waits for the answers' lock, so a run that acquires sources and the harvest may index
    the same domain together; the domain's own lock keeps them in turn (each passage once, the manifest right)."""
    import threading
    import time
    VaultWriter(cfg).add_many([doc(i) for i in range(12)])

    class Slow(FakeEncoder):
        def encode_documents(self, texts):
            time.sleep(0.2)                              # both threads inside update at the same moment
            return super().encode_documents(texts)
    enc = Slow()
    added = []
    threads = [threading.Thread(target=lambda: added.append(Indexer(enc, cfg).update("physics"))) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(added) == [0, 12] and enc.encoded == 12
    m = Indexer(enc, cfg).files("physics").read_manifest()
    assert m["count"] == 12


def test_leftovers_of_an_interrupted_update_are_cut(cfg):
    VaultWriter(cfg).add_many([doc(i) for i in range(4)])
    ix = Indexer(FakeEncoder(), cfg)
    ix.update("physics")
    f = ix.files("physics")
    with open(f.vectors, "ab") as fh:
        fh.write(b"\x00" * 100)                 # half-written batch
    VaultWriter(cfg).add(doc(10))
    assert ix.update("physics") == 1
    m = json.loads(f.manifest.read_text())
    assert f.vectors.stat().st_size == m["count"] * 64 * 2 == 5 * 128


def test_a_different_encoder_is_refused(cfg):
    VaultWriter(cfg).add(doc(1))
    Indexer(FakeEncoder(), cfg).update("physics")
    other = FakeEncoder()
    other.name = "another-encoder"
    with pytest.raises(IndexMismatch, match="rebuild"):
        Indexer(other, cfg).update("physics")
    assert Indexer(other, cfg).rebuild("physics") == 1


def test_hnsw_and_the_exactly_searched_tail(cfg):
    cfg.values["AURORA_INDEX_EXACT_MAX"] = 10
    w, enc = VaultWriter(cfg), FakeEncoder()
    w.add_many([doc(i) for i in range(40)])
    ix = Indexer(enc, cfg)
    ix.update("physics")
    f = ix.files("physics")
    assert f.hnsw.exists() and json.loads(f.manifest.read_text())["hnsw_count"] == 40
    special = S.Soliton.new("Quasicrystals exhibit aperiodic order with forbidden rotational symmetry." + FILLER,
                            "physics", "knowledge", "en", "src:qc")
    w.add(special)
    ix.update("physics", extend_hnsw=False)    # the graph now misses the newest row
    res = IndexSet(cfg).search(enc.encode_queries(["quasicrystals aperiodic forbidden rotational symmetry"]), 5)[0]
    assert res[0][0] == special.sid


def test_memory_is_indexed_and_searchable(cfg):
    w, enc = VaultWriter(cfg), FakeEncoder()
    turn = S.Soliton.new("Ricordami che la riunione sul brevetto solitonico è giovedì.", "conversation",
                         "conversation", "it", "session:1")
    w.add_many([doc(1), turn])
    Indexer(enc, cfg).update_all()
    res = IndexSet(cfg).search(enc.encode_queries(["riunione brevetto solitonico giovedì"]), 2)[0]
    assert res[0][0] == turn.sid and res[0][2] == "memory"
    only_memory = IndexSet(cfg).search(enc.encode_queries(["riunione brevetto solitonico giovedì"]), 5, {"memory"})[0]
    assert only_memory and all(r[2] == "memory" for r in only_memory)       # recall of memories never brings knowledge


def test_reset_memory_also_drops_the_memory_index(cfg):
    w, enc = VaultWriter(cfg), FakeEncoder()
    turn = S.Soliton.new("Ricordami la riunione di giovedì sul brevetto.", "conversation", "conversation", "it", "s:1")
    w.add_many([doc(1), turn])
    Indexer(enc, cfg).update_all()
    w.reset_memory(confirm=True)
    res = IndexSet(cfg).search(enc.encode_queries(["riunione giovedì brevetto"]), 5)[0]
    assert all(section == "knowledge" for _, _, section, _ in res)
    assert not (cfg.path("AURORA_INDEX_DIR") / "memory").exists()


def test_search_reads_each_passage_in_its_own_language(cfg):
    w, enc, rr = VaultWriter(cfg), FakeEncoder(), FakeReranker()
    it = S.Soliton.new("Il contratto di locazione si rinnova tacitamente alla scadenza, salvo disdetta. " * 5,
                       "law_it", "knowledge", "it", "normattiva:1")
    en = S.Soliton.new("Lease contracts renew tacitly at expiry unless notice is given. " * 5,
                       "economics", "knowledge", "en", "arxiv:1")
    w.add_many([it, en])
    Indexer(enc, cfg).update_all()
    hits = Searcher(enc, rr, cfg).search("Il contratto di locazione si rinnova tacitamente?",
                                         translation="Do lease contracts renew tacitly?", top_k=2)
    used = {h.soliton.lang: h.query_used for h in hits}
    assert used == {"it": "original", "en": "translation"}
    asked = {p: q for q, p in rr.pairs}
    assert asked[it.text].startswith("Il contratto") and asked[en.text].startswith("Do lease")
    groups = Searcher.group_by_domain(hits)
    assert set(groups) == {"law_it", "economics"}


@pytest.mark.parametrize("exact_max", [1000, 10])       # exact search, then an HNSW graph rebuilt after the drop
def test_remove_source_drops_vault_rows_and_vectors_without_encoding(cfg, exact_max):
    cfg.values["AURORA_INDEX_EXACT_MAX"] = exact_max
    w, enc = VaultWriter(cfg), FakeEncoder()
    w.add_many([doc(i) for i in range(40)])
    bad = S.Soliton.new("Quasicrystals exhibit aperiodic order with forbidden rotational symmetry." + FILLER,
                        "physics", "knowledge", "en", "src:fake")
    w.add(bad)
    ix = Indexer(enc, cfg)
    ix.update("physics")
    q = enc.encode_queries(["quasicrystals aperiodic forbidden rotational symmetry"])
    iset = IndexSet(cfg)
    assert iset.search(q, 3)[0][0][0] == bad.sid
    encoded = enc.encoded
    removed = w.remove_source("physics", "src:fake")
    assert removed == [bad.sid] and ix.drop("physics", removed) == 1
    assert enc.encoded == encoded                                    # nothing encoded again
    assert VaultReader(cfg).get(bad.sid) is None and VaultReader(cfg).count("physics") == {"physics": 40}
    assert bad.sid not in [r[0] for r in iset.search(q, 10)[0]]      # the reader reloads the changed index
    assert json.loads(ix.files("physics").manifest.read_text())["count"] == 40
    w.add(doc(99))
    assert ix.update("physics") == 1                                 # incremental updates still work after a drop


def test_a_memory_reset_lets_go_of_every_thread_s_connections_and_the_loaded_index(cfg):
    """C207: Windows does not delete an open or mapped file (a real run): before the memory goes, every reader's
    connections — in every thread — and every loaded index of it are let go; the threads open them again later."""
    import sqlite3
    import threading
    from pathlib import Path
    from aurora import sol_index
    from aurora.sol_reader import VaultReader
    w, enc = VaultWriter(cfg), FakeEncoder()
    turn = S.Soliton.new("Ricordami la riunione di giovedì sul brevetto.", "conversation", "conversation", "it", "s:1")
    w.add_many([doc(1), turn])
    Indexer(enc, cfg).update_all()
    reader, held = VaultReader(cfg), {}
    opened, done = threading.Event(), threading.Event()

    def other_thread():                               # a pool's thread: alive, its connections cached
        reader.locate([turn.sid])
        held.update(reader._local.cons)
        opened.set()
        done.wait(30)
    t = threading.Thread(target=other_thread)
    t.start()
    opened.wait(30)
    s = IndexSet(cfg)
    s.search(enc.encode_queries(["riunione giovedì brevetto"]), 5)
    mem_vault = w.layout.base("memory").resolve()
    mem_index = (cfg.path("AURORA_INDEX_DIR") / "memory").resolve()
    in_memory = lambda p, top: Path(p).resolve().is_relative_to(top)                  # noqa: E731
    assert any(in_memory(f, mem_index) for f in s._loaded) and any(in_memory(p, mem_vault) for p in held)
    knowledge = [c for p, c in held.items() if not in_memory(p, mem_vault)]
    w.reset_memory(confirm=True)
    for path, con in held.items():
        if in_memory(path, mem_vault):
            with pytest.raises(sqlite3.ProgrammingError):    # closed
                con.execute("SELECT 1")
    assert all(c.execute("SELECT 1").fetchone() for c in knowledge)             # the knowledge's stay open
    done.set()
    t.join()
    assert not any(in_memory(f, mem_index) for f in s._loaded)
    assert sol_index.forget(cfg.path("AURORA_INDEX_DIR") / "memory") == 0

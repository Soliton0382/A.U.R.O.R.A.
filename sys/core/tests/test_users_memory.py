# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""U3, memory: after the migration each user's conversations are theirs (vault, index, search); the knowledge stays
shared and loaded once; before it, everything is where it always was."""
import json

from aurora import sol_schema as S
from aurora import sys_users_layout as L
from aurora.sol_index import Indexer, IndexSet
from aurora.sol_reader import VaultReader
from aurora.sol_search import Searcher
from aurora.sol_writer import VaultWriter
from test_sol_index import FILLER, FakeEncoder


class Reranker:
    def score(self, pairs):
        return [float(len(set(q.lower().split()) & set(t.lower().split()))) for q, t in pairs]


def turn(text, run):
    return S.Soliton.new(text + FILLER, "conversation", "conversation", "en", f"run:{run}", extra={"role": "user", "run_id": run})


def migrated(cfg):
    (cfg.path("AURORA_STATUS_DIR")).mkdir(parents=True, exist_ok=True)
    (cfg.path("AURORA_STATUS_DIR") / L.STATE).write_text(json.dumps({"layout": 1, "admin": "boss"}))


def test_before_the_migration_a_user_reads_today_s_memory(cfg):
    VaultWriter(cfg).add_many([turn("an old conversation about comets", "r0")])
    assert [t.text[:12] for t in VaultReader(cfg, user="boss").recent(5)] == ["an old conver"[:12]]


def test_each_user_has_their_own_memory_and_shares_the_knowledge(cfg):
    migrated(cfg)
    enc = FakeEncoder()
    VaultWriter(cfg).add_many([S.Soliton.new("Comets are icy bodies of the solar system." + FILLER, "physics", "knowledge", "en",
                                             "arxiv:comets")])
    Indexer(enc, cfg).update("physics")
    for user, text in (("boss", "my secret plan about comets for the boss"), ("guest", "the guest talks about comets too")):
        VaultWriter(cfg, user=user).add_many([turn(text, user)])
        Indexer(enc, cfg, user=user).update("conversation")
    assert (cfg.path("AURORA_VAULT_DIR") / "memory" / "users" / "boss" / "conversation").is_dir()
    assert not (cfg.path("AURORA_VAULT_DIR") / "memory" / "conversation").exists()      # nothing in the shared root
    assert [t.text.split()[1] for t in VaultReader(cfg, user="guest").recent(5)] == ["guest"]
    shared = IndexSet(cfg)
    for user, mine, theirs in (("boss", "secret", "guest"), ("guest", "guest", "secret")):
        hits = Searcher(enc, Reranker(), cfg, index=shared, user=user).search("comets plan guest secret")
        texts = " ".join(h.soliton.text for h in hits)
        assert mine in texts and theirs not in texts                  # never the other user's conversations
        assert any(h.soliton.source_id == "arxiv:comets" for h in hits)  # the knowledge is everyone's
    assert len([k for k in shared._loaded if "physics" in str(k)]) == 1  # the knowledge index loaded once

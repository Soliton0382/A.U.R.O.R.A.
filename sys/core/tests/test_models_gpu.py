# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""End-to-end with the real encoder and re-ranker. Runs only where the GPU and the models are present."""
from pathlib import Path

import pytest

from aurora import sol_schema as S
from aurora import sys_config, sys_log
from conftest import write_env

REAL_MODELS = Path(sys_config.CODE_ROOT) / "sys" / "models"
torch = pytest.importorskip("torch")
pytestmark = pytest.mark.skipif(
    not (torch.cuda.device_count() > 1 and (REAL_MODELS / "embedder" / "Qwen3-Embedding-0.6B").exists()
         and (REAL_MODELS / "reranker" / "bge-reranker-v2-m3").exists()),
    reason="needs two GPUs and the models in sys/models")


def test_real_models_find_italian_law_and_english_physics(tmp_path):
    (tmp_path / "sys").mkdir()
    (tmp_path / "sys" / "models").symlink_to(REAL_MODELS)
    cfg = sys_config.load(write_env(tmp_path), check_root=False)
    sys_log.configure(cfg)
    from aurora.mdl_embedder import Embedder
    from aurora.mdl_reranker import Reranker
    from aurora.sol_index import Indexer
    from aurora.sol_search import Searcher
    from aurora.sol_writer import VaultWriter

    law = S.Soliton.new(
        "Art. 1571. Nozione. La locazione è il contratto col quale una parte si obbliga a far godere all'altra "
        "una cosa mobile o immobile per un dato tempo, verso un determinato corrispettivo.",
        "law_it", "knowledge", "it", "normattiva:codice-civile:art1571", title="Codice civile, art. 1571")
    physics = S.Soliton.new(
        "Solitons are localized waves that keep their shape while propagating at constant speed. In shallow "
        "water they arise when nonlinear steepening exactly balances dispersion, as described by the "
        "Korteweg-de Vries equation, and two solitons emerge unchanged from a collision except for a phase shift. "
        * 2, "physics", "knowledge", "en", "arxiv:demo", title="Solitons")
    noise = [S.Soliton.new(t * 4, d, "knowledge", "en", f"demo:{i}") for i, (t, d) in enumerate([
        ("Monetary policy affects inflation expectations through interest rate announcements. ", "economics"),
        ("Graph neural networks predict molecular properties from atom and bond features. ", "artificial_intelligence"),
        ("Plate tectonics explains the distribution of earthquakes along plate boundaries. ", "earth_science")])]
    VaultWriter(cfg).add_many([law, physics] + noise)
    emb, rr = Embedder(cfg), Reranker(cfg)
    Indexer(emb, cfg).update_all()
    s = Searcher(emb, rr, cfg)

    hits = s.search("Che cos'è la locazione secondo il codice civile?", translation="What is a lease under the civil code?")
    assert hits[0].sid == law.sid and hits[0].query_used == "original"

    hits = s.search("Perché un solitone non cambia forma mentre si propaga?",
                    translation="Why does a soliton not change shape while it propagates?")
    assert hits[0].sid == physics.sid and hits[0].query_used == "translation"
    assert hits[0].rerank > 0.5

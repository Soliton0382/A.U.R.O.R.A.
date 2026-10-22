# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📚 The vault as an agent's tool (owner, 22 Oct: «i modelli hanno una data di addestramento, il vault è più
aggiornato paradossalmente, quindi sfruttare il vault per applicare nuove scoperte potrebbe portare a risultati
interessanti»).

search_vault: the same search as the answers (sol_search: embeddings, then the re-ranker), the passages returned with
their title, domain and source, so that a phase of a project can start from what the vault knows that the model does
not, and cite it. Aurora's own answers, reflections and the conversations are never returned: not sources (kno_answer).
"""
from __future__ import annotations

TOP_K = 6
MAX_K = 10
PASSAGE_CHARS = 1500
NOT_SOURCES = {"reflection", "conversation"}

TOOL = {"name": "search_vault", "description": "Search Aurora's vault: verified documents (papers, patents, books, "
        "laws) acquired after the models were trained, so often newer than what you know. Use it BEFORE choosing a "
        "method, a material or a design, to apply recent findings; cite the titles you use. Returns passages with "
        "title, domain and source.",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "what to look for, in plain words (English finds more papers)"},
            "top_k": {"type": "integer", "description": f"passages to return, at most {MAX_K} (default {TOP_K})"}},
            "required": ["query"]}}


def run(pipeline, args: dict, emit) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "ERROR: empty query"
    try:
        k = max(1, min(MAX_K, int(args.get("top_k") or TOP_K)))
    except (TypeError, ValueError):
        k = TOP_K
    hits = [h for h in pipeline.search.search(query, top_k=k + 4) if h.soliton.kind not in NOT_SOURCES][:k]
    emit("vault.search", {"query": query[:200], "hits": len(hits)})
    if not hits:
        return "The vault has nothing on this. Say so; do not invent sources."
    return "\n\n".join(f"[{i}] {h.soliton.title} — {h.soliton.domain} — {h.soliton.source_id} "
                       f"(score {h.rerank:.2f})\n{h.soliton.text[:PASSAGE_CHARS]}" for i, h in enumerate(hits, 1))

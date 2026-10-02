# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-models: the resident encoder and re-ranker behind a local HTTP API.

    POST /embed   {"texts": [...], "kind": "documents" | "queries"}  -> {"vectors": [[...]], "dim", "encoder"}
    POST /rerank  {"pairs": [[question, passage], ...]}              -> {"scores": [...]}
    GET  /health                                                       -> {"status": "ok", "encoder", "reranker"}

Listens on AURORA_MODELS_HOST:AURORA_MODELS_PORT (local only). Separate from the
API so that a crash of a model cannot take the API down.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from aurora import sys_config, sys_log  # noqa: E402
from aurora.mdl_embedder import Embedder  # noqa: E402
from aurora.mdl_reranker import Reranker  # noqa: E402

cfg = sys_config.get()
log = sys_log.get_logger("models")
app = FastAPI(title="aurora-models")
state: dict = {}


SPARE_MB = 256          # cache kept above what the models use; the rest goes back to the GPU after each request


def give_back() -> None:
    """PyTorch keeps the memory of the largest batch seen; on the GPU it shares with the reasoner that cache grew
    by 4.2 GB in a day and llama.cpp could no longer allocate its compute buffers: a crash at every request (C95)."""
    import torch
    if not torch.cuda.is_available():
        return
    for d in range(torch.cuda.device_count()):
        if torch.cuda.memory_reserved(d) - torch.cuda.memory_allocated(d) > SPARE_MB * 2**20:
            with torch.cuda.device(d):
                torch.cuda.empty_cache()


class EmbedIn(BaseModel):
    texts: list[str]
    kind: str = "documents"


class RerankIn(BaseModel):
    pairs: list[tuple[str, str]]


@app.on_event("startup")
def load() -> None:
    state["embedder"], state["reranker"] = Embedder(cfg), Reranker(cfg)
    sys_log.trace("models", "service.start", {"encoder": state["embedder"].name, "reranker": state["reranker"].name})


@app.get("/health")
def health() -> dict:
    return {"status": "ok" if state else "loading", "encoder": getattr(state.get("embedder"), "name", None),
            "reranker": getattr(state.get("reranker"), "name", None), "dim": getattr(state.get("embedder"), "dim", None)}


@app.post("/embed")
def embed(body: EmbedIn) -> dict:
    t0 = time.time()
    e = state["embedder"]
    v = e.encode_queries(body.texts) if body.kind == "queries" else e.encode_documents(body.texts)
    give_back()
    log.debug("embed %s: %d texts in %.2f s", body.kind, len(body.texts), time.time() - t0)
    return {"vectors": v.astype("float32").tolist(), "dim": e.dim, "encoder": e.name}


@app.post("/rerank")
def rerank(body: RerankIn) -> dict:
    t0 = time.time()
    scores = state["reranker"].score(body.pairs)
    give_back()
    log.debug("rerank: %d pairs in %.2f s", len(body.pairs), time.time() - t0)
    return {"scores": scores.tolist()}


if __name__ == "__main__":
    # Lifecycle in the component's own log: a start without a clean stop before it means a crash or a kill.
    from aurora import sys_ethics
    sys_ethics.require_intact(log)
    log.info("started: pid %d on %s:%s (systemd invocation %s)", os.getpid(), cfg["AURORA_MODELS_HOST"], cfg["AURORA_MODELS_PORT"],
             os.environ.get("INVOCATION_ID", "-"))
    # Open streams (the WebUI's activity feed never ends by itself) would hold the shutdown until
    # systemd kills the process: close them after 5 s so that a stop is clean (BUGS C23).
    # uvicorn re-raises SIGTERM after a graceful shutdown, so a line after run() would never be
    # written: the clean stop is logged by the application's shutdown hook instead.
    app.router.add_event_handler("shutdown", lambda: log.info("stopped cleanly: pid %d", os.getpid()))
    uvicorn.run(app, host=cfg["AURORA_MODELS_HOST"], port=cfg["AURORA_MODELS_PORT"], log_level="warning", timeout_graceful_shutdown=5)

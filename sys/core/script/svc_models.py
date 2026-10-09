# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-models: the resident encoder and re-ranker behind a local HTTP API.

    POST /embed   {"texts": [...], "kind": "documents" | "queries"}  -> {"vectors": [[...]], "dim", "encoder"}
    POST /rerank  {"pairs": [[question, passage], ...]}              -> {"scores": [...]}
    POST /transcribe[/segments]?lang=it   raw 16 kHz float32 audio   -> mdl_stt's answer (Whisper on the CPU, M145)
    GET  /health                                                       -> {"status": "ok", "encoder", "reranker"}

Listens on AURORA_MODELS_HOST:AURORA_MODELS_PORT (local only). Separate from the
API so that a crash of a model cannot take the API down.
"""
from __future__ import annotations

import gc
import heapq
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
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


class Turns:
    """One request on the device at a time, the owner's first: a question waiting (its encoding, its re-ranking) goes
    before the next slice of a harvested document (C219, 9 Oct: on a CPU a 43-passage import held the only lock for
    minutes and a question waited behind it until its 10-minute timeout)."""

    def __init__(self):
        self._cond = threading.Condition()
        self._busy = False
        self._waiting: list[tuple[int, int]] = []     # heap of (0 a question | 1 the rest, ticket)
        self._ticket = 0

    def take(self, urgent: bool) -> None:
        """In order of arrival, questions first: the next slice of a long batch takes a new ticket, so whoever came
        meanwhile goes before it (the same Windows: the conversation's memory, 2 passages, waited behind a 300-passage
        import until its timeout — the import's thread took the turn back the instant it gave it)."""
        with self._cond:
            me = (0 if urgent else 1, self._ticket)
            self._ticket += 1
            heapq.heappush(self._waiting, me)
            while self._busy or self._waiting[0] != me:
                self._cond.wait()
            heapq.heappop(self._waiting)
            self._busy = True

    def give(self) -> None:
        with self._cond:
            self._busy = False
            self._cond.notify_all()


_gpu = Turns()


def shrinking(owner, fn, items, urgent: bool = True):
    """fn(items), the owner's question first (Turns). A document batch goes slice by slice (the model's batch): between
    two slices a waiting question takes the device."""
    if urgent or len(items) <= max(1, owner.batch):
        return _one(owner, fn, items, urgent)
    import numpy as np
    step = max(1, owner.batch)
    return np.concatenate([_one(owner, fn, items[i:i + step], False) for i in range(0, len(items), step)])


def _one(owner, fn, items, urgent: bool):
    """fn(items) with the model's batch halved on CUDA out of memory, down to 1 (C197, 8 Oct: the harvester's batches
    of 8 long chunks ran out of memory beside the reasoner, the service answered 500 every 5 s and the failed batch's
    tensors stayed held by the exception — 5.7 GB allocated while idle). One request on the GPU at a time: two batches
    together were twice the peak."""
    import torch
    _gpu.take(urgent)
    try:
        batch = owner.batch
        try:
            while True:
                try:
                    return fn(items)
                except torch.OutOfMemoryError:
                    if owner.batch <= 1:
                        raise
                    owner.batch = max(1, owner.batch // 2)
                    failed = True
                else:
                    failed = False
                if failed:                           # outside the except: the failed batch's frames are gone
                    gc.collect()
                    give_back()
                    log.warning("out of GPU memory: %s again with batch %d (%d items)", type(owner).__name__, owner.batch,
                                len(items))
        finally:
            owner.batch = batch
            if sys.exc_info()[0] is not None:        # it failed even with batch 1: give the memory back anyway
                gc.collect()
                give_back()
    finally:
        _gpu.give()


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
    queries = body.kind == "queries"
    v = shrinking(e, e.encode_queries if queries else e.encode_documents, body.texts, urgent=queries)
    give_back()
    log.debug("embed %s: %d texts in %.2f s", body.kind, len(body.texts), time.time() - t0)
    return {"vectors": v.astype("float32").tolist(), "dim": e.dim, "encoder": e.name}


@app.post("/rerank")
def rerank(body: RerankIn) -> dict:
    t0 = time.time()
    scores = shrinking(state["reranker"], state["reranker"].score, body.pairs)
    give_back()
    log.debug("rerank: %d pairs in %.2f s", len(body.pairs), time.time() - t0)
    return {"scores": scores.tolist()}


def _audio(body: bytes):
    import numpy as np
    return np.frombuffer(body, dtype="<f4")


@app.post("/transcribe")
async def transcribe(request: Request, lang: str = "it") -> dict:
    """A voice message to text (sns_av.transcribe asks here: torch never in the API's process beside faiss)."""
    from starlette.concurrency import run_in_threadpool
    from aurora import mdl_stt
    return await run_in_threadpool(mdl_stt.transcribe, _audio(await request.body()), lang, cfg)


@app.post("/transcribe/segments")
async def transcribe_segments(request: Request, lang: str = "it") -> list:
    """A video's track to timed segments."""
    from starlette.concurrency import run_in_threadpool
    from aurora import mdl_stt
    return await run_in_threadpool(mdl_stt.segments, _audio(await request.body()), lang, cfg)


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

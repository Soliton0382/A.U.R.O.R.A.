# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A local reasoner of one's own (owner, 2026-10-09: «se uno lo vuole cambiare con un modello suo magari più potente
perché ha hardware… un'interfaccia che permette di scaricare il modello che si desidera»; roadmap 73).

  inspect(repo)        a Hugging Face repository: its GGUF files (split ones as one), the vision projectors, the
                       licence, the revision it is pinned to
  check(repo, file)    before downloading tens of GB: the first megabytes of the file (an HTTP range) give its
                       header — architecture, mixture of experts or dense, context, chat template — so its profile
                       (mdl_formats) and whether it fits this machine
  download(...)        the files at that revision into sys/models/llm/custom/<repo>/, each checked against the
                       SHA-256 Hugging Face publishes
  switch(model, mmproj) aurora-llm restarted on it (rule 6: never during a GPU job), one trial question; a model that
                       does not answer is undone at once. The model before is kept: revert() goes back to it.
Without a vision projector the local model does not see pictures: the Vision role goes to a cloud provider (Models
page) or stays off — said, never pretended.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from . import mdl_formats, mdl_gguf, sys_config

CUSTOM = Path("sys/models/llm/custom")
HEAD_STEPS = (8, 32, 96)              # MiB asked of a remote file until its header is whole (the vocabulary is in it)
ROOM_GB = 2.0                         # left on the GPUs besides the weights: context cache and buffers (an assumption)
TRIAL = ("Rispondi con una sola parola.", "Qual è la capitale d'Italia?")


class CustomError(Exception):
    pass


def _parts(name: str) -> tuple[str, int] | None:
    """(the model's name without the part, the part's number) for «…-00001-of-00003.gguf»."""
    m = re.match(r"(.+)-(\d{5})-of-\d{5}\.gguf$", name)
    return (m.group(1), int(m.group(2))) if m else None


def inspect(repo: str, revision: str | None = None) -> dict:
    from huggingface_hub import HfApi
    try:
        info = HfApi().model_info(repo, revision=revision, files_metadata=True)
    except Exception as e:                               # noqa: BLE001 - not found, private, offline: said
        raise CustomError(f"{repo}: {str(e)[:200]}") from None
    card = getattr(info, "card_data", None) or {}
    licence = (card.get("license") if hasattr(card, "get") else None) or next(
        (t.split(":", 1)[1] for t in info.tags or [] if t.startswith("license:")), "")
    models: dict[str, dict] = {}
    projectors = []
    for s in info.siblings:
        n = s.rfilename
        if not n.endswith(".gguf"):
            continue
        if "mmproj" in n.lower():
            projectors.append({"file": n, "size_gb": round((s.size or 0) / 2**30, 2)})
            continue
        base, part = _parts(n) or (n[:-5], 1)
        m = models.setdefault(base, {"file": n if part == 1 else "", "parts": [], "size_gb": 0.0})
        m["parts"].append(n)
        m["size_gb"] = round(m["size_gb"] + (s.size or 0) / 2**30, 2)
        if part == 1:
            m["file"] = n
    files = sorted((m for m in models.values() if m["file"]), key=lambda m: m["size_gb"])
    if not files:
        raise CustomError(f"{repo}: no GGUF file (llama.cpp reads GGUF only)")
    return {"repo": repo, "revision": info.sha, "licence": licence, "files": files, "projectors": projectors}


def remote_meta(repo: str, revision: str, file: str, size_gb: float, get=None) -> dict:
    """The header of a remote GGUF from its first megabytes, asked for more until it is whole."""
    import httpx
    from huggingface_hub import hf_hub_url
    url = hf_hub_url(repo, file, revision=revision)
    get = get or (lambda u, h: httpx.get(u, headers=h, follow_redirects=True, timeout=120))
    for mib in HEAD_STEPS:
        r = get(url, {"Range": f"bytes=0-{mib * 2**20 - 1}"})
        if r.status_code not in (200, 206):
            raise CustomError(f"{file}: HTTP {r.status_code}")
        try:
            kv = mdl_gguf.read_header(io.BytesIO(r.content), file)
        except mdl_gguf.Short:
            continue
        except mdl_gguf.NotGGUF as e:
            raise CustomError(str(e)) from None
        return mdl_gguf.facts(kv, file[:-5], int(size_gb * 2**30))
    raise CustomError(f"{file}: the header is longer than {HEAD_STEPS[-1]} MiB")


def _machine() -> tuple[float, float]:
    """(GPU memory, RAM) in GB, as the hardware profile reads them."""
    script = Path(__file__).resolve().parents[1] / "script"
    if str(script) not in sys.path:
        sys.path.insert(0, str(script))
    import sys_profile
    return round(sum(g["vram_gb"] for g in sys_profile.gpus()), 1), sys_profile.ram_gb()


def fit(meta: dict, vram_gb: float, ram_gb: float) -> dict:
    """whole / experts_in_ram / no, with the numbers it was decided on."""
    size, moe = float(meta["size_gb"]), int(meta.get("experts") or 0) > 0
    if vram_gb and size + ROOM_GB <= vram_gb:
        return {"verdict": "whole", "why": f"{size} GB of weights + {ROOM_GB} GB of room ≤ {vram_gb} GB of GPU memory"}
    if moe and vram_gb and size <= vram_gb + ram_gb * 0.5:
        return {"verdict": "experts_in_ram", "why": f"{size} GB > {vram_gb} GB of GPU memory: some experts in RAM "
                f"({ram_gb} GB), slower answers (M23 measured the transfer)"}
    return {"verdict": "no", "why": f"{size} GB of weights; GPU {vram_gb} GB, RAM {ram_gb} GB"
            + ("" if moe else " (a dense model cannot keep part of itself in RAM here)")}


def check(repo: str, revision: str, file: str, size_gb: float, machine=None, get=None) -> dict:
    meta = remote_meta(repo, revision, file, size_gb, get)
    vram, ram = machine or _machine()
    prof = mdl_formats.from_gguf(meta)
    return {"model": meta["name"], "architecture": meta["architecture"],
            "moe": f"{meta['experts_used']} of {meta['experts']} experts" if meta["experts"] else "dense",
            "context": meta["context"], "size_gb": meta["size_gb"], "profile": mdl_formats.describe(prof),
            "fit": fit(meta, vram, ram)}


def folder(cfg: sys_config.Config, repo: str) -> Path:
    return cfg.root / CUSTOM / re.sub(r"[^A-Za-z0-9._-]", "_", repo)


def download(cfg: sys_config.Config, repo: str, revision: str, files: list[str], emit=lambda e, p: None) -> list[str]:
    """The files at that revision, each checked against Hugging Face's SHA-256. Returns their paths from the root."""
    from huggingface_hub import HfApi, hf_hub_download
    remote = {s.rfilename: s for s in HfApi().model_info(repo, revision=revision, files_metadata=True).siblings}
    dest = folder(cfg, repo)
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for n in files:
        r = remote.get(n)
        if r is None:
            raise CustomError(f"{n} is not in {repo}@{revision[:12]}")
        p = dest / n
        if not (p.is_file() and p.stat().st_size == r.size):
            emit("custom.download", {"file": n, "size_gb": round((r.size or 0) / 2**30, 2)})
            hf_hub_download(repo, n, revision=revision, local_dir=dest)
        if r.lfs and _sha256(p) != r.lfs.sha256:
            p.unlink()
            raise CustomError(f"{n}: its SHA-256 differs from Hugging Face's: removed, download it again")
        emit("custom.verified", {"file": n})
        out.append(str(p.relative_to(cfg.root)))
    return out


def _sha256(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def _previous_file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "llm_previous.json"


def installed(cfg: sys_config.Config) -> dict:
    root = cfg.root / CUSTOM
    models = sorted(str(p.relative_to(cfg.root)) for p in root.rglob("*.gguf")
                    if "mmproj" not in p.name.lower() and (_parts(p.name) or ("", 1))[1] == 1) if root.exists() else []
    prev = json.loads(_previous_file(cfg).read_text(encoding="utf-8")) if _previous_file(cfg).exists() else None
    return {"current": {"model": str(cfg["AURORA_LLM_MODEL"]), "mmproj": str(cfg["AURORA_LLM_MMPROJ"]),
                        "profile": mdl_formats.describe(mdl_formats.local(cfg))},
            "previous": prev, "installed": models}


def _restart_and_try(cfg: sys_config.Config, run, wait_s: float) -> dict:
    from . import mdl_llm, mdl_modes
    code, said = mdl_modes._service("restart", run)       # each system's own way (the ports rewrite it)
    if code != 0:
        raise CustomError(f"aurora-llm: {said[-200:]}")
    llm = mdl_llm.LLM(mdl_modes.now(cfg))                  # the settings as the .env holds them now
    end = time.time() + wait_s
    while not llm.health():
        if time.time() > end:
            raise CustomError(f"aurora-llm did not answer within {int(wait_s)} s")
        time.sleep(5)
    t0 = time.time()
    out = llm.complete(*TRIAL, 64)
    if not out.answer.strip():
        raise CustomError("the model answered nothing to the trial question")
    return {"answer": out.answer.strip()[:200], "seconds": round(time.time() - t0, 1)}


def switch(cfg: sys_config.Config, model: str, mmproj: str = "", run=subprocess.run, wait_s: float = 600) -> dict:
    """The local reasoner on another model; the one before kept to go back to. Undone at once if it does not answer."""
    from . import sys_health
    job = sys_health.gpu_job(cfg)
    if job:                                            # rule 6: one GPU, one job
        raise CustomError(f"la GPU sta lavorando ({job}): riprova alla fine")
    path = cfg.root / model
    if not path.is_file() or (mmproj and not (cfg.root / mmproj).is_file()):
        raise CustomError(f"{model}: not downloaded here")
    from . import mdl_modes
    env = mdl_modes._env(cfg)                             # the machine's .env (the admin's, in multi-user)
    before = {"AURORA_LLM_MODEL": str(cfg["AURORA_LLM_MODEL"]), "AURORA_LLM_MMPROJ": str(cfg["AURORA_LLM_MMPROJ"])}
    sys_config.write_env(env, {"AURORA_LLM_MODEL": model, "AURORA_LLM_MMPROJ": mmproj})
    try:
        trial = _restart_and_try(cfg, run, wait_s)
    except CustomError:
        from . import mdl_modes
        sys_config.write_env(env, before)                # as it was, and the old model back on the GPU
        mdl_modes._service("restart", run)
        raise
    _previous_file(cfg).parent.mkdir(parents=True, exist_ok=True)
    _previous_file(cfg).write_text(json.dumps(before), encoding="utf-8")
    vision = bool(mmproj)
    return {**trial, "model": model, "vision": vision,
            "note": "" if vision else "senza proiettore visivo il modello locale non vede le immagini: "
                                      "nella pagina Modelli dai il ruolo Visione a un provider cloud, o resta spento"}


def revert(cfg: sys_config.Config, run=subprocess.run, wait_s: float = 600) -> dict:
    f = _previous_file(cfg)
    if not f.exists():
        raise CustomError("no model before this one")
    prev = json.loads(f.read_text(encoding="utf-8"))
    out = switch(cfg, prev["AURORA_LLM_MODEL"], prev.get("AURORA_LLM_MMPROJ", ""), run, wait_s)
    return out

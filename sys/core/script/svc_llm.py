# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-llm: runs the reasoner (llama.cpp server) with the parameters in .env.

llama-server is a child process; its output goes into the rotating log
<AURORA_LOG_DIR>/llm/llm.log, and SIGTERM/SIGINT are forwarded to it, so
systemd can stop the service cleanly.

The binaries find their libraries next to themselves (RUNPATH $ORIGIN, set once with
patchelf: BUGS C20): the folder can move with the installation.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config, sys_log  # noqa: E402


def command(cfg: sys_config.Config) -> list[str]:
    bin_dir = cfg.path("AURORA_LLAMACPP_DIR") / "bin"
    cmd = [str(bin_dir / "llama-server"),
           "-m", str(cfg.path("AURORA_LLM_MODEL")),
           "--host", cfg["AURORA_LLM_HOST"], "--port", str(cfg["AURORA_LLM_PORT"]),
           "-c", str(cfg["AURORA_LLM_CTX"]), "-ngl", "999", "-fa", "on", "--no-webui",
           "--tensor-split", cfg["AURORA_LLM_TENSOR_SPLIT"], "--parallel", str(cfg["AURORA_LLM_PARALLEL"])]
    mmproj = cfg.path("AURORA_LLM_MMPROJ")
    if mmproj.exists():
        cmd += ["--mmproj", str(mmproj)]
    if cfg["AURORA_LLM_CPU_MOE_LAYERS"] > 0:
        cmd += ["--n-cpu-moe", str(cfg["AURORA_LLM_CPU_MOE_LAYERS"])]
    return cmd


def main() -> int:
    cfg = sys_config.get()
    log = sys_log.get_logger("llm")
    if str(cfg["AURORA_LLM_BACKEND"]) == "cloud":      # the owner switched the local reasoner off: the GPU stays free
        log.info("AURORA_LLM_BACKEND=cloud: the local reasoner is off (🧠 Modelli → Ragionatore locale)")
        return 0
    from aurora import sys_ethics
    sys_ethics.require_intact(log)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=cfg["AURORA_LLM_GPUS"])
    cmd = command(cfg)
    log.info("starting: %s", " ".join(cmd))
    sys_log.trace("llm", "service.start", {"model": cfg.path("AURORA_LLM_MODEL").name, "gpus": cfg["AURORA_LLM_GPUS"],
                                           "tensor_split": cfg["AURORA_LLM_TENSOR_SPLIT"], "ctx": cfg["AURORA_LLM_CTX"]})
    child = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def forward(signum, _frame):
        log.info("signal %d: stopping llama-server", signum)
        child.send_signal(signum)

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    for line in child.stdout:
        line = line.rstrip()
        if line:
            (log.warning if (" E " in line or "error" in line.lower()) else log.info)("%s", line)
    code = child.wait()
    log.info("llama-server exited with %d", code)
    sys_log.trace("llm", "service.stop", {"exit": code})
    return code


if __name__ == "__main__":
    sys.exit(main())

# Compatibility

What Aurora was measured on (**recommended**: the owner's machine), and what is expected to work.
"Measured" means run here, with the measurement named; everything else is marked as not measured.

## Recommended stack (measured, 2026-10-01)

| layer | version | how it is installed | evidence |
|---|---|---|---|
| OS | Ubuntu 26.04 LTS, kernel 7.0.0-34-generic | — | all services, tests |
| GPUs | 2 × NVIDIA GeForce RTX 5060 Ti 16 GB (Blackwell, compute capability 12.0) | — | M23, M28 |
| NVIDIA driver | **595-open (595.91.07, CUDA 13.2)**; 580-server-open (580.178.04, CUDA 13.0) also measured | Ubuntu's signed, precompiled modules (`linux-modules-nvidia-*-generic`), never NVIDIA's driver packages | `sys_nvidia.sh verify`; M34: 112.4 tok/s on 595, 112.3 on 580 |
| CUDA toolkit | 13.4 (`cuda-toolkit-13-4`) from NVIDIA's ubuntu2604 repository, toolkit only, apt pin against NVIDIA drivers | `sys_nvidia.sh toolkit` | M34 |
| llama.cpp | commit 7fee178, built for sm_120 with CUDA 13.4, RUNPATH $ORIGIN | `sys_nvidia.sh llama` | M34: 112.3 tok/s |
| Python | 3.14 (venv) with torch 2.14 + cu130 (carries its own CUDA runtime and cuDNN) | requirements.txt | tests |
| Reasoner | Qwen3.6-35B-A3B UD-Q4_K_M, ctx 32k, split 4.5,3.5 over two GPUs | — | M28 |
| Encoder / re-ranker | Qwen3-Embedding-0.6B / bge-reranker-v2-m3 (GPU 1, ~3.3-6.2 GB) | — | M25, M31 |
| Images | SDXL-Lightning 4 steps, CPU offload, reasoner swapped out (~20 s) | — | M27 |
| HTTPS | Caddy, TLS 1.3 | install.sh | SECURITY.md |
| Voice (TTS) | Piper 1.8.0 (piper-tts, **GPL-3**: its own venv in sys/runtime/piper, run as a separate program, never imported into Aurora's Apache-2.0 code); voices rhasspy/piper-voices @c10ece1 (MIT): it_IT paola (dataset CC0), en_US ljspeech (public domain), CPU | `script/sys_tts_install.sh` | M114: 12.7 s of speech in 0.95 s, 248 MB |
| Natural voice (TTS) | Qwen3-TTS-12Hz-0.6B-Base @5d83992 (Apache-2.0) with qwen-tts 0.1.1, transformers 4.57.3, tokenizers 0.22.1, huggingface_hub 0.36.2, accelerate 1.12.0 in sys/runtime/qwen-tts/pkgs (Aurora's torch 2.14 reused; librosa and torchaudio replaced by script/tts_qwen_shims) | `script/sys_tts_qwen_install.sh` | M122: GPU 0.7 s per second of speech, 3.5 GB; CPU 3.8-4 s per second |

## Rules learnt the hard way

- The driver comes from Ubuntu, CUDA toolkits from NVIDIA: installing NVIDIA's `cuda` meta-package
  pulls NVIDIA's driver and fights Ubuntu's (the GPUs disappeared in March 2026 after repeated
  580 ↔ 590 switches). `sys_nvidia.sh toolkit` pins NVIDIA's driver packages to -1.
- Blackwell (RTX 50) needs the **open** kernel modules and nvcc ≥ 12.8 to build native kernels.
- The toolkit may be newer than the driver within CUDA 13 (13.4 toolkit on a 13.0 driver: verified);
  a newer *major* needs a newer driver.
- cuDNN from a repository for another Ubuntu release is not needed: torch's wheel carries its own.

## Hardware profiles (sys_profile.py, chosen by install.sh)

| profile | .env values | status |
|---|---|---|
| 2 GPUs ≥ 16 GB | split 4.5,3.5, experts on GPU, ctx 32k, encoder + re-ranker on the second GPU | **measured** (this page) |
| 1 GPU ≥ 24 GB | split 1, 8 MoE layers' experts in RAM, ctx 32k, everything on one GPU | not measured |
| 1 GPU of 16 GB | 28 MoE layers' experts in RAM, ctx 16k, everything on one GPU (48 GB RAM advised) | not measured |
| less, or no NVIDIA GPU | **cloud**: no local reasoner (AURORA_LLM_BACKEND=cloud, no aurora-llm), every step to the chosen provider (Anthropic, OpenAI, Gemini, Mistral, OpenRouter, xAI or Claude Code), always masked, with the owner's exemption (rule 9); encoder + re-ranker on the CPU (bfloat16 where the CPU has it, else float32), 30 candidates at 512 tokens; no dreams, edits or videos; 15 GB of disk | encoder/re-ranker speed **measured** on 4 cores (M151); the whole installation on a clean machine: the Install workflow |

## Expected to work, not measured

| case | expectation |
|---|---|
| one 24 GB GPU | the reasoner fits on one GPU with the models service on the same card only if VRAM allows; not measured |
| one 16 GB GPU | reasoner with MoE experts on CPU (`AURORA_LLM_CPU_MOE_LAYERS`, M23 measured the transfer cost), slower; not measured end to end |
| Ampere / Ada (RTX 30 / 40) | CUDA 13 supports them; `sys_nvidia.sh llama` builds for the compute capability it finds; not measured |
| no NVIDIA GPU | not supported today |
| other distributions | the scripts use apt and Ubuntu's driver packages: Ubuntu only |

#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# NVIDIA stack for Aurora on Ubuntu: clean up, CUDA toolkit 13 (side by side, never the driver from
# NVIDIA's repository), optional driver change with Ubuntu's signed packages, verification, and a
# llama.cpp build for the GPUs actually present (Blackwell = sm_120, which needs nvcc >= 12.8: A4).
#
# Every phase only PRINTS what it would do; add --yes to do it. Run the phases in order:
#
#   sudo sys/core/script/sys_nvidia.sh check
#   sudo sys/core/script/sys_nvidia.sh clean   [--yes] [--keep-cudnn] [--purge-container]
#   sudo sys/core/script/sys_nvidia.sh toolkit [--yes] [--cuda 13-4] [--cudnn]
#   sudo sys/core/script/sys_nvidia.sh driver  [--yes] [--driver 595-open]     # optional, then reboot
#        sys/core/script/sys_nvidia.sh verify                                  # after a reboot too
#        sys/core/script/sys_nvidia.sh llama   [--yes] [--commit 7fee178]      # as your user, not root
#
# Why the toolkit comes from NVIDIA but the driver from Ubuntu: Ubuntu ships the driver as signed,
# precompiled modules for each kernel (no DKMS build that can fail at the next kernel update); NVIDIA's
# repository has the newest toolkits. Mixing NVIDIA's *driver* packages with Ubuntu's is the usual way a
# system loses its GPUs: an apt pin forbids it. Everything is logged to /var/log/aurora-nvidia.log.
set -euo pipefail

PHASE="${1:-help}"; shift || true
YES=0; CUDA="13-4"; DRIVER=""; KEEP_CUDNN=0; CUDNN=0; PURGE_CONTAINER=0; COMMIT="7fee178"
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1 ;;
    --cuda) CUDA="$2"; shift ;;
    --driver) DRIVER="$2"; shift ;;
    --keep-cudnn) KEEP_CUDNN=1 ;;
    --cudnn) CUDNN=1 ;;
    --purge-container) PURGE_CONTAINER=1 ;;
    --commit) COMMIT="$2"; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
  shift
done

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
LOG=/var/log/aurora-nvidia.log
REPO=https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2604/x86_64
UNITS="aurora-harvester aurora-rem aurora-sentinel aurora-api aurora-llm aurora-models"

say()  { echo -e "\e[1m$*\e[0m"; [ -w "$(dirname $LOG)" ] && echo "$(date -Is) $*" >> "$LOG" || true; }
run()  {                                   # print, and do it only with --yes
  echo "  \$ $*"
  if [ "$YES" = 1 ]; then
    [ -w "$(dirname $LOG)" ] && echo "$(date -Is) RUN $*" >> "$LOG"
    eval "$@"
  fi
}
need_root() { [ "$YES" = 0 ] || [ "$(id -u)" = 0 ] || { echo "with --yes this phase needs sudo"; exit 1; }; }
installed() {                              # really installed ("ii"), not removed with configs left ("rc")
  dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' 2>/dev/null | awk '$1 == "ii" {print $2}' | sort -u | grep -E "$1" || true
}
leftovers() {                              # removed packages whose configuration files are still there
  dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' 2>/dev/null | awk '$1 == "rc" {print $2}' | sort -u | grep -E "$1" || true
}
dry_note() { [ "$YES" = 1 ] || echo -e "\n(nothing done: add --yes to do it)"; }

stop_aurora() {
  say "Stopping Aurora's services (they use the GPUs)"
  run "systemctl stop $UNITS || true"
}

case "$PHASE" in
check)
  say "== System"
  grep -E '^(PRETTY_NAME)=' /etc/os-release; echo "kernel $(uname -r)"
  echo "Secure Boot: $(mokutil --sb-state 2>/dev/null || echo unknown)  (enabled = modules must be signed: Ubuntu's are)"
  say "== GPUs and driver"
  nvidia-smi --query-gpu=index,name,driver_version,compute_cap --format=csv,noheader 2>/dev/null || echo "nvidia-smi does not answer"
  echo "driver CUDA level: $(nvidia-smi 2>/dev/null | grep -o 'CUDA Version: [0-9.]*' || echo -)"
  echo "kernel module: $(modinfo -F version nvidia 2>/dev/null || echo none) for $(uname -r)"
  say "== NVIDIA packages"
  installed '^(nvidia-driver|linux-(modules|objects|signatures)-nvidia|nvidia-compute|libnvidia-(cfg|compute|gl))' | sed 's/^/  /'
  say "== CUDA toolkits"
  echo "nvcc in PATH: $(command -v nvcc || echo none) $(nvcc --version 2>/dev/null | grep -o 'release [0-9.]*' || true)"
  ls -d /usr/local/cuda-* 2>/dev/null | sed 's/^/  /' || true
  installed '^(nvidia-cuda-toolkit|nvidia-cuda-dev|cuda-toolkit-|cuda-nvcc-)' | sed 's/^/  /'
  say "== cuDNN and repositories"
  installed '^(cudnn|libcudnn)' | sed 's/^/  /'
  ls /etc/apt/sources.list.d/ | grep -iE 'cuda|cudnn|nvidia' | sed 's/^/  /' || true
  ls -d /var/cudnn-local-repo-* /var/cuda-repo-* 2>/dev/null | sed 's/^/  /' || true
  say "== Ubuntu's driver recommendation"
  ubuntu-drivers devices 2>/dev/null | grep -E 'recommended' || true
  ;;

clean)
  need_root; stop_aurora
  say "Removing Ubuntu's CUDA 12.4 toolkit (nvcc 12.4 cannot build for Blackwell)"
  run "apt-get purge -y nvidia-cuda-toolkit nvidia-cuda-dev nvidia-cuda-toolkit-doc nvidia-cuda-gdb nsight-compute nsight-compute-target nsight-systems nsight-systems-target 2>/dev/null || true"
  if [ "$KEEP_CUDNN" = 0 ]; then
    say "Removing cuDNN 9.16 from the Ubuntu 24.04 local repository (wrong release; Aurora's torch carries its own cuDNN)"
    pk=$(installed '^(cudnn|libcudnn|cudnn-local-repo)' | tr '\n' ' ')
    [ -n "$pk" ] && run "apt-get purge -y $pk"
    run "rm -f /usr/share/keyrings/cudnn-local-*-keyring.gpg"
  fi
  stray=$(installed '^linux-objects-nvidia-' | grep -v "$(installed '^linux-modules-nvidia-.*-generic$' | sed -E 's/linux-modules-nvidia-([0-9]+).*/\1/' | head -1)" | tr '\n' ' ' || true)
  [ -n "$stray" ] && { say "Leftovers of other drivers: $stray"; run "apt-get purge -y $stray"; }
  if [ "$PURGE_CONTAINER" = 1 ]; then
    say "Removing the NVIDIA container toolkit (Docker GPU)"
    run "apt-get purge -y nvidia-container-toolkit nvidia-container-toolkit-base nvidia-container-runtime libnvidia-container-tools libnvidia-container1"
  fi
  rc=$(leftovers 'nvidia|cuda|cudnn|nsight' | tr '\n' ' ')
  if [ -n "$rc" ]; then
    say "Configuration files left by $(echo $rc | wc -w) NVIDIA/CUDA packages removed in the past: purged"
    run "dpkg --purge $rc"
  fi
  say "What apt would remove in all, purges and the packages left unused (review before --yes):"
  all=$(installed '^(nvidia-cuda-toolkit|nvidia-cuda-dev|nvidia-cuda-toolkit-doc|nvidia-cuda-gdb|nsight-(compute|systems)(-target)?)$' | tr '\n' ' ')
  [ "$KEEP_CUDNN" = 0 ] && all="$all $(installed '^(cudnn|libcudnn|cudnn-local-repo)' | tr '\n' ' ')"
  all="$all ${stray:-}"
  if [ -n "${all// /}" ]; then
    sim=$(apt-get -s purge --autoremove $all 2>/dev/null | grep -E '^(Purg|Remv)' | awk '{print $2}' | sort)
    echo "  $(echo "$sim" | grep -c .) packages:"; echo "$sim" | paste -sd' ' | fold -s -w 110 | sed 's/^/    /'
    if echo "$sim" | grep -qE '^(nvidia-driver|libnvidia-(gl|compute)|linux-modules-nvidia)'; then
      echo "ABORT: the clean-up would touch the driver"; exit 1
    fi
  fi
  run "apt-get autoremove -y"
  run "rm -f /etc/profile.d/cuda-12*.sh"
  if [ -L /usr/local/cuda ] && ! update-alternatives --query cuda >/dev/null 2>&1; then
    say "/usr/local/cuda is a hand-made link to $(readlink /usr/local/cuda): NVIDIA's packages manage it, it goes"
    run "rm /usr/local/cuda"
  fi
  dry_note
  ;;

toolkit)
  need_root
  say "CUDA toolkit $CUDA from NVIDIA's Ubuntu 26.04 repository — toolkit only, the driver stays Ubuntu's"
  if ! dpkg -s cuda-keyring >/dev/null 2>&1; then
    run "curl -fsSL -o /tmp/cuda-keyring.deb $REPO/cuda-keyring_1.1-1_all.deb && dpkg -i /tmp/cuda-keyring.deb"
  fi
  say "apt pin: from NVIDIA's repository only toolkits, never drivers or kernel modules"
  run "cat > /etc/apt/preferences.d/aurora-nvidia-toolkit-only <<'EOF'
# Written by Aurora's sys_nvidia.sh: the driver comes from Ubuntu, only CUDA toolkits from NVIDIA.
Package: nvidia-* libnvidia-* cuda-drivers* cuda-compat* xserver-xorg-video-nvidia* linux-*nvidia* nvidia-open* nvidia-dkms*
Pin: origin developer.download.nvidia.com
Pin-Priority: -1

Package: *
Pin: origin developer.download.nvidia.com
Pin-Priority: 100
EOF"
  run "apt-get update"
  say "The install must not touch any driver package: simulation first"
  if [ "$YES" = 1 ]; then
    if apt-get install -s "cuda-toolkit-$CUDA" | grep -E '^Inst (nvidia-driver|libnvidia-|linux-.*nvidia|cuda-drivers)'; then
      echo "ABORT: the toolkit would install driver packages (see above)"; exit 1
    fi
  fi
  run "apt-get install -y --no-install-recommends cuda-toolkit-$CUDA"
  [ "$CUDNN" = 1 ] && run "apt-get install -y cudnn9-cuda-13"
  ver="${CUDA/-/.}"
  run "[ -x /usr/local/cuda/bin/nvcc ] || { [ -L /usr/local/cuda ] && rm /usr/local/cuda; ln -s /usr/local/cuda-$ver /usr/local/cuda; }"
  run "printf 'export PATH=/usr/local/cuda/bin:\$PATH\n' > /etc/profile.d/cuda.sh"
  run "/usr/local/cuda/bin/nvcc --version | tail -1"
  dry_note
  ;;

driver)
  need_root
  [ -n "$DRIVER" ] || { echo "say which: --driver 595-open (Ubuntu recommends it), or 580-server-open (today's)"; exit 2; }
  old_meta=$(installed '^nvidia-driver-[0-9]+' | tr '\n' ' ')
  old_mods=$(installed '^linux-modules-nvidia-[0-9].*-generic$' | tr '\n' ' ')
  say "Driver: $old_meta-> nvidia-driver-$DRIVER (Ubuntu's signed, precompiled modules for each kernel)"
  echo "Rollback, if the GPUs are not seen after the reboot (from a text console, Ctrl+Alt+F3):"
  echo "  sudo apt-get install -y $old_meta $old_mods && sudo reboot"
  stop_aurora
  num="${DRIVER%%-*}"                      # 595 from 595-open: packages of that branch stay (apt sorts them out)
  remove=$(installed '^(nvidia-driver-|nvidia-compute-utils-|nvidia-utils-|nvidia-kernel-common-|nvidia-kernel-source-|libnvidia-(cfg|common|compute|decode|encode|extra|fbc|gl)[0-9]*-|linux-(modules|objects)-nvidia-|xserver-xorg-video-nvidia-|nvidia-firmware-|nvidia-dkms-)' \
           | grep -v -E -- "-${num}(-|$)" | sed 's/$/-/' | tr '\n' ' ' || true)
  say "One apt transaction: the new driver in, every other driver package out"
  run "apt-get install -y --purge nvidia-driver-$DRIVER linux-modules-nvidia-$DRIVER-generic $remove"
  say "Before rebooting: the module for this kernel must exist"
  if [ "$YES" = 1 ]; then
    v=$(modinfo -F version nvidia 2>/dev/null || true)
    if [ -z "$v" ]; then echo "ABORT: no nvidia module for $(uname -r). Do NOT reboot; run the rollback above."; exit 1; fi
    echo "module nvidia $v for $(uname -r): reboot now (sudo reboot), then: sys/core/script/sys_nvidia.sh verify"
  fi
  dry_note
  ;;

verify)
  say "== Driver"
  nvidia-smi --query-gpu=index,name,driver_version,compute_cap,memory.total --format=csv,noheader || { echo "FAIL: nvidia-smi"; exit 1; }
  n=$(nvidia-smi -L | wc -l); echo "GPUs seen: $n"
  say "== Toolkit"
  NVCC=$(ls -d /usr/local/cuda/bin/nvcc 2>/dev/null || command -v nvcc || true)
  [ -n "$NVCC" ] || { echo "FAIL: no nvcc"; exit 1; }
  "$NVCC" --version | tail -1
  arch=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1 | tr -d .)
  say "== A kernel built for sm_$arch, run on every GPU (SASS, no JIT)"
  t=$(mktemp -d)
  cat > "$t/k.cu" <<'EOF'
#include <cstdio>
__global__ void add(int *x) { x[threadIdx.x] += threadIdx.x; }
int main() {
  int n; cudaGetDeviceCount(&n);
  for (int d = 0; d < n; d++) {
    cudaSetDevice(d); int *x, h[32] = {0};
    cudaMalloc(&x, sizeof h); cudaMemcpy(x, h, sizeof h, cudaMemcpyHostToDevice);
    add<<<1, 32>>>(x); cudaError_t e = cudaDeviceSynchronize();
    cudaMemcpy(h, x, sizeof h, cudaMemcpyDeviceToHost); cudaFree(x);
    printf("GPU %d: %s (h[31]=%d)\n", d, e == cudaSuccess && h[31] == 31 ? "OK" : cudaGetErrorString(e), h[31]);
  }
  return 0;
}
EOF
  "$NVCC" -arch=sm_"$arch" -o "$t/k" "$t/k.cu" && "$t/k"
  rm -rf "$t"
  ;;

llama)
  [ "$(id -u)" != 0 ] || { echo "run this phase as your user (the build belongs to the installation)"; exit 1; }
  NVCC=/usr/local/cuda/bin/nvcc
  [ -x "$NVCC" ] || { echo "no $NVCC: run the toolkit phase first"; exit 1; }
  arch=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1 | tr -d .)
  SRC="$ROOT/sys/runtime/llama.cpp-src"; OUT="$ROOT/sys/runtime/llama.cpp"
  say "llama.cpp $COMMIT for sm_$arch with $("$NVCC" --version | grep -o 'release [0-9.]*')"
  [ -d "$SRC/.git" ] || run "git clone https://github.com/ggml-org/llama.cpp '$SRC'"
  run "git -C '$SRC' fetch --quiet origin && git -C '$SRC' checkout --quiet '$COMMIT'"
  run "cmake -S '$SRC' -B '$SRC/build' -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=$arch -DCMAKE_CUDA_COMPILER=$NVCC -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_RPATH='\$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON"
  run "cmake --build '$SRC/build' -j\$(nproc) --target llama-server"
  say "The current build is kept as bin.previous; the new one replaces bin only after it starts"
  run "rm -rf '$OUT/bin.new' && mkdir -p '$OUT/bin.new' && cp -a '$SRC/build/bin/.' '$OUT/bin.new/'"
  run "'$OUT/bin.new/llama-server' --version"
  run "[ -e '$OUT/bin.previous' ] || [ ! -e '$OUT/bin' ] || cp -a '$OUT/bin' '$OUT/bin.previous'"   # a first install has no build yet
  run "rm -rf '$OUT/bin' && mv '$OUT/bin.new' '$OUT/bin'"
  echo "Then: systemctl restart aurora-llm, and measure the first load (A4: 15.8 s with JIT, 0.71 s warm)."
  echo "Back to the previous build: rm -rf '$OUT/bin' && cp -a '$OUT/bin.previous' '$OUT/bin'"
  dry_note
  ;;

*)
  sed -n '4,20p' "$0" | sed 's/^# \{0,1\}//'
  ;;
esac

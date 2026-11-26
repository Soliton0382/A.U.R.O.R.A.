#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
# Finite elements (N155): FEniCSx (dolfinx 0.9, PETSc, MPICH, gmsh) in an environment of its own under
# sys/runtime/fenicsx — nothing in apt, nothing in the system's Python. micromamba pinned by version and SHA-256 (written
# here, not fetched from where the file comes from); the environment rebuilt from sys/core/config/fenicsx.lock (every
# package by URL and MD5, conda-forge). About 440 MB downloaded, 2.1 GB on disk; the package cache emptied after.
# Already there: only checked (an exact-solution test).
set -euo pipefail
cd "$(dirname "$0")/../../.."
D=sys/runtime/fenicsx
MM_VERSION=2.0.5-0
MM_SHA256=cdf5a2e18d213617b6c5c32d8763b4e8fc05f8173b4f4017997683cb984357eb
LOCK=sys/core/config/fenicsx.lock
mkdir -p "$D/bin" "$D/dl"
if [ ! -x "$D/bin/micromamba" ] || ! echo "$MM_SHA256  $D/bin/micromamba" | sha256sum -c --quiet - 2>/dev/null; then
  curl -sSfL -o "$D/dl/micromamba.new" \
    "https://github.com/mamba-org/micromamba-releases/releases/download/$MM_VERSION/micromamba-linux-64"
  echo "$MM_SHA256  $D/dl/micromamba.new" | sha256sum -c --quiet - || { echo "micromamba: SHA-256 diverso, non installato" >&2; exit 1; }
  chmod 0755 "$D/dl/micromamba.new"
  mv -f "$D/dl/micromamba.new" "$D/bin/micromamba"
fi
export MAMBA_ROOT_PREFIX="$PWD/$D/mamba"
if [ ! -x "$D/env/bin/python" ]; then
  "$D/bin/micromamba" create -y -p "$PWD/$D/env" --file "$LOCK" >/dev/null
  "$D/bin/micromamba" clean -a -y >/dev/null
fi
# the check: Poisson with an exact quadratic solution, P2 elements, error at machine precision
out=$(env -i PATH=/usr/bin:/bin HOME="$HOME" CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 "$D/env/bin/python" -I -c '
from mpi4py import MPI
import numpy as np, ufl
from dolfinx import fem, mesh
from dolfinx.fem.petsc import LinearProblem
dom = mesh.create_unit_square(MPI.COMM_WORLD, 16, 16)
V = fem.functionspace(dom, ("Lagrange", 2))
ue = fem.Function(V); ue.interpolate(lambda x: 1 + x[0] ** 2 + 2 * x[1] ** 2)
dom.topology.create_connectivity(1, 2)
bc = fem.dirichletbc(ue, fem.locate_dofs_topological(V, 1, mesh.exterior_facet_indices(dom.topology)))
u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
uh = LinearProblem(ufl.dot(ufl.grad(u), ufl.grad(v)) * ufl.dx, fem.Constant(dom, -6.0) * v * ufl.dx, bcs=[bc],
                   petsc_options={"ksp_type": "preonly", "pc_type": "lu"}).solve()
e = float(np.max(np.abs(uh.x.array - ue.x.array)))
print(f"{e:.1e}")
assert e < 1e-10')
echo "FEniCSx pronto (dolfinx 0.9): errore sul caso esatto $out"

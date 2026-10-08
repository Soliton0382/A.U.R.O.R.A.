# Aurora for the Mac — experimental, not ready to install

In the repository since 8 October 2026: phases 1 and 2 of 5 done (PORTING.md), no installer yet (phase 3).
Every publication builds this port from the Linux code and runs its platform tests (dev_publish.sh); on GitHub
the **Ports** workflow (Actions → Ports → Run workflow, and every release tag) builds it on a real Mac,
installs the requirements from PyPI, runs the platform tests and `probe.py` — the backend called for real on
that machine — then the whole Linux suite on the built tree, for information (what fails is phase 3's list).

It holds only what differs from the Linux Aurora; `build.py` makes the whole Mac tree from the published Linux code,
so there is one truth and the port follows every change of it.

    python3 build.py --test          # → ../Aurora_build/Aurora_mac, then the platform tests on it
    python3 build.py --probe         # on a real Mac: the backend called for real (probe.py)

| File | What |
|---|---|
| `PORTING.md` | every place the Linux code speaks to the system, what replaces it here, the phase |
| `build.py` | Linux code + this folder + REWRITES (each on an anchor found exactly once) |
| `probe.py` | the backend on a real machine: each read called, checked against the machine where the answer is known |
| `sys/core/aurora/sys_platform/` | the interface (`base.py`), the Linux reference, the Mac backend |
| `sys/core/tests/test_platform_*.py` | the reference against the real Linux machine; the Mac with recorded tool outputs |

Shared with the other port (the same bytes, checked by build.py): `build.py`, `sys_platform/__init__.py`,
`base.py`, `linux.py`, `tests/test_platform_linux.py`, `tests/test_platform_residue.py`, `rewrites.py`, `probe.py`.

## How it is in the repository

| Way | How | For |
|---|---|---|
| Folders ✅ (chosen, 8 Oct) | `Aurora_mac/`, `Aurora_windows/` taken out of .gitignore, one commit | simplest; everyone gets everything |
| Branches | `mac` and `windows` branches of the same repository, each the built tree | a download per system from the Releases |
| Built in CI ✅ (Ports workflow) | the folders stay, GitHub Actions builds and tests on macos-latest and windows-latest, Releases carry the zips | the most checked: every change of Linux is built for both |

Nothing has run on a real Mac until the Ports workflow is run: its results are the first measures.

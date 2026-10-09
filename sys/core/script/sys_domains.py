# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The domains an installation cares about (owner, 9 Oct: «chi scarica ha qualcosa in più per ciò che sceglie»).

Eight areas instead of 34 domains: the installers ask which (numbers, «all», or Enter for the defaults); the
harvester collects those domains, and the published seed of answers (config/shadow_seed.json) brings the shadows of
those domains in the installation's language. Changed later on the Knowledge page, domain by domain.

    python sys/core/script/sys_domains.py --list it          # the areas, numbered, in Italian (or en)
    python sys/core/script/sys_domains.py --set 1,4,8        # those areas harvested, the others off
    python sys/core/script/sys_domains.py --set all          # every domain
    python sys/core/script/sys_domains.py --set ""           # the defaults (nothing changed)
Docker: AURORA_DOMAINS in docker/.env, the same values, applied at the first start.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# aurora is imported only to apply: the installers list the areas before the venv exists (the system's python)

AREAS = [
    ("Intelligenza artificiale e informatica", "Artificial intelligence and computing",
     ["artificial_intelligence", "computer_science", "programming", "information_theory"]),
    ("Sicurezza informatica e reti", "Cyber security and networks", ["cyber_security", "network_security"]),
    ("Matematica e statistica", "Mathematics and statistics", ["mathematics", "statistics"]),
    ("Fisica", "Physics", ["physics", "quantum_physics", "particle_physics", "condensed_matter", "astrophysics",
                           "relativity", "mathematical_physics", "nonlinear_science"]),
    ("Chimica, materiali, Terra, ingegneria e robotica", "Chemistry, materials, Earth, engineering and robotics",
     ["chemistry", "materials", "earth_science", "engineering", "robotics", "patents"]),
    ("Biologia e medicina", "Biology and medicine", ["biomedicine", "genomics", "medicine"]),
    ("Persone e società: psicologia, economia, storia, filosofia, religioni, letteratura",
     "People and society: psychology, economics, history, philosophy, religions, literature",
     ["psychology", "economics", "society", "history", "philosophy", "religion", "literature"]),
    ("Diritto italiano", "Italian law", ["law_it"]),
]


def areas_list(lang: str) -> str:
    return "\n".join(f"    {i}) {it if lang == 'it' else en}" for i, (it, en, _) in enumerate(AREAS, 1))


def chosen_domains(answer: str) -> set[str] | None:
    """The domains of the areas answered («1,4», «1 4», «all» / «tutte»); None for the defaults (empty answer)."""
    answer = answer.strip().lower()
    if not answer:
        return None
    if answer in ("all", "tutte", "tutti", "*"):
        return {d for _, _, ds in AREAS for d in ds}
    out = set()
    for tok in answer.replace(",", " ").split():
        if not tok.isdigit() or not 1 <= int(tok) <= len(AREAS):
            raise ValueError(f"not an area: {tok} (1-{len(AREAS)})")
        out |= set(AREAS[int(tok) - 1][2])
    return out


def apply(cfg, answer: str) -> dict[str, str]:
    """The chosen areas' domains harvested («round»), the others off; «general» always on. Defaults: nothing changed."""
    from aurora import kno_sources
    want = chosen_domains(answer)
    cur = kno_sources.modes(cfg)
    if want is None:
        return cur
    want |= {"general"}
    # a domain already harvested keeps its mode («exhaust» stays), a new one goes «round»
    return kno_sources.set_modes(cfg, {d: ((m if m != "off" else "round") if d in want else "off") for d, m in cur.items()})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", metavar="LANG", choices=("it", "en"))
    ap.add_argument("--set", metavar="AREAS")
    ap.add_argument("--check", metavar="AREAS", help="exit 0 if the answer is valid (the installers' question)")
    a = ap.parse_args()
    if a.list:
        print(areas_list(a.list))
        return 0
    if a.check is not None:
        try:
            chosen_domains(a.check)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        return 0
    if a.set is not None:
        from aurora import sys_config
        try:
            modes = apply(sys_config.get(), a.set)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        print(f"{sum(m != 'off' for m in modes.values())} domains harvested")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

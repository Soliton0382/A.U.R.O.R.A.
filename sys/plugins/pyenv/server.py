# SPDX-License-Identifier: Apache-2.0
"""Plugin "pyenv": reads Aurora's Python environment (versions, project dependencies, ML-KEM availability in cryptography)."""
from __future__ import annotations

import importlib
import importlib.metadata as md
import platform
import re
import sys
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("pyenv", version="1.0")


def _err(e: Exception) -> str:
    import traceback
    return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


def _projects_dir() -> Path | None:
    for key in ("AURORA_PROJECTS_DIR",):
        try:
            p = Path(cfg.path(key))
            if p.is_dir():
                return p
        except Exception:
            pass
    return None


def _installed(name: str) -> str | None:
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


@server.tool()
def pyenv_versions(packages: str = "cryptography") -> str:
    """Python version and installed versions of the given packages (comma-separated names) in Aurora's environment."""
    try:
        out = [f"Python {platform.python_version()} ({sys.executable})"]
        names = [n.strip() for n in re.split(r"[,\s]+", packages or "") if n.strip()]
        if not names:
            return "\n".join(out + ["Nessun pacchetto indicato."])
        for n in names:
            v = _installed(n)
            out.append(f"- {n}: {v}" if v else f"- {n}: non installato")
        return "\n".join(out)
    except Exception as e:
        return _err(e)


def _mlkem_probe() -> list[str]:
    lines: list[str] = []
    mod = None
    for modname in ("cryptography.hazmat.primitives.asymmetric.mlkem",
                    "cryptography.hazmat.primitives.asymmetric.ml_kem"):
        try:
            mod = importlib.import_module(modname)
            break
        except ImportError:
            continue
    if mod is None:
        lines.append("ML-KEM-768: ASSENTE (in questa versione di cryptography non c'è un modulo mlkem).")
        return lines
    names = [n for n in dir(mod) if "768" in n]
    priv = next((getattr(mod, n) for n in names if "Private" in n), None)
    if priv is None:
        lines.append(f"ML-KEM-768: il modulo {mod.__name__} esiste, ma non contiene classi 768 (trovate: {', '.join(dir(mod)[:10])}).")
        return lines
    try:
        sk = priv.generate()
        pk = sk.public_key()
    except Exception as e:
        lines.append(f"ML-KEM-768: l'API c'è ({priv.__name__}), ma il backend non la supporta: {type(e).__name__}: {e}")
        return lines
    enc = getattr(pk, "encapsulate", None)
    dec = getattr(sk, "decapsulate", None)
    if not (enc and dec):
        lines.append(f"ML-KEM-768: genera le chiavi ({priv.__name__}); non ho trovato encapsulate/decapsulate.")
        return lines
    r = enc()
    ok = False
    for shared, ct in ((r[0], r[1]), (r[1], r[0])):
        try:
            if dec(ct) == shared:
                ok = True
                break
        except Exception:
            continue
    if ok:
        lines.append(f"ML-KEM-768: DISPONIBILE ({mod.__name__}.{priv.__name__}); prova di incapsulamento e decapsulamento in memoria riuscita.")
    else:
        lines.append(f"ML-KEM-768: le classi ci sono ({priv.__name__}), ma la prova in memoria non ha prodotto lo stesso segreto.")
    return lines


@server.tool()
def pyenv_crypto_check() -> str:
    """Checks, in memory only, whether the cryptography library offers ML-KEM-768, X25519 and HKDF-SHA256, and reports the library and OpenSSL versions."""
    try:
        try:
            import cryptography
        except ImportError:
            return "La libreria cryptography non è installata nell'ambiente di Aurora: ML-KEM-768 non è disponibile."
        out = [f"Python {platform.python_version()}, cryptography {cryptography.__version__}"]
        try:
            from cryptography.hazmat.backends.openssl.backend import backend
            out.append("Backend: " + backend.openssl_version_text())
        except Exception:
            pass
        try:
            out += _mlkem_probe()
        except Exception as e:
            out.append(f"ML-KEM-768: la verifica non è riuscita: {type(e).__name__}: {e}")
        try:
            from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
            a, b = X25519PrivateKey.generate(), X25519PrivateKey.generate()
            same = a.exchange(b.public_key()) == b.exchange(a.public_key())
            out.append("X25519: disponibile" + ("" if same else " (ma lo scambio non coincide)"))
        except Exception as e:
            out.append(f"X25519: non disponibile ({type(e).__name__}: {e})")
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.hkdf import HKDF
            HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"t").derive(b"x" * 32)
            out.append("HKDF-SHA256: disponibile")
        except Exception as e:
            out.append(f"HKDF-SHA256: non disponibile ({type(e).__name__}: {e})")
        return "\n".join(out)
    except Exception as e:
        return _err(e)


def _declared_deps(proj: Path) -> list[str]:
    deps: list[str] = []
    pp = proj / "pyproject.toml"
    if pp.is_file():
        import tomllib
        data = tomllib.loads(pp.read_text(encoding="utf-8", errors="replace"))
        deps += list(data.get("project", {}).get("dependencies", []) or [])
        for group in (data.get("project", {}).get("optional-dependencies", {}) or {}).values():
            deps += list(group or [])
    req = proj / "requirements.txt"
    if req.is_file():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                deps.append(line)
    return deps


@server.tool()
def pyenv_project_deps(project: str = "") -> str:
    """Compares the dependencies a project declares (pyproject.toml, requirements.txt) with the versions installed; with no name, lists the projects."""
    try:
        root = _projects_dir()
        if root is None:
            return "Non trovo la cartella dei progetti (AURORA_PROJECTS_DIR)."
        projects = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
        if not project.strip():
            if not projects:
                return "Non ci sono ancora progetti."
            return "Progetti: " + ", ".join(projects)
        proj = (root / project.strip()).resolve()
        if root.resolve() not in proj.parents or not proj.is_dir():
            return f"Il progetto '{project}' non esiste. Progetti: " + (", ".join(projects) or "nessuno")
        deps = _declared_deps(proj)
        if not deps:
            return f"{proj.name}: nessuna dipendenza dichiarata (manca pyproject.toml o requirements.txt, oppure sono vuoti)."
        out = [f"{proj.name}: {len(deps)} dipendenze dichiarate"]
        for d in deps:
            name = re.split(r"[\s<>=!~;\[(]", d, maxsplit=1)[0]
            v = _installed(name)
            out.append(f"- {d}: installata {v}" if v else f"- {d}: NON installata")
        return "\n".join(out)
    except Exception as e:
        return _err(e)


if __name__ == "__main__":
    server.run("stdio")

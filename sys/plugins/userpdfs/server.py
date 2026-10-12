# SPDX-License-Identifier: Apache-2.0
"""Plugin "userpdfs": elenca, in sola lettura, i PDF della cartella Documenti dell'utente (solo metadati)."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

server = MCPServer("userpdfs", version="1.0")

KEY = "AURORA_USERPDFS_DIR"


def _xdg_documents(home: Path) -> Path | None:
    """Legge XDG_DOCUMENTS_DIR da ~/.config/user-dirs.dirs, se c'è."""
    f = home / ".config" / "user-dirs.dirs"
    try:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("XDG_DOCUMENTS_DIR="):
                val = line.split("=", 1)[1].strip().strip('"')
                val = val.replace("$HOME", str(home))
                p = Path(val).expanduser()
                if p != home:
                    return p
    except OSError:
        pass
    return None


def _docs_dir() -> tuple[Path | None, str]:
    """Restituisce (cartella, nota) oppure (None, messaggio)."""
    custom = str(sys_config.get().values.get(KEY, "") or "").strip()
    if custom:
        p = Path(custom).expanduser()
        if p.is_dir():
            return p, ""
        return None, f"La cartella indicata in {KEY} non esiste: {p}"
    home = Path.home()
    candidates = []
    x = _xdg_documents(home)
    if x:
        candidates.append(x)
    candidates += [home / "Documenti", home / "Documents"]
    for c in candidates:
        if c.is_dir():
            return c, ""
    return None, ("Cartella Documenti non trovata (cercate: "
                  + ", ".join(str(c) for c in candidates)
                  + f"). Puoi indicarla in {KEY} (Plugin → userpdfs).")


def _scan(root: Path) -> tuple[list[tuple[str, int, float]], int]:
    """Cammina la cartella senza seguire i link; restituisce (pdf, cartelle_illeggibili)."""
    found: list[tuple[str, int, float]] = []
    errors = 0

    def onerr(_e):
        nonlocal errors
        errors += 1

    for dirpath, _dirs, files in os.walk(root, onerror=onerr, followlinks=False):
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError:
                errors += 1
                continue
            found.append((full, st.st_size, st.st_mtime))
    return found, errors


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


@server.tool()
def userpdfs_count() -> str:
    """Quanti PDF ci sono nella cartella Documenti dell'utente, sottocartelle incluse, con dimensione totale e numero per sottocartella principale."""
    try:
        root, msg = _docs_dir()
        if root is None:
            return msg
        pdfs, errs = _scan(root)
        if not pdfs:
            out = f"Nessun PDF in {root} (sottocartelle incluse)."
            return out + (f" {errs} elementi non leggibili." if errs else "")
        total = sum(s for _, s, _ in pdfs)
        per: dict[str, int] = {}
        for p, _, _ in pdfs:
            rel = Path(p).relative_to(root)
            top = rel.parts[0] if len(rel.parts) > 1 else "(cartella principale)"
            per[top] = per.get(top, 0) + 1
        lines = [f"PDF in {root}: {len(pdfs)} (sottocartelle incluse), totale {_size(total)}."]
        lines.append("Per cartella:")
        for k, v in sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))[:30]:
            lines.append(f"- {k}: {v}")
        if len(per) > 30:
            lines.append(f"- … altre {len(per) - 30} cartelle")
        if errs:
            lines.append(f"Attenzione: {errs} elementi non leggibili (permessi).")
        return "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def userpdfs_list(limit: int = 50, order: str = "recenti", contains: str = "") -> str:
    """Elenco dei PDF nella cartella Documenti (percorso, dimensione, data di modifica) con il totale; order: recenti, nome o grandi; contains filtra per testo nel percorso."""
    try:
        root, msg = _docs_dir()
        if root is None:
            return msg
        pdfs, errs = _scan(root)
        total_all = len(pdfs)
        if contains:
            needle = contains.lower()
            pdfs = [x for x in pdfs if needle in x[0].lower()]
        if not pdfs:
            extra = f" contenenti «{contains}»" if contains else ""
            return f"Nessun PDF{extra} in {root} (sottocartelle incluse; PDF totali: {total_all})."
        o = (order or "").lower()
        if o.startswith("nom"):
            pdfs.sort(key=lambda x: x[0].lower())
        elif o.startswith("grand") or o.startswith("dim"):
            pdfs.sort(key=lambda x: -x[1])
        else:
            pdfs.sort(key=lambda x: -x[2])
        limit = max(1, min(int(limit or 50), 500))
        head = f"PDF in {root}: {len(pdfs)}"
        if contains:
            head += f" contenenti «{contains}» (su {total_all} totali)"
        head += f", totale {_size(sum(s for _, s, _ in pdfs))}."
        lines = [head]
        for p, s, m in pdfs[:limit]:
            rel = Path(p).relative_to(root)
            when = datetime.fromtimestamp(m).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- {rel} | {_size(s)} | {when}")
        if len(pdfs) > limit:
            lines.append(f"… e altri {len(pdfs) - limit} (aumenta limit per vederli).")
        if errs:
            lines.append(f"Attenzione: {errs} elementi non leggibili (permessi).")
        return "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "backup_files": per-file view of the nightly backup (destination folder, file cache, critical files)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("backup_files", version="1.0")


def _status_dir() -> Path:
    """The backup service's status folder (last.json, cache.json)."""
    return Path(cfg.path("AURORA_STATUS_DIR")) / "backup"


def _last() -> tuple[dict | None, str]:
    """Read last.json; return (data, error text)."""
    p = _status_dir() / "last.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, f"Non trovo {p}: non ho potuto leggere l'ultimo esito del backup."
    except Exception as e:
        return None, f"Non ho potuto leggere {p}: {e}"


def _cache() -> tuple[dict | None, str]:
    """Load cache.json and map each recorded file path to its entry, whatever the layout."""
    p = _status_dir() / "cache.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"Non trovo {p}: non ho potuto leggere l'elenco dei file del backup."
    except Exception as e:
        return None, f"Non ho potuto leggere {p}: {e}"
    if isinstance(data, dict):
        for k in ("files", "entries", "cache", "items"):
            if isinstance(data.get(k), (dict, list)):
                data = data[k]
                break
    out: dict = {}
    if isinstance(data, dict):
        for k, v in data.items():
            if "/" in str(k):
                out[str(k)] = v
    elif isinstance(data, list):
        for v in data:
            if isinstance(v, dict):
                q = v.get("path") or v.get("file") or v.get("name")
                if q:
                    out[str(q)] = v
            elif isinstance(v, (list, tuple)) and v and isinstance(v[0], str):
                out[v[0]] = v
    return out, ""


def _size(v) -> int | None:
    """Best-effort size of a cache entry."""
    if isinstance(v, dict):
        for k in ("size", "bytes", "st_size"):
            if isinstance(v.get(k), int):
                return v[k]
    return None


def _gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB" if n >= 1e8 else f"{n / 1e6:.1f} MB"


@server.tool()
def backup_files_dest(max_files: int = 300000) -> str:
    """Contents of the backup destination: per top-level folder files, size, empty and unreadable files, and whether the last snapshot is there and readable."""
    try:
        last, err = _last()
        if last is None:
            return err
        dest = Path(str(last.get("dest", "")))
        snap = str(last.get("snapshot", ""))
        at = last.get("at")
        when = datetime.fromtimestamp(at).astimezone().isoformat(timespec="seconds") if at else "?"
        head = (f"Ultimo backup: {snap} ({when}), esito {'ok' if last.get('ok') else 'NON ok'}, "
                f"{last.get('files', '?')} file, {last.get('checked_blobs', '?')} blob verificati.\n"
                f"Destinazione: {dest}")
        if not str(dest) or not dest.exists():
            return head + "\nNon trovo la destinazione: non ho potuto leggerla (disco o NAS non montato?)."
        if not os.access(dest, os.R_OK | os.X_OK):
            return head + "\nLa destinazione esiste ma non ho potuto leggerla (permessi)."
        errors: list[str] = []
        stats: dict[str, list[int]] = {}   # top-level name -> [files, bytes, empty]
        hits: list[str] = []
        n, cut = 0, False

        def onerr(e):
            errors.append(f"{e.filename}: {e.strerror}")

        for root, _dirs, files in os.walk(dest, onerror=onerr):
            rel = os.path.relpath(root, dest)
            top = None if rel == "." else rel.split(os.sep)[0]
            for f in files:
                if n >= max_files:
                    cut = True
                    break
                n += 1
                fp = os.path.join(root, f)
                try:
                    sz = os.lstat(fp).st_size
                except OSError as e:
                    errors.append(f"{fp}: {e.strerror}")
                    continue
                s = stats.setdefault(top or f, [0, 0, 0])
                s[0] += 1
                s[1] += sz
                s[2] += sz == 0
                if snap and snap in fp:
                    hits.append(fp)
            if cut:
                break
        lines = [head]
        for name, (c, b, z) in sorted(stats.items(), key=lambda x: -x[1][1])[:15]:
            lines.append(f"- {name}: {c} file, {_gb(b)}" + (f", {z} VUOTI" if z else ""))
        if not stats:
            lines.append("La destinazione è vuota.")
        if snap:
            if not hits:
                lines.append(f"Snapshot {snap}: NON trovato tra i file della destinazione.")
            else:
                bad = []
                for fp in hits[:20]:
                    try:
                        with open(fp, "rb") as fh:
                            fh.read(16)
                    except OSError as e:
                        bad.append(f"{fp}: {e.strerror}")
                lines.append(f"Snapshot {snap}: {len(hits)} file trovati, "
                             + ("leggibili." if not bad else f"{len(bad)} illeggibili: " + "; ".join(bad[:5])))
        if errors:
            lines.append(f"{len(errors)} elementi che non ho potuto leggere: " + "; ".join(errors[:5]))
        if cut:
            lines.append(f"(Conteggio fermato a {max_files} file.)")
        return "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def backup_files_list(filter: str = "", limit: int = 50) -> str:
    """Files recorded by the backup (its file cache), optionally only those whose path contains the filter."""
    try:
        files, err = _cache()
        if files is None:
            return err
        if not files:
            return "La cache del backup è leggibile ma non contiene percorsi di file riconoscibili."
        f = filter.strip().lower()
        sel = sorted(p for p in files if f in p.lower())
        if not sel:
            return f"Nessun file registrato contiene «{filter}» (su {len(files)} registrati)."
        lines = [f"{len(sel)} file registrati" + (f" con «{filter}»" if f else "") + f" (su {len(files)}):"]
        for p in sel[:max(1, limit)]:
            sz = _size(files[p])
            lines.append(f"- {p}" + (f" ({_gb(sz)})" if sz is not None else ""))
        if len(sel) > limit:
            lines.append(f"… e altri {len(sel) - limit}.")
        return "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def backup_files_check(paths: str) -> str:
    """For each critical file or name (comma or newline separated): whether the backup records it, and whether the original still exists and is readable."""
    try:
        items = [x.strip() for x in paths.replace("\n", ",").split(",") if x.strip()]
        if not items:
            return "Indica almeno un file o un nome da verificare."
        files, err = _cache()
        if files is None:
            return err
        lines, missing = [], 0
        for it in items:
            key = it.rstrip("/")
            hits = [p for p in files if p == key or p.endswith("/" + key.lstrip("/"))]
            if not hits:
                hits = [p for p in files if key.lower() in p.lower()]
            if not hits:
                missing += 1
                lines.append(f"- {it}: NON registrato nel backup.")
                continue
            p = hits[0]
            src = Path(p)
            if not src.is_absolute():
                state = "originale non verificabile (percorso relativo)"
            elif not src.exists():
                state = "originale non trovato o non visibile da qui: non ho potuto leggerlo"
            elif os.access(src, os.R_OK):
                state = "originale presente e leggibile"
            else:
                state = "originale presente ma non leggibile"
            lines.append(f"- {it}: registrato ({len(hits)} corrispondenze, es. {p}); {state}.")
        head = (f"Verificati {len(items)} elementi: "
                + ("tutti registrati." if not missing else f"{missing} NON registrati."))
        return head + "\n" + "\n".join(lines)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")

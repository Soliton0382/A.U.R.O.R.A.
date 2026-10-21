# SPDX-License-Identifier: Apache-2.0
"""Plugin "vista": looks at a project's images with Aurora's local vision model (llama.cpp + mmproj)."""
from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("vista", version="1.0")

_EXT = {".png", ".jpg", ".jpeg"}
_PROMPT = (
    "Sei un esaminatore di tavole tecniche e di brevetto. Guarda l'immagine e rispondi in italiano, "
    "in modo concreto e breve. Descrivi cosa è disegnato; segnala se le linee di richiamo dei numeri "
    "incrociano altre linee o tra loro, se testi o numeri si sovrappongono a linee o ad altri testi, "
    "se ci sono colori, grigi o sfumature invece del solo tratto nero su bianco. "
    "Indica dove (in alto, al centro, a sinistra...). Istruzione: "
)


def _resolve(project: str, path: str) -> tuple[Path | None, str]:
    """Return the image path inside the project, or None and an Italian reason."""
    root = Path(cfg.path("AURORA_PROJECTS_DIR")).resolve()
    proj = (root / project).resolve()
    if proj.parent != root:
        return None, f"Progetto non valido: {project}"
    rel = path.lstrip("/")
    # The path may repeat the project name (cad/<project>/...) or start inside it.
    cands = [(proj / rel).resolve()]
    if rel.startswith(project + "/"):
        cands.append((proj / rel[len(project) + 1:]).resolve())
    for c in cands:
        if not c.is_relative_to(proj):
            return None, "Percorso fuori dal progetto: rifiutato."
        if c.is_file():
            if c.suffix.lower() not in _EXT:
                return None, f"Formato non supportato ({c.suffix}): solo PNG o JPG."
            return c, ""
    return None, f"File non trovato: {path} nel progetto {project}"


def _png_stats(p: Path) -> str:
    """Decode a PNG with the standard library and count black/white, grey and coloured pixels."""
    data = p.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return "non è un PNG valido"
    pos, idat, plte, trns = 8, [], None, None
    w = h = bd = ct = il = 0
    while pos + 8 <= len(data):
        ln = int.from_bytes(data[pos:pos + 4], "big")
        typ, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
            bd, ct, il = body[8], body[9], body[12]
        elif typ == b"PLTE":
            plte = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat.append(body)
    head = f"{w}x{h} pixel"
    if bd != 8 or il or ct not in (0, 2, 3, 4, 6):
        return f"{head}, {bd} bit, tipo colore {ct}{', interlacciato' if il else ''}: conteggio colori non disponibile"
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(b"".join(idat))
    stride = w * ch
    prev = bytearray(stride)
    step = max(1, (w * h) // 2_000_000)          # sample big images to stay fast
    bw = grey = col = 0
    i = 0
    for _y in range(h):
        f = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        # Undo the PNG row filter (None, Sub, Up, Average, Paeth).
        if f == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 255
        elif f == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif f == 3:
            for x in range(stride):
                left = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b, c = prev[x], (prev[x - ch] if x >= ch else 0)
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        for x in range(0, w, step):
            o = x * ch
            alpha = 255
            if ct == 0:
                r = g = b = line[o]
            elif ct == 2:
                r, g, b = line[o:o + 3]
            elif ct == 3:
                k = line[o]
                r, g, b = plte[k] if plte and k < len(plte) else (0, 0, 0)
                if trns and k < len(trns):
                    alpha = trns[k]
            elif ct == 4:
                r = g = b = line[o]
                alpha = line[o + 1]
            else:
                r, g, b, alpha = line[o:o + 4]
            if alpha < 128:                      # transparent counts as white paper
                bw += 1
            elif max(r, g, b) - min(r, g, b) > 30:
                col += 1
            elif max(r, g, b) <= 40 or min(r, g, b) >= 215:
                bw += 1
            else:
                grey += 1
    tot = max(1, bw + grey + col)
    verdict = ("solo bianco e nero al tratto" if col == 0 and grey / tot < 0.01
               else "contiene colori" if col else "contiene grigi/sfumature")
    return (f"{head}; bianco/nero {100 * bw / tot:.2f}%, grigi {100 * grey / tot:.2f}%, "
            f"colorati {100 * col / tot:.2f}% → {verdict}"
            + (" (i grigi sotto 1% sono di solito bordi antialiasing)" if 0 < grey / tot < 0.01 else ""))


@server.tool()
def vista_info(project: str, path: str) -> str:
    """Size and format of a project image; for PNG an exact count of black/white, grey and coloured pixels (line-art check)."""
    try:
        p, why = _resolve(project, path)
        if p is None:
            return why
        kb = p.stat().st_size / 1024
        if p.suffix.lower() == ".png":
            return f"{p.name} ({kb:.0f} KB): {_png_stats(p)}"
        return f"{p.name} ({kb:.0f} KB): JPG, conteggio colori solo per PNG (il JPG introduce comunque sfumature di compressione)."
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def vista_describe(project: str, path: str, instruction: str = "Descrivi la tavola e i suoi difetti.") -> str:
    """Describe a project image (PNG/JPG) with Aurora's local vision model, following the instruction (drawn content, crossing leader lines, overlapping texts, line art)."""
    try:
        p, why = _resolve(project, path)
        if p is None:
            return why
        # the running llama-server already sees (its mmproj is loaded): a second copy of the model on the GPU would
        # break «one GPU, one job» and the CLI it needed is not built here
        import io
        from PIL import Image
        from aurora.mdl_llm import LLM
        im = Image.open(p).convert("RGB")
        im.thumbnail((1600, 1600))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        text = re.sub(r"<think>.*?</think>", "", LLM(cfg).see(buf.getvalue(), _PROMPT + instruction, max_tokens=1024),
                      flags=re.S).strip()
        if not text:
            return "La visione non ha risposto."
        stats = _png_stats(p) if p.suffix.lower() == ".png" else ""
        return text + (f"\n\nControllo pixel: {stats}" if stats else "")
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")

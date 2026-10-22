# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🖼️ A project's cover on its card (owner, 23 Oct: «dare un'icona ai vari progetti che corrisponde ad esempio alle
immagini proof of concept o a schermate di codice se si tratta di algoritmi»).

In this order: the picture set from the page (the realistic view sets its own the first time it is drawn, or the
owner's «use as cover»), kept with the user's state, not in the project's history; a cover the project has itself
(cover.png/jpg at its root or in docs/); else its latest CAD model drawn here (prj_cover_cad); else a picture of its
main source file, coloured as in an editor. The made ones are kept until their source changes. None of these: the
card keeps its emoji.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from . import prj_policy, sys_config, sys_users_layout as L

MAX_IN = 4 * 2 ** 20
CODE = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".c", ".h", ".cpp", ".hpp", ".cc", ".rs", ".go", ".java", ".kt",
        ".swift", ".rb", ".php", ".sh", ".scad", ".jl", ".r", ".m", ".cs", ".lua", ".dart", ".zig"}
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "tests", "test", "build", "dist", "cad", "deposito",
        "deposito2", "docs", ".aurora"}
MAINS = ("main", "app", "__main__", "index", "server", "cli")
KEYWORDS = set("""def class return if elif else for while in import from as with try except finally raise yield lambda
not and or is None True False pass break continue async await global nonlocal function const let var new this export
default switch case fn pub mut impl struct enum use match package func type interface public private static void int
float double char bool include module translate rotate difference union intersection""".split())
COLORS = {"text": (201, 209, 217), "kw": (255, 123, 114), "str": (165, 214, 255), "com": (139, 148, 158),
          "num": (121, 192, 255), "bg": (13, 17, 23), "bar": (22, 27, 34), "name": (210, 168, 255)}
TOKEN = re.compile(r"(#.*|//.*)|(\"(?:\\.|[^\"])*\"?|'(?:\\.|[^'])*'?)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)|(\s+|.)")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def _root(cfg: sys_config.Config, project: str) -> Path:
    if not prj_policy.NAME.fullmatch(project or ""):
        raise ValueError("bad name")
    p = cfg.path("AURORA_PROJECTS_DIR") / project
    if not p.is_dir():
        raise ValueError("no such project")
    return p


def _state(cfg: sys_config.Config, project: str) -> Path:
    return L.place(cfg, "state", cfg.user) / "projects" / project


def main_file(root: Path) -> Path | None:
    """The file that says most what the project is: a main/app/index… first, else the largest source file."""
    found = []
    stack = [root]
    while stack and len(found) < 400:
        d = stack.pop()
        try:
            items = sorted(d.iterdir())
        except OSError:
            continue
        for x in items:
            if x.is_dir() and x.name not in SKIP and not x.name.startswith("."):
                stack.append(x)
            elif x.is_file() and x.suffix.lower() in CODE and not x.name.startswith("test"):
                try:
                    size = x.stat().st_size
                except OSError:
                    continue
                if 0 < size < 400_000:
                    found.append((x.stem.lower() in MAINS, size, x))
    return max(found, key=lambda f: (f[0], f[1]))[2] if found else None


def _lines(f: Path, n: int = 16) -> list[str]:
    text = f.read_text(encoding="utf-8", errors="replace").splitlines()
    out, started, doc = [], False, None
    for line in text:
        head = line.strip()
        if doc:                                          # inside the module's docstring: the code is what shows
            if doc in head:
                doc = None
            continue
        if not started and head[:3] in ('"""', "'''"):
            doc = None if head.count(head[:3]) > 1 else head[:3]
            continue
        if not started and (not head or head.startswith("#!") or "SPDX" in head or "Copyright" in head):
            continue
        started = True
        out.append(line.replace("\t", "    ")[:62])
        if len(out) >= n:
            break
    return out


def code_card(f: Path, label: str) -> bytes:
    """A picture of a source file's first lines, coloured as in a dark editor (JPEG, 960 × 540)."""
    from PIL import Image, ImageDraw, ImageFont
    W, H, S = 960, 540, 24
    img = Image.new("RGB", (W, H), COLORS["bg"])
    d = ImageDraw.Draw(img)
    font, small = ImageFont.truetype(FONT, S), ImageFont.truetype(FONT, 20)
    d.rectangle((0, 0, W, 44), fill=COLORS["bar"])
    for k, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse((18 + k * 26, 14, 34 + k * 26, 30), fill=c)
    d.text((110, 11), label[:60], font=small, fill=COLORS["com"])
    y, cw = 62, d.textlength("M", font=font)
    after_def = False
    for line in _lines(f, (H - 70) // (S + 6)):
        x = 24
        for m in TOKEN.finditer(line):
            com, s, num, word, other = m.groups()
            tok = m.group(0)
            col = COLORS["com"] if com else COLORS["str"] if s else COLORS["num"] if num else COLORS["text"]
            if word:
                col = COLORS["kw"] if word in KEYWORDS else COLORS["name"] if after_def else COLORS["text"]
                after_def = word in ("def", "class", "function", "fn", "func", "module", "struct")
            elif not (other and other.isspace()):
                after_def = False
            d.text((x, y), tok, font=font, fill=col)
            x += cw * len(tok)
        y += S + 6
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def kind(cfg: sys_config.Config, project: str) -> str:
    """set (from the page), repo (the project's own), cad (its model drawn here), code (from its source) or none."""
    root = _root(cfg, project)
    if (_state(cfg, project) / "cover.jpg").is_file():
        return "set"
    if _repo_cover(root):
        return "repo"
    if _model(root):
        return "cad"
    return "code" if main_file(root) else "none"


def _model(root: Path) -> Path | None:
    """The CAD model drawn last (its parts.json the newest) that has at least one part's STL."""
    found = [d for d in (root / "cad").glob("*") if (d / "parts.json").is_file() and (d / "part_0.stl").is_file()] \
        if (root / "cad").is_dir() else []
    return max(found, key=lambda d: (d / "parts.json").stat().st_mtime) if found else None


def _made(cfg: sys_config.Config, project: str, name: str, key: str, make) -> bytes | None:
    """A picture made here, kept with its key until the key changes."""
    cache = _state(cfg, project) / f"{name}.jpg"
    stamp = cache.with_suffix(".key")
    if cache.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8") == key:
        return cache.read_bytes()
    data = make()
    if data:
        cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache.write_bytes(data)
        stamp.write_text(key, encoding="utf-8")
    return data


def _repo_cover(root: Path) -> Path | None:
    for d in (root, root / "docs"):
        for ext in ("png", "jpg", "jpeg", "webp"):
            if (d / f"cover.{ext}").is_file():
                return d / f"cover.{ext}"
    return None


def get(cfg: sys_config.Config, project: str) -> tuple[bytes, str] | None:
    """The cover's bytes and type, or None (the card keeps its emoji)."""
    root = _root(cfg, project)
    mine = _state(cfg, project) / "cover.jpg"
    if mine.is_file():
        return mine.read_bytes(), "image/jpeg"
    own = _repo_cover(root)
    if own:
        return own.read_bytes(), {"png": "image/png", "webp": "image/webp"}.get(own.suffix[1:].lower(), "image/jpeg")
    m = _model(root)
    if m is not None:
        from . import prj_cover_cad, prj_print, prj_view
        def draw():
            listed = prj_print._listed(m)
            parts = [{**p, "material": prj_view.material(p)[0]} for p in listed]
            return prj_cover_cad.render(m, parts, prj_view.MATERIALS)
        data = _made(cfg, project, "cad", f"{m.name}:{(m / 'parts.json').stat().st_mtime_ns}", draw)
        if data:
            return data, "image/jpeg"
    f = main_file(root)
    if f is None:
        return None
    data = _made(cfg, project, "code", f"{f.relative_to(root)}:{f.stat().st_mtime_ns}",
                 lambda: code_card(f, str(f.relative_to(root))))
    return data, "image/jpeg"


def put(cfg: sys_config.Config, project: str, data: bytes) -> int:
    """The page's picture as the cover: a PNG or JPEG, made again as a JPEG at most 960 wide (nothing else kept)."""
    from PIL import Image
    _root(cfg, project)
    if not data or len(data) > MAX_IN or not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"):
        raise ValueError("a PNG or JPEG up to 4 MB")
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((960, 960))
    out = _state(cfg, project) / "cover.jpg"
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    out.write_bytes(buf.getvalue())
    return len(buf.getvalue())

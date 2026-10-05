# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Programming documentation as knowledge (owner, 2026-10-05: "so that Aurora can use programming as knowledge to
write code when needed"): official documentation with an open licence, harvested like any other source.

Two kinds of spec in harvest_sources.json, domain "programming":
- {"source": "docs", "set": "python"}: the Python documentation's own plain-text archive (docs.python.org/3/archives,
  the newest python-X.Y-docs-text.tar.bz2; PSF licence): the library, the tutorial, the language reference, the howtos
  and the FAQ, one text per page;
- {"source": "docs", "set": "github", "repo", "branch", "prefix", "suffix", "licence", "url"}: the Markdown files of a
  documentation repository under `prefix` (the Rust book, MDN's JavaScript pages…), one per page; `url` is the
  page's public address with {path} for the file's path inside prefix, without the suffix.
"""
from __future__ import annotations

import io
import re
import tarfile

from . import sys_config

ARCHIVES = "https://docs.python.org/3/archives/"
PY_PARTS = ("library/", "tutorial/", "reference/", "howto/", "faq/")


def _cache(cfg: sys_config.Config):
    d = cfg.path("AURORA_STATUS_DIR") / "harvest" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _python(fetch, cfg, domain, st, want, seen, Doc) -> list:
    if "files" not in st:
        names = sorted(set(re.findall(r"python-(\d+\.\d+)-docs-text\.tar\.bz2", fetch(ARCHIVES).text)),
                       key=lambda v: tuple(int(x) for x in v.split(".")))
        if not names:
            raise ValueError("no text archive of the Python documentation found")
        archive = f"python-{names[-1]}-docs-text.tar.bz2"
        (_cache(cfg) / archive).write_bytes(fetch(ARCHIVES + archive).content)
        with tarfile.open(_cache(cfg) / archive, "r:bz2") as tar:
            files = sorted(m.name for m in tar.getmembers() if m.isfile() and m.name.endswith(".txt")
                           and any(f"/{p}" in m.name for p in PY_PARTS))
        st.update(files=files, archive=archive, version=names[-1], pos=0)
    out = []
    with tarfile.open(_cache(cfg) / st["archive"], "r:bz2") as tar:
        while st["pos"] < len(st["files"]) and len(out) < want:
            name = st["files"][st["pos"]]
            st["pos"] += 1
            rel = name.split("/", 1)[1]                              # inside python-X.Y-docs-text/
            key = f"docs:python:{rel}"
            if key in seen:
                continue
            text = tar.extractfile(name).read().decode("utf-8", "replace")
            if len(text) < 400:
                continue
            title = next((x.strip() for x in text.splitlines() if x.strip() and not set(x.strip()) <= set("=*-#")), rel)
            out.append(Doc(key, domain, f"Python {st['version']}: {title}"[:200], key, "PSF-2.0",
                           f"https://docs.python.org/{st['version']}/{rel[:-4]}.html",
                           name=re.sub(r"\W+", "_", rel)[:100] + ".txt", data=text.encode()))
    st["done"] = st["pos"] >= len(st["files"])
    return out


def clean_markdown(text: str) -> tuple[str, str]:
    """(title, text) of a documentation page: the front matter's title, MDN's {{macros}} removed."""
    title = ""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if m:
        t = re.search(r"^title:\s*(.+)$", m.group(1), re.M)
        title = t.group(1).strip().strip("'\"") if t else ""
        text = text[m.end():]
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    if not title:
        h = re.search(r"^#\s+(.+)$", text, re.M)
        title = h.group(1).strip() if h else ""
    return title, text.strip()


def _github(fetch, cfg, domain, spec, st, want, seen, Doc) -> list:
    repo, prefix, suffix = spec["repo"], spec.get("prefix", ""), spec.get("suffix", ".md")
    if "files" not in st:
        tree = fetch(f"https://api.github.com/repos/{repo}/git/trees/{spec.get('branch', 'main')}", recursive=1).json()
        st.update(files=sorted(x["path"] for x in tree.get("tree", []) if x.get("type") == "blob"
                               and x["path"].startswith(prefix) and x["path"].endswith(suffix)), pos=0)
    out = []
    while st["pos"] < len(st["files"]) and len(out) < want:
        path = st["files"][st["pos"]]
        st["pos"] += 1
        key = f"docs:{repo}:{path}"
        if key in seen:
            continue
        raw = fetch(f"https://raw.githubusercontent.com/{repo}/{spec.get('branch', 'main')}/{path}").text
        title, text = clean_markdown(raw)
        if len(text) < 400:
            continue
        inner = path[len(prefix):-len(suffix)] if suffix else path[len(prefix):]
        url = spec.get("url", f"https://github.com/{repo}/blob/{spec.get('branch', 'main')}/{{path}}").format(
            path=re.sub(r"/index$", "", inner))
        out.append(Doc(key, domain, f"{spec.get('label', repo)}: {title or inner}"[:200], key, spec["licence"], url,
                       name=re.sub(r"\W+", "_", inner)[:100] + ".md", data=text.encode()))
    st["done"] = st["pos"] >= len(st["files"])
    return out


def docs(fetch, cfg, domain: str, spec: dict, st: dict, want: int, deep: bool, seen: set) -> list:
    from .kno_sources import Doc
    if spec.get("set") == "python":
        return _python(fetch, cfg, domain, st, want, seen, Doc)
    if spec.get("set") == "github":
        return _github(fetch, cfg, domain, spec, st, want, seen, Doc)
    raise ValueError(f"docs: unknown set {spec.get('set')!r}")

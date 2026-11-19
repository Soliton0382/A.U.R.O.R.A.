# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "projects": Aurora starts and keeps software projects, ready for GitHub.

Each project is a git repository in AURORA_PROJECTS_DIR/<name>. Scaffolding uses GitHub's own
licence and .gitignore templates; the README says the project was made with Aurora (EU AI Act).

C674: this plugin runs no git on an existing project and holds no token. A project's .git is written by code Aurora
runs, and six reviews in a row found a new way through git's own files (C658-C674): the commit, publish and push tools
are gone, project_list and project_tree read the folder without git, and only project_create runs git — on the folder
it has just made. Commits and the package to publish are made by the user in the project's cage (the Projects page's
«📦 Pubblica», prj_package, or its terminal; guide: prj_gitguide); the push is the user's, from their own computer.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import httpx
from aurora import prj_gitguide, prj_gitsafe, prj_safeio, sys_config, sys_disclosure
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
BASE = cfg.path("AURORA_PROJECTS_DIR")


server = MCPServer("projects", version="1.0")


def tool(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return server.tool()(wrapped)



def _project(name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name):
        raise ValueError("project names: lowercase letters, digits, . _ - (max 64)")
    return BASE / name


def _inside(project: Path, path: str, write: bool = False) -> str:
    """The path as the project sees it, checked lexically; the file is then opened from the project's folder one
    component at a time, never through a link (prj_safeio, C643: a check by name and an open by name let a run of
    the project swap a folder for a link in between)."""
    try:
        r = prj_safeio.norm(path, project.resolve())
    except ValueError:
        raise ValueError(f"outside the project: {path}") from None
    parts = set(r.split("/"))
    if ".git" in parts:
        raise ValueError("the .git folder is git's own")
    if write and (r == "." or ".venv" in parts):        # C629: a .pth written there ran in pip
        raise ValueError("the .venv folder is project_install's own")
    return r


def _git_env(**extra: str) -> dict:
    """git's environment (C591, C658): never this plugin's token or keys (the push gets the token for GitHub only), no
    system or global configuration, and a repository is looked for in the project itself, never above it."""
    return prj_gitsafe.env(BASE, extra)


def _busy(project: Path) -> bool:
    """A long run of the project is going (C658): its folder may change under git, so git waits."""
    try:
        from aurora import prj_longrun
        return prj_longrun.busy(cfg, project.name)
    except Exception:  # noqa: BLE001 — the engine off or not importable: nothing is going
        return False


DEEP = {("add",), ("commit",), ("status",), ("bundle",)}   # the commands that read the whole work tree


def _git(project: Path, *args: str, extra_env: dict | None = None) -> str:
    author = cfg["AURORA_GIT_AUTHOR_NAME"] or "Aurora"
    email = cfg["AURORA_GIT_AUTHOR_EMAIL"] or "aurora@localhost"
    env = prj_gitsafe.env(BASE, dict(GIT_AUTHOR_NAME=author, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME=author,
                                     GIT_COMMITTER_EMAIL=email, **(extra_env or {})), project=project)
    # a project's .git is not trusted (C420, C658, C670): bubblewrap does not nest inside this plugin's own cage, so
    # git runs here only on a repository whose configuration holds the keys git init and remote add write — a key no
    # list foresaw is refused too —, never on one nested in it or asking for Git LFS; the repository is named
    # (GIT_DIR), never looked for, and the known programs are switched off again by -c
    if args[:1] != ("init",) and (why := prj_gitsafe.refusal(project, deep=args[:1] in DEEP)):
        raise ToolError(f"git not run on {project.name}: {why} (C670)")
    if _busy(project):
        raise ToolError(f"a long run of {project.name} is going: git waits until it ends (C658)")
    r = subprocess.run(["git", *prj_gitsafe.args(), "-c", f"safe.directory={project}", *args], cwd=project, env=env,
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise ToolError(f"git {args[0]}: {(r.stderr or r.stdout).strip()[:1500]}")
    return (r.stdout + r.stderr).strip()



@tool
def project_list() -> str:
    """The projects, with their last commit."""
    BASE.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted(x for x in BASE.iterdir() if (x / ".git").is_dir() and not (x / ".git").is_symlink()):
        rows.append(f"{p.name}")                     # C674: no git on an existing project's folder
    return "\n".join(rows) or "no projects"


@tool
def project_create(name: str, description: str, license: str = "MIT", language: str = "Python",
                   holder: str = "") -> str:
    """Create a project ready for GitHub: README, LICENSE (GitHub template, e.g. MIT, Apache-2.0, GPL-3.0),
    .gitignore for the language, CHANGELOG, src/; git repository with a first commit on 'main'."""
    p = _project(name)
    if p.exists():
        raise ValueError(f"project {name} exists")
    lic = httpx.get(f"https://api.github.com/licenses/{license.lower()}", timeout=30)
    if lic.status_code != 200:
        raise ValueError(f"unknown licence {license!r} (GitHub has e.g. mit, apache-2.0, gpl-3.0, bsd-3-clause)")
    who = holder or cfg["AURORA_GITHUB_OWNER"] or cfg["AURORA_GIT_AUTHOR_NAME"]
    body = lic.json()["body"].replace("[year]", time.strftime("%Y")).replace("[fullname]", who)
    gi = httpx.get(f"https://api.github.com/gitignore/templates/{language}", timeout=30)
    ignore = gi.json()["source"] if gi.status_code == 200 else ""
    (p / "src").mkdir(parents=True)
    (p / "src" / ".gitkeep").write_text("")
    readme = f"# {name}\n\n{description}\n\n## License\n\n{lic.json()['name']} — see [LICENSE](LICENSE).\n"
    (p / "README.md").write_text(sys_disclosure.mark_document(readme, "en", cfg))
    (p / "LICENSE").write_text(body)
    (p / ".gitignore").write_text(ignore)
    (p / "CHANGELOG.md").write_text(f"# Changelog\n\n## [0.1.0] - {time.strftime('%Y-%m-%d')}\n\n- Project created.\n")
    prj_gitguide.ensure(p)                            # C674: how the user commits and publishes, from the terminal
    _git(p, "init", "-b", "main")                     # a folder made just now: no .git of anyone's yet
    _git(p, "add", "-A")
    _git(p, "commit", "-m", "Initial scaffold")
    return f"project {name} created in {p} ({lic.json()['spdx_id']}, .gitignore {language if ignore else 'none'})"


@tool
def project_tree(name: str) -> str:
    """The files of a project."""
    p = _project(name)
    return "\n".join(r for r, d, _ in prj_safeio.walk(p, skip=frozenset({".git", ".venv", "__pycache__"}))   # C674:
                     if not d) or "empty"                                                       # no git, no link entered


@tool
def project_read_file(name: str, path: str, offset: int = 0) -> str:
    """Read a file of a project (a PDF: its text, page by page), 20,000 characters at a time: a longer one says where
    it stops — read the rest with offset (C376: a long file was cut without a word)."""
    project = _project(name)
    f = _inside(project, path)
    if f.lower().endswith(".pdf"):                      # its raw bytes say nothing and look like data to mask (C310)
        import io
        from pypdf import PdfReader
        pages = PdfReader(io.BytesIO(prj_safeio.read_bytes(project.resolve(), f))).pages
        text = "\n\n".join(f"--- page {i}/{len(pages)} ---\n{p.extract_text() or '(no text: a drawing)'}"
                           for i, p in enumerate(pages, 1))
    else:
        text = prj_safeio.read_text(project.resolve(), f)
    start = max(0, int(offset or 0))
    part = text[start:start + READ_MAX]
    if start + READ_MAX < len(text):
        part += (f"\n\n[… {len(text) - start - READ_MAX} more characters of {len(text)}: "
                 f"project_read_file(name, path, offset={start + READ_MAX}) for the rest]")
    return part


@tool
def project_write_file(name: str, path: str, content: str, append: bool = False) -> str:
    """Write a file of a project (new or whole). append=true adds the content at the end instead: a long document is
    written a section per call (C397: a whole paper in one call ran past the model's budget and was never written)."""
    project = _project(name)
    root, f = project.resolve(), _inside(project, path, write=True)
    if append and prj_safeio.is_file(root, f):
        prj_safeio.write_text(root, f, content, append=True)
        return f"appended to {path} ({len(content.splitlines())} lines, {len(prj_safeio.read_text(root, f).splitlines())} in all)"
    prj_safeio.write_text(root, f, content)
    return f"written {path} ({len(content.splitlines())} lines)"


@tool
def project_edit_file(name: str, path: str, old: str, new: str) -> str:
    """Change one part of a project's file without writing it all again: `old` must occur exactly once in the file
    (copy it from project_read_file, with its spaces), and is replaced by `new`. For a long document, edit a sentence
    or a section at a time (C398: a model that cannot write a whole paper in one call could not fix one line of it)."""
    project = _project(name)
    root, f = project.resolve(), _inside(project, path, write=True)
    if not prj_safeio.is_file(root, f):
        raise ToolError(f"no file {path}")
    text = prj_safeio.read_text(root, f)
    n = text.count(old) if old else 0
    if n != 1:
        raise ToolError(f"`old` occurs {n} times in {path}: it must occur exactly once (copy a longer, exact passage)")
    prj_safeio.write_text(root, f, text.replace(old, new, 1))
    return f"edited {path}: {len(old.splitlines()) or 1} lines replaced by {len(new.splitlines()) or 1}"


def _remove_dist(site: Path, name: str) -> None:
    """The files an installed distribution lists (its RECORD), inside the project's site-packages only (C664)."""
    from importlib import metadata
    key = name.lower().replace("_", "-")
    base = site.resolve()
    for d in metadata.distributions(path=[str(site)]):
        if (d.metadata["Name"] or "").lower().replace("_", "-") != key:
            continue
        for f in d.files or []:
            q = (site / f).resolve() if not (site / f).is_symlink() else site / f
            if q.is_relative_to(base) and (q.is_file() or q.is_symlink()):
                q.unlink()
        info = Path(str(d._path)) if hasattr(d, "_path") else None   # the dist-info folder itself
        if info and info.resolve().is_relative_to(base) and info.is_dir():
            import shutil
            shutil.rmtree(info, ignore_errors=True)


# C692: names a wheel's script never takes in .venv/bin (first on the PATH of the user's own cages: the terminal, the
# package button): the programs the user's commit and bundle run, the shells, the interpreters and their tools
SYSTEM_NAMES = frozenset("""git git-upload-pack git-receive-pack git-shell gitk ssh scp sftp ssh-agent gpg gpg2 gpgv
bash sh dash zsh fish ksh csh tcsh busybox env sudo su doas pkexec login nohup setsid xargs exec time timeout nice
python python3 pip pip3 pipx uv virtualenv pytest py.test ipython jupyter node npm npx perl ruby
ls cat cp mv rm ln mkdir rmdir chmod chown touch find grep sed awk gawk head tail sort uniq wc tr cut tee diff patch
tar gzip gunzip zip unzip xz curl wget make cmake gcc cc ld vi vim nano less more man which whereis id whoami ps
kill pkill pgrep bwrap prlimit systemctl journalctl""".split())
SYSTEM_DIRS = ("/usr/bin", "/bin", "/usr/local/bin", "/usr/sbin", "/sbin")


def _system_name(name: str) -> bool:
    """A script's name that would stand for a program of the system: in SYSTEM_NAMES, starting with python/pip/git,
    any name found in SYSTEM_DIRS, or not a plain ASCII name at all."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", name or ""):
        return True
    low = name.lower()
    if low in SYSTEM_NAMES or low.startswith(("python", "pip", "git")):
        return True
    return any(os.path.lexists(os.path.join(d, name)) for d in SYSTEM_DIRS)


def _merge(stage: Path, site: Path, env: Path, project: Path) -> list[str]:
    """The staged install copied file by file into site-packages (a namespace folder of another library kept, C664);
    its command-line scripts into .venv/bin, run by the project's own python (C664: in site-packages/bin they were on
    no PATH and ran Aurora's interpreter without the project's libraries). The scripts left out (O4: named as the
    environment's interpreter or a system program, C692), to be said in the result."""
    import shutil
    skipped: list[str] = []
    bindir = env / ("Scripts" if os.name == "nt" else "bin")
    py = bindir / ("python.exe" if os.name == "nt" else "python")
    for src in stage.rglob("*"):
        if src.is_symlink() or not src.is_file():
            continue
        rel = src.relative_to(stage)
        if rel.parts[0] in ("bin", "Scripts"):
            data = src.read_bytes()
            if data.startswith(b"#!"):
                data = b"#!" + str(py).encode() + data[data.index(b"\n"):]
            dst = bindir / rel.name
            if dst.name.startswith("python") or dst.name.startswith("activate") or _system_name(dst.name):
                skipped.append(dst.name)
                continue                               # never the environment's own interpreter or scripts, nor a
            if dst.is_symlink():                       # system program's name (C692: a wheel's «git» ran in the
                dst.unlink()                           # user's commit)
            dst.write_bytes(data)
            dst.chmod(0o755)
            continue
        dst = site / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink():
            dst.unlink()
        shutil.copyfile(src, dst)
    return sorted(set(skipped))


READ_MAX = 20000
SPEC = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}(\[[A-Za-z0-9,_-]{1,60}\])?((==|>=|<=|~=|<|>)[0-9][0-9A-Za-z.*+!-]{0,30})?")


@tool
def project_install(name: str, packages: list[str]) -> str:
    """Install Python libraries the project needs (owner, 2026-10-21: «dalle la capacità di installare nei progetti
    tutto quello che serve»), e.g. ["magpylib==6.0.0", "pandas"]. They go into the project's own environment
    (<project>/.venv), which sees Aurora's libraries without changing them, so only what is missing is fetched; wheels
    only (no package's code runs while installing); the versions written to requirements-aurora.txt. run_in_project
    uses that environment by itself: `python script.py` imports them. At most 10 packages a call."""
    import sys
    project = _project(name)
    if not project.is_dir():
        raise ToolError(f"no project {name}")
    packages = [str(x).strip() for x in (packages or []) if str(x).strip()]
    if not packages or len(packages) > 10 or not all(SPEC.fullmatch(x) for x in packages):
        raise ToolError("1 to 10 packages, as «name» or «name==1.2.3» (extras like «name[plot]» allowed)")
    env, t0 = project / ".venv", time.time()
    py = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")      # a venv's layout on each system
    if env.is_symlink() or (env.exists() and not env.is_dir()):
        raise ToolError(f"{name}/.venv is a link or a file: not made by project_install (C629); ask the owner to remove it")
    if py.exists() and os.name != "nt" and not (py.is_symlink() and py.resolve() == Path(sys.executable).resolve()):
        raise ToolError(f"{name}/.venv was not made by project_install (its python is not Aurora's): its code would "
                        "run here (C629); ask the owner to remove it")
    if not py.exists():                               # the project's own environment, on Aurora's Python
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(env)], check=True, capture_output=True,
                       timeout=120)
        site = next(env.glob("lib/python*/site-packages"), env / "Lib" / "site-packages")
        aurora = next(p for p in sys.path if p.endswith("site-packages") and Path(p).is_dir())
        (site / "aurora.pth").write_text(aurora + "\n", encoding="utf-8")     # Aurora's libraries seen, not copied
        root = project.resolve()
        if prj_safeio.is_file(root, ".gitignore") and ".venv/" not in prj_safeio.read_text(root, ".gitignore").split():
            prj_safeio.write_text(root, ".gitignore", prj_safeio.read_text(root, ".gitignore").rstrip("\n") + "\n.venv/\n")
    if _busy(project):
        raise ToolError(f"a long run of {name} is going: libraries are installed once it has ended (C658)")
    clean = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "HOME", "SSL_CERT_FILE", "SSL_CERT_DIR",
                                        "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL",
                                        "PIP_FIND_LINKS", "PIP_NO_INDEX", "PIP_CERT") if k in os.environ}   # C629: no token
    # C655: the project's own interpreter never runs here (a .pth in a wheel it installed ran at the next «pip
    # --python»): Aurora's pip resolves against Aurora's libraries (wheels only, nothing of theirs runs), then puts what
    # is missing into the project's site-packages with --target, and the list is read from the metadata files
    import json
    import shutil
    import tempfile
    from importlib import metadata
    common = ["--only-binary=:all:", "--no-input", "--disable-pip-version-check", "--no-cache-dir"]
    site = next(env.glob("lib/python*/site-packages"), env / "Lib" / "site-packages")
    # C664: what the project has already is kept unless asked again (constraints: read from its metadata files,
    # nothing of it imported — a PYTHONPATH would have let a module of it run inside pip)
    have = {d.metadata["Name"].lower().replace("_", "-"): d.version
            for d in metadata.distributions(path=[str(site)]) if d.metadata["Name"]}
    asked = {re.split(r"[\[=<>~!]", x, maxsplit=1)[0].lower().replace("_", "-") for x in packages}
    skipped: list[str] = []                           # O4: the scripts left out, said in the result
    with tempfile.TemporaryDirectory(prefix="aurora-install-") as tmp:
        cons = Path(tmp) / "constraints.txt"
        cons.write_text("".join(f"{n}=={v}\n" for n, v in have.items() if n not in asked), encoding="utf-8")
        plan = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--quiet", "--report", "-",
                               "-c", str(cons), *common, *packages], capture_output=True, text=True, timeout=900,
                              env=clean)
        if plan.returncode:
            raise ToolError(f"pip refused: {(plan.stderr or plan.stdout).strip()[-1200:]}")
        want = [f"{i['metadata']['name']}=={i['metadata']['version']}"
                for i in json.loads(plan.stdout or "{}").get("install", [])
                if have.get(i["metadata"]["name"].lower().replace("_", "-")) != i["metadata"]["version"]]
        if want:
            stage = Path(tmp) / "stage"
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--target", str(stage), "--no-deps", *common,
                                *want], capture_output=True, text=True, timeout=900, env=clean)
            if r.returncode:
                raise ToolError(f"pip refused: {(r.stderr or r.stdout).strip()[-1200:]}")
            for w in want:                            # C664: the old version's files go first (--upgrade with
                _remove_dist(site, w.split("==")[0])  # --target left two dist-info and cut namespace folders)
            skipped = _merge(stage, site, env, project)
    listed = sorted({f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions(path=[str(site)])
                     if d.metadata["Name"]}, key=str.lower)
    prj_safeio.write_text(project.resolve(), "requirements-aurora.txt",
                          "# what Aurora installed for this project (project_install), beside Aurora's own libraries\n"
                          + "".join(x + "\n" for x in listed))
    done = [" ".join(want)] if want else []
    left = (f" Scripts not installed — named as a system program or the environment's own (C692): "
            f"{', '.join(skipped[:20])}{' …' if len(skipped) > 20 else ''}; run them as `python -m <module>`."
            if skipped else "")
    return (f"Installed in {time.time() - t0:.0f} s into {name}/.venv: {done[0] if done else 'already there'}. "
            f"run_in_project uses it: `python your_script.py` imports them.{left}")


if __name__ == "__main__":
    server.run("stdio")

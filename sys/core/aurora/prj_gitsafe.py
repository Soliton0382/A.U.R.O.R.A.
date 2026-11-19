# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""git on a project's own .git, from outside every cage (C658, C670).

A project's .git is not trusted: a caged command (prj_run, a long run) can write one, or turn the project's folder
itself into a repository, and git runs what its configuration names — core.fsmonitor at «status», a filter's clean
command at «add», a signing program at «commit» (gpg.ssh.defaultKeyCommand), a driver, an ssh command.

C658 kept a list of the dangerous keys and the fifth review found three more ways around it (a bare repository at the
project's root, config.worktree and commondir, a signing command the list did not name). C670 turns it around:

- the API reads in a cage of its own (prj_browse), where whatever the configuration names runs sealed;
- where no cage can start (inside a plugin's own cage bubblewrap does not nest: measured, 20 Nov), git runs only on a
  repository whose configuration holds nothing but the keys `git init`, `git clone` and `git remote add` write
  (ALLOW): everything else refuses the repository, so a key no list foresaw is refused too;
- the repository is never looked for: GIT_DIR and GIT_WORK_TREE are given (a bare repository at the root is never
  used), and the structures that bring another configuration in (commondir, config.worktree, worktrees/, a .git file
  or link) refuse it;
- a second layer of -c overrides switches the known programs off anyway.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# the only keys a project's .git/config may hold (lower case; git's section and key names are case-insensitive):
# what `git init`, `git clone`, `git remote add` and `git branch -u` write, and a few plain behaviours. Nothing that
# names a program, a file, another work tree or another configuration
ALLOW = re.compile(
    r"^(core\.(repositoryformatversion|filemode|bare|logallrefupdates|ignorecase|precomposeunicode|symlinks|"
    r"autocrlf|eol|safecrlf|quotepath|checkstat|trustctime)|extensions\.objectformat|"
    r"remote\..+\.(url|fetch)|branch\..+\.(remote|merge|rebase)|user\.(name|email)|init\.defaultbranch|"
    r"gc\.auto|pull\.rebase)$")

# what a reading git (status, log, ls-files, branch) switched off by name may leave in a configuration when no cage
# starts (prj_browse._git_bare): these keys run nothing there once the overrides are given
READ_NEUTRAL = re.compile(r"^(core\.(fsmonitor|hookspath|pager|attributesfile|sshcommand|gitproxy|askpass|editor)|"
                          r"filter\..+\.(clean|smudge|process|required)|gpg\.(.+\.)?program|credential\..*helper|"
                          r"credential\.helper|sequence\.editor|protocol\..*allow|url\..+\.(insteadof|pushinsteadof)|"
                          r"http\..*(proxy|sslverify|cookiefile)|commit\.gpgsign|tag\.gpgsign|color\..+|"
                          r"user\.signingkey|gpg\.format)$")

# the second layer: given to every host-side git, after `git` and before the subcommand
ARGS = ["-c", "core.fsmonitor=false", "-c", f"core.hooksPath={os.devnull}", "-c", f"core.attributesFile={os.devnull}",
        "-c", "log.showSignature=false", "-c", "core.pager=cat", "-c", "protocol.file.allow=never",
        "-c", "protocol.ext.allow=never", "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false",
        "-c", "safe.bareRepository=explicit", "-c", "submodule.recurse=false", "-c", "diff.ignoreSubmodules=all",
        "-c", "status.submoduleSummary=false", "-c", "push.recurseSubmodules=no", "-c", "fetch.recurseSubmodules=false",
        "-c", "core.sshCommand=false", "-c", "core.askPass=", "-c", "credential.helper="]

SCAN_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
SCAN_MAX = 200_000


def args() -> list[str]:
    """The -c overrides every host-side git gets (after `git`, before the subcommand)."""
    return list(ARGS)


def env(base: Path | str, extra: dict | None = None, inherit: dict | None = None,
        project: Path | str | None = None) -> dict:
    """git's environment: no system or global configuration, no prompt, no optional lock, nothing of git's own
    variables inherited; with `project` the repository is named (GIT_DIR = <project>/.git, the work tree the project),
    never looked for — a bare repository at the project's root is never used (C670)."""
    src = dict(os.environ if inherit is None else inherit)
    for k in list(src):
        if k.startswith("GIT_") or k == "AURORA_GITHUB_TOKEN" or k.startswith(("AURORA_PLUGIN_SECRET_",
                                                                               "AURORA_SEAL_KEY_")):
            src.pop(k)
    named = {"GIT_DIR": str(Path(project) / ".git"), "GIT_WORK_TREE": str(project)} if project is not None else {}
    return dict(src, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
                GIT_OPTIONAL_LOCKS="0", GIT_CEILING_DIRECTORIES=str(base), **named, **(extra or {}))


def _config(cfgfile: Path) -> list[tuple[str, str]]:
    """The (key, value) pairs of one configuration file, read as text by git without following includes (reading runs
    nothing)."""
    r = subprocess.run(["git", "config", "--file", str(cfgfile), "--no-includes", "-z", "--list"],
                       capture_output=True, text=True, timeout=20,
                       env=env(cfgfile.parent, inherit={"PATH": os.environ.get("PATH", "/usr/bin:/bin")}))
    if r.returncode != 0:
        raise ValueError("its git configuration cannot be read")
    out = []
    for item in r.stdout.split("\0"):
        if item:
            k, _, v = item.partition("\n")
            out.append((k.strip().lower(), v))
    return out


def _config_keys(cfgfile: Path) -> list[str]:
    return [k for k, _ in _config(cfgfile)]


def structure(project: Path) -> str:
    """Why the project's .git is not a plain repository of its own ("" when it is, or when there is none)."""
    g = Path(project) / ".git"
    if g.is_symlink():
        return ".git is a link"
    if not g.exists():
        return ""
    if not g.is_dir():
        return ".git is not a folder (a «gitdir:» file points elsewhere)"
    for part, why in (("commondir", "takes its configuration from another folder"),
                      ("config.worktree", "has a per-worktree configuration"),
                      ("worktrees", "has linked work trees")):
        if os.path.lexists(g / part):
            return f".git/{part} exists: it {why}"
    cfgfile = g / "config"
    if cfgfile.is_symlink():
        return ".git/config is a link"
    return ""


def scan(project: Path) -> tuple[list[str], list[str], bool]:
    """The repositories nested in the project (a .git below its root), the .gitattributes asking for Git LFS, and
    whether the walk stopped at SCAN_MAX entries."""
    nested, lfs, n = [], [], 0
    root = Path(project)
    for dirpath, dirs, files in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        n += len(dirs) + len(files)
        if n > SCAN_MAX:
            return nested, lfs, True
        for name in (*dirs, *files):
            if name == ".git" and rel != Path("."):
                nested.append((rel / name).as_posix())
        if ".gitattributes" in files:
            try:
                if "filter=lfs" in (Path(dirpath) / ".gitattributes").read_text(encoding="utf-8", errors="replace"):
                    lfs.append((rel / ".gitattributes").as_posix())
            except OSError:
                pass
        dirs[:] = [d for d in dirs if d not in SCAN_SKIP and not os.path.islink(os.path.join(dirpath, d))]
    return nested, lfs, False


def refusal(project: Path, tolerate: re.Pattern | None = None, deep: bool = False) -> str:
    """Why no git must run on this project ("" when it may): the structure (structure()), then any key of its
    configuration outside ALLOW (`tolerate`: keys the caller switches off itself), core.bare not false; `deep`: also a
    repository nested in it or a .gitattributes asking for Git LFS (C670)."""
    project = Path(project)
    why = structure(project)
    if why:
        return why
    cfgfile = project / ".git" / "config"
    if cfgfile.exists():
        try:
            pairs = _config(cfgfile)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            return f".git/config: {e}"
        bad = sorted({k for k, _ in pairs if not ALLOW.match(k) and not (tolerate and tolerate.match(k))})
        if bad:
            return ("its .git/config sets " + ", ".join(bad[:6]) + " — only the keys git init, clone and remote add "
                    "write are accepted (remove the others from .git/config)")
        if any(k == "core.bare" and v.strip().lower() not in ("false", "no", "off", "0") for k, v in pairs):
            return "its .git/config says the repository is bare"
    if deep:
        nested, lfs, capped = scan(project)
        if nested:
            return (f"a repository is nested in it ({', '.join(nested[:3])}): submodules and nested repositories "
                    "are not handled here (move them out, or remove their .git)")
        if lfs:
            return (f"{lfs[0]} asks for Git LFS, which is not run here: the large files would be committed whole "
                    "(commit and push this project with git-lfs yourself)")
        if capped:
            return f"more than {SCAN_MAX} files: nested repositories cannot be ruled out"
    return ""


def run(project: Path, *a: str, base: Path | str | None = None, extra_env: dict | None = None,
        timeout: int = 60) -> subprocess.CompletedProcess:
    """git in the project, hardened and with the repository named; ValueError when `refusal` names a reason."""
    project = Path(project)
    why = refusal(project)
    if why:
        raise ValueError(f"git not run on {project.name}: {why} (C670)")
    return subprocess.run(["git", *args(), "-c", f"safe.directory={project}", *a], cwd=project,
                          env=env(base or project.parent, extra_env, project=project), capture_output=True, text=True,
                          timeout=timeout)


def clone_command(full: str, dest: Path | str, token: str) -> tuple[list[str], dict]:
    """git's command line and environment for a clone from GitHub (C671): the token as a request header through the
    environment (GIT_CONFIG_COUNT), never on the command line — /proc/<pid>/cmdline is readable by every process of the
    machine; no system or user configuration, https only, no submodules, no hooks."""
    import base64
    e = env(Path(dest).parent)
    if token:
        e.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraHeader", "GIT_CONFIG_VALUE_0":
                  "Authorization: Basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()})
    cmd = ["git", *args(), "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
           "clone", "--quiet", "--no-recurse-submodules", f"https://github.com/{full}.git", str(dest)]
    return cmd, e


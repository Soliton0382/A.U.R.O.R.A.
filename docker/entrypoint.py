#!/opt/aurora/.venv/bin/python
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora in Docker, cloud reasoner only (owner, 2026-10-09: «un bel docker cloud only di aurora ideato per macchine con
poche risorse»): the container's first process. It prepares, then runs and watches Aurora's services.

Every start:
  1. the data in /data (one volume): the folders Aurora writes are links to it — vault, status, logs, models, the users'
     folders, HTTPS, the key (/etc/aurora), the signature, Caddy's local authority — so a new image keeps everything;
  2. the settings: the first start writes /data/.env from the container's AURORA_* variables (docker/.env), every start
     takes the ports and the domain from them again (Docker maps the same ports outside);
  3. the per-user layout, the encoder and re-ranker (Hugging Face, pinned, checked), the installation's key and
     signature (again when the image changed: pulling a new image is the owner's update), the Caddyfile;
  4. the services, each restarted when it ends; `systemctl` in the container is a stand-in (docker/systemctl) that
     asks this process, so the Status page, the restarts from Settings and Caddy's reload work as with systemd.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/opt/aurora")
DATA = Path("/data")
RUN = Path("/run/aurora")
PY = str(ROOT / ".venv" / "bin" / "python")
SCRIPT = ROOT / "sys" / "core" / "script"
DIRS = {"sys/vault": "vault", "sys/status": "status", "sys/logs": "logs", "sys/models": "models", "sys/https": "https",
        "sys/sandbox": "sandbox", "usr": "usr"}
FILES = {"sys/core/ethics/MANIFEST.json": "ethics/MANIFEST.json", "sys/core/ethics/exemption.sig": "ethics/exemption.sig",
         "sys/core/ethics/private_to_cloud.sig": "ethics/private_to_cloud.sig"}
ELSEWHERE = {Path("/etc/aurora"): "keys", Path("/root/.local/share/caddy"): "caddy"}
# taken from the container's environment at every start (Docker publishes the same ports outside)
ALWAYS = ("AURORA_HTTPS_PORT", "AURORA_HTTP_PORT", "AURORA_DOMAIN")      # the aliases: first start, then the 🔒 page
# never from the environment: the container's own layout
# the services run as root inside the container (its only user: Caddy's authority lives in its home, /root)
FIXED = {"AURORA_ROOT": str(ROOT), "AURORA_LLM_BACKEND": "cloud",
         "AURORA_SERVICE_USER": "root", "AURORA_UPDATE_MODE": "off",      # updates come with the image (no git here)
         "AURORA_CADDY_BIN": "/usr/bin/caddy", "AURORA_PDFTOTEXT_BIN": "/usr/bin/pdftotext"}
UNITS = {
    "aurora-models": ([PY, str(SCRIPT / "svc_models.py")], 10),      # nice 10: the CPU is shared (C216)
    "aurora-api": ([PY, str(SCRIPT / "svc_api.py")], 0),
    "aurora-rem": ([PY, str(SCRIPT / "svc_rem.py")], 10),
    "aurora-harvester": ([PY, str(SCRIPT / "svc_harvester.py")], 10),
    "aurora-sentinel": ([PY, str(SCRIPT / "svc_sentinel.py")], 0),
    "aurora-https": (["/usr/bin/caddy", "run", "--config", str(ROOT / "sys/https/Caddyfile"), "--adapter", "caddyfile"], 0),
}


def say(msg: str) -> None:
    print(f"[aurora] {msg}", flush=True)


def run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if check and r.returncode != 0:
        say(f"FAILED: {' '.join(cmd)}\n{(r.stdout + r.stderr).strip()[-1500:]}")
        sys.exit(1)
    return r


# ---- 1. the data ---------------------------------------------------------------------------------------------------
def link(path: Path, target: Path, folder: bool) -> None:
    """`path` a link to `target` in the volume; what the image or an earlier start left there is moved in first."""
    (target if folder else target.parent).mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        if path.resolve() == target.resolve():
            return
        path.unlink()
    elif path.is_dir():
        for p in path.iterdir():                     # what the image carries (empty folders, a README)
            if not (target / p.name).exists():
                shutil.move(str(p), target / p.name)
        shutil.rmtree(path)
    elif path.exists():                              # a file written when the link had been removed (a revoked consent)
        shutil.move(str(path), target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target, target_is_directory=folder)


def data() -> None:
    for rel, name in DIRS.items():
        link(ROOT / rel, DATA / name, True)
    for rel, name in FILES.items():
        link(ROOT / rel, DATA / name, False)
    for path, name in ELSEWHERE.items():
        link(path, DATA / name, True)
    os.chmod(DATA / "keys", 0o755)                   # the key's folder: root's, written by root only (sys_ethics)
    os.chmod(DATA, 0o700)


# ---- 2. the settings ----------------------------------------------------------------------------------------------
def settings() -> None:
    env_file = Path(os.environ["AURORA_ENV_FILE"])
    first = not env_file.exists()
    schema = json.loads((ROOT / "sys/core/config/settings_schema.json").read_text(encoding="utf-8"))["settings"]
    keys = {s["key"]: s for s in schema}
    args: list[str] = []
    if first:
        say("first start: settings from docker/.env")
        prof = json.loads(run(PY, str(SCRIPT / "sys_profile.py"), "--json", "--cloud").stdout)["env"]
        # no local voice or painting in the image: off at first, a cloud provider in the Models page switches them on
        values = {**prof, "AURORA_TTS": "0", "AURORA_IMAGE_ENABLED": "0", **FIXED}
        for k, v in os.environ.items():
            if k in keys and k not in FIXED and v != "":
                if keys[k].get("secret"):
                    args += ["--set-env", k]         # by the environment, never on a command line
                else:
                    values[k] = v
        provider = values.get("AURORA_CLOUD_PROVIDER", "anthropic")
        if provider == "claude_code":
            say("Claude Code is not in this image: choose an API provider in docker/.env")
            sys.exit(1)
        key = {"custom": "AURORA_CUSTOM_API_KEY"}.get(provider, f"AURORA_{provider.upper()}_API_KEY")
        trial = {**os.environ, "AURORA_INSTALL_CLOUD_KEY": os.environ.get(key, ""),
                 "AURORA_INSTALL_CLOUD_URL": values.get("AURORA_CUSTOM_BASE_URL", "")}
        if not values.get("AURORA_CLOUD_MODEL"):             # the provider's own list, as the installer does
            r = subprocess.run([PY, str(SCRIPT / "sys_cloud_setup.py"), "models", provider], cwd=ROOT, env=trial,
                               capture_output=True, text=True)
            if r.returncode != 0 or not r.stdout.strip():
                say(f"{provider} refuses the key or lists no model: {(r.stdout + r.stderr).strip()[-300:]}")
                sys.exit(1)
            values["AURORA_CLOUD_MODEL"] = r.stdout.split()[0]
        r = subprocess.run([PY, str(SCRIPT / "sys_cloud_setup.py"), "try", provider, values["AURORA_CLOUD_MODEL"]],
                           cwd=ROOT, env=trial, capture_output=True, text=True)
        if r.returncode != 0:
            say(f"{provider} {values['AURORA_CLOUD_MODEL']} does not answer: {(r.stdout + r.stderr).strip()[-300:]}")
            sys.exit(1)
        say(f"{provider} {values['AURORA_CLOUD_MODEL']} answers")
    else:
        values = {k: os.environ[k] for k in ALWAYS if os.environ.get(k, "") != ""}
        values.update(FIXED)
    for k, v in values.items():
        args += ["--set", f"{k}={v}"]
    run(PY, str(SCRIPT / "sys_env_sync.py"), *args)
    os.replace(env_file.with_name(env_file.name + ".proposed"), env_file)
    os.chmod(env_file, 0o600)
    run(PY, "-c", "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config; sys_config.get()")


# ---- 3. layout, models, key, Caddyfile ----------------------------------------------------------------------------
def prepare() -> None:
    status = Path(run(PY, "-c", "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config; "
                                "print(sys_config.get().path('AURORA_STATUS_DIR'))").stdout.strip())
    if not (status / "users_layout.json").exists():
        run(PY, str(SCRIPT / "sys_users_migrate.py"), "migrate", "--yes", "--fresh", check=False)
    # the command cards' commands: run on the host (an update is a new image, never applied from the WebUI)
    run(PY, str(SCRIPT / "sys_commands_write.py"), "--from", str(ROOT / "docker" / "commands.json"), check=False)
    chosen = status / "domains_set"
    if not chosen.exists():                          # the areas (docker/.env AURORA_DOMAINS), at the first start only
        areas = os.environ.get("AURORA_DOMAINS", "all").strip() or "all"
        out = run(PY, str(SCRIPT / "sys_domains.py"), "--set", areas, check=False)
        if out.returncode != 0:
            say(f"AURORA_DOMAINS={areas}: {(out.stdout + out.stderr).strip()[-200:]} (numbers 1-8 or all)")
            sys.exit(1)
        chosen.write_text(areas + "\n", encoding="utf-8")
        say(f"areas {areas}: {out.stdout.strip()}")
    say("models: encoder and re-ranker (3.3 GB the first time)")
    extra = os.environ.get("AURORA_DOCKER_MODELS", "").strip()
    run(PY, str(SCRIPT / "sys_models_fetch.py"), "--models", "embedder,reranker" + (f",{extra}" if extra else ""), "--yes")
    tuned = DATA / "status" / "calibrated"
    if not tuned.exists():                           # the machine's audit: search and harvest fit this CPU (C229)
        say("machine audit: measuring the encoder and the re-ranker")
        out = run(PY, str(SCRIPT / "sys_calibrate.py"), "--write", "--say", "en", check=False)
        if out.returncode == 0:
            tuned.write_text(out.stdout, encoding="utf-8")
            say(out.stdout.strip())
    build = (ROOT / "docker" / "BUILD").read_text(encoding="utf-8").strip() if (ROOT / "docker" / "BUILD").exists() else "?"
    signed = DATA / "ethics" / "build"
    if not (DATA / "keys" / "owner_ed25519").exists() or not signed.exists() or signed.read_text().strip() != build:
        say(f"code of conduct: this installation's key and signature (image {build})")
        run(PY, str(SCRIPT / "sys_ethics_sign.py"), "setup", "--exempt")
        signed.write_text(build + "\n", encoding="utf-8")
    run(PY, str(SCRIPT / "sys_ethics_sign.py"), "check")
    run(PY, "-c", "import sys; sys.path.insert(0, 'sys/core'); from aurora import net_https, sys_config; "
                  "print(net_https.write(sys_config.get()))")


# ---- 4. the services ----------------------------------------------------------------------------------------------
class Supervisor:
    def __init__(self):
        self.procs: dict[str, subprocess.Popen] = {}
        self.wanted = dict.fromkeys(UNITS, True)
        self.restarts = dict.fromkeys(UNITS, 0)
        self.started: dict[str, float] = {}
        self.down_since: dict[str, float] = {}
        self.stopping = False
        (RUN / "cmd").mkdir(parents=True, exist_ok=True)

    def start(self, unit: str) -> None:
        cmd, nice = UNITS[unit]
        if unit in self.procs and self.procs[unit].poll() is None:
            return
        self.procs[unit] = subprocess.Popen(cmd, cwd=ROOT, preexec_fn=(lambda: os.nice(nice)) if nice else None)
        self.started[unit] = time.time()
        self.down_since.pop(unit, None)

    def stop(self, unit: str, wait: float = 20) -> None:
        p = self.procs.get(unit)
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(wait)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()

    def state(self) -> dict:
        out = {}
        for u in UNITS:
            p = self.procs.get(u)
            alive = bool(p and p.poll() is None)
            out[u] = {"active": "active" if alive else ("activating" if self.wanted[u] else "inactive"),
                      "pid": p.pid if alive else 0, "restarts": self.restarts[u], "command": " ".join(UNITS[u][0]),
                      "status": (p.returncode if p and not alive else 0) or 0}
        return out

    def command(self, f: Path) -> None:
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        f.unlink(missing_ok=True)
        verb, units, code, msg = c.get("verb"), [u for u in c.get("units", []) if u in UNITS], 0, ""
        for u in units:
            if verb == "stop":
                self.wanted[u] = False
                self.stop(u)
            elif verb == "start":
                self.wanted[u] = True
                self.start(u)
            elif verb == "restart":
                self.wanted[u] = True
                self.stop(u)
                self.start(u)
            elif verb == "reload" and u == "aurora-https":
                r = subprocess.run(["/usr/bin/caddy", "reload", "--config", str(ROOT / "sys/https/Caddyfile"),
                                    "--adapter", "caddyfile", "--force"], capture_output=True, text=True)
                code, msg = r.returncode, (r.stderr or r.stdout)[-500:]
            elif verb == "reload":
                self.stop(u)
                self.start(u)
        if c.get("reply", True):                     # --no-block: nobody waits for it
            (RUN / "cmd" / f"{c.get('id', 'x')}.result").write_text(json.dumps({"code": code, "message": msg}),
                                                                     encoding="utf-8")

    def loop(self) -> None:
        for u in UNITS:
            self.start(u)
            if u == "aurora-models":
                time.sleep(3)                        # the API asks the models at its first question, not at start
        say("services started")
        while not self.stopping:
            for u, p in list(self.procs.items()):
                if self.wanted[u] and p.poll() is not None:
                    since = self.down_since.setdefault(u, time.time())
                    if time.time() - since >= 5:     # systemd's RestartSec=5
                        self.restarts[u] += 1
                        say(f"{u} ended ({p.returncode}): started again")
                        self.start(u)
            for f in sorted((RUN / "cmd").glob("*.json")):
                self.command(f)
            tmp = RUN / "state.tmp"
            tmp.write_text(json.dumps(self.state()), encoding="utf-8")
            os.replace(tmp, RUN / "state.json")
            time.sleep(1)

    def shutdown(self, *_) -> None:
        self.stopping = True
        say("stopping")
        for u in reversed(list(UNITS)):
            self.stop(u, 15)
        sys.exit(0)


def main() -> int:
    os.chdir(ROOT)
    RUN.mkdir(parents=True, exist_ok=True)
    data()
    settings()
    prepare()
    sup = Supervisor()
    signal.signal(signal.SIGTERM, sup.shutdown)
    signal.signal(signal.SIGINT, sup.shutdown)
    port = run(PY, "-c", "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config; "
                         "print(sys_config.get()['AURORA_API_PORT'])").stdout.strip()

    def ready() -> None:                             # the address and the key, once the API answers
        for _ in range(150):
            if subprocess.run(["curl", "-fs", "-o", "/dev/null", f"http://127.0.0.1:{port}/health"]).returncode == 0:
                break
            time.sleep(2)
        subprocess.run([PY, str(SCRIPT / "sys_ready.py")], cwd=ROOT)
    import threading
    threading.Thread(target=ready, daemon=True).start()
    sup.loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

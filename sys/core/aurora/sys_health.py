# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Is Aurora well? Every service, checked two ways, plus disk and GPU memory.

 service      systemd state (is-active) and a real check: its HTTP health, or for the daemons
              without a port a recent line in their own log
 disk         free space where the installation lives
 gpu          memory used on each GPU
Levels: ok (green), warn (yellow: degraded, keeps working), down (red: something does not work).
The overall level is the worst one; each problem has a sentence that says what is wrong.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime

import httpx

from . import sys_config, sys_metrics
from .sys_lang import say as _t   # a check is told by its name; its words follow the reader (C526)

LEVEL = {"ok": 0, "warn": 1, "down": 2}


def _unit(name: str) -> str:
    try:
        return subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _http(url: str) -> tuple[bool, str]:
    try:
        r = httpx.get(url, timeout=4)
        return r.status_code < 500, f"HTTP {r.status_code}"
    except httpx.HTTPError as e:
        return False, type(e).__name__


def _https(domain: str, port: int) -> tuple[bool, str]:
    """A real HTTPS request to the public name, answered by this machine (SNI and certificate checked)."""
    try:
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5",
                            "--resolve", f"{domain}:{port}:127.0.0.1", f"https://{domain}:{port}/health"],
                           capture_output=True, text=True, timeout=10)
        out = r.stdout.strip()
        if r.returncode in (60, 35, 77):              # the certificate, not the service (the colleague's «HTTP 000», 9 Oct)
            return False, _t("certificato non riconosciuto da questo computer: sudo caddy trust", "certificate not recognised by this computer: sudo caddy trust")
        if r.returncode == 7:
            return False, _t(f"nessuno ascolta sulla porta {port}", f"nobody listens on port {port}")
        return out.isdigit() and 0 < int(out) < 500, f"HTTP {out or '-'}"
    except (OSError, subprocess.SubprocessError) as e:
        return False, type(e).__name__


SYSLOG_SILENT_MIN = 30


def syslog_silence(cfg, now: float | None = None) -> tuple[str, str] | None:
    """The sentinel alive but nothing from the firewall for SYSLOG_SILENT_MIN: Aurora is blind and must say so (the
    owner, 10 Oct: a rule removed from this machine's firewall, no line for 8 hours, and not a word). Only where the
    firewall has spoken before (its log exists)."""
    import time
    f = cfg.path("AURORA_LOG_DIR") / "firewall" / "firewall.log"
    if not f.exists() or not cfg["AURORA_SENTINEL_ALLOW"]:
        return None
    age = ((now or time.time()) - f.stat().st_mtime) / 60
    if age < SYSLOG_SILENT_MIN:
        return None
    port = str(cfg["AURORA_SENTINEL_BIND"]).rsplit(":", 1)[-1]
    who = ", ".join(cfg["AURORA_SENTINEL_ALLOW"])
    return _t((f"nessuna riga dal firewall da {age:.0f} min: Aurora non vede la rete",
            f"controlla il firewall di questa macchina (ufw: sudo ufw allow from {who} to any port {port} proto udp) "
            f"e il server syslog sul firewall"), (f"no line from the firewall for {age:.0f} min: Aurora does not see the network",
            f"check this machine's firewall (ufw: sudo ufw allow from {who} to any port {port} proto udp) "
            f"and the syslog server on the firewall"))


def heartbeat(cfg, name: str) -> None:
    """Daemons without a port say they are alive by touching this file (checked by check())."""
    f = cfg.path("AURORA_STATUS_DIR") / "heartbeat" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.touch()


def _beat_age_min(cfg, name: str) -> float | None:
    f = cfg.path("AURORA_STATUS_DIR") / "heartbeat" / name
    return (time.time() - f.stat().st_mtime) / 60 if f.exists() else None


def health_change(items: list[dict], before: set[str]) -> tuple[str, str] | None:
    """(event, text) when a check went down since `before` (the names down then), or all came back; else None."""
    down = {i["name"]: i for i in items if i["level"] == "down"}
    new = [down[n] for n in down if n not in before]
    if new:
        return "health.down", "; ".join(f"{i['name']}: {i['text']}" for i in new)[:300]
    if before and not down:
        return "health.up", ", ".join(sorted(before))
    return None


def gpu_job(cfg: sys_config.Config) -> str:
    """What holds the GPU lock now (mdl_image.gpu_lock: a painting, an edit, a video), "" when nobody does."""
    import fcntl
    f = cfg.path("AURORA_STATUS_DIR") / "gpu.lock"
    if not f.exists():
        return ""
    with open(f, encoding="utf-8") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
            return ""
        except BlockingIOError:
            return fh.read().strip() or "a GPU job"


def check(cfg: sys_config.Config | None = None) -> dict:
    cfg = cfg or sys_config.get()
    items = []

    def add(name, level, text, detail=""):
        items.append({"name": name, "level": level, "text": text, "detail": detail})

    web = [("aurora-api", f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}/health"),
           ("aurora-models", f"http://{cfg['AURORA_MODELS_HOST']}:{cfg['AURORA_MODELS_PORT']}/health"),
           ("aurora-llm", f"http://{cfg['AURORA_LLM_HOST']}:{cfg['AURORA_LLM_PORT']}/health")]
    if str(cfg["AURORA_LLM_BACKEND"]) == "cloud":      # no local reasoner: the cloud default, checked without a call
        from . import mdl_router
        web = web[:2]
        why = mdl_router.CloudBase(cfg).problem()
        add("cloud", "down" if why else "ok", why or _t("ragionatore cloud", "cloud reasoner") + f": {cfg['AURORA_CLOUD_PROVIDER']} "
            f"{cfg['AURORA_CLOUD_MODEL'] or ''}".strip(), "AURORA_LLM_BACKEND=cloud")
    for unit, url in web:
        state = _unit(unit)
        ok, how = _http(url)
        if state == "active" and ok:
            add(unit, "ok", _t("attivo e risponde", "active and answering"), how)
        elif ok:
            add(unit, "warn", _t(f"risponde ma systemd dice {state!r}", f"answers, but systemd says {state!r}"), how)
        elif unit == "aurora-llm" and (job := gpu_job(cfg)):
            # stopped on purpose for a GPU job (a dream, a song, a video), in every state of the swap: stopping, off,
            # starting again and loading — the job holds the lock until the reasoner answers again (C157, C409)
            add(unit, "ok", _t(f"in pausa per un lavoro sulla GPU: {job}", f"paused for a job on the GPU: {job}") + ("" if state == "inactive" else f" (systemd: {state})"),
                _t("si riaccende alla fine (C157)", "it starts again at the end (C157)"))
        else:
            add(unit, "down", _t(f"non risponde ({how}), systemd: {state}", f"does not answer ({how}), systemd: {state}"), url)

    state = _unit("aurora-https")
    ok, how = _https(cfg["AURORA_DOMAIN"], cfg["AURORA_HTTPS_PORT"])
    add("aurora-https", "ok" if state == "active" and ok else "down",
        _t("HTTPS attivo" if state == "active" and ok else f"HTTPS non risponde ({how}), systemd: {state}", "HTTPS active" if state == "active" and ok else f"HTTPS does not answer ({how}), systemd: {state}"), how)

    for unit, beat, limit_min in (("aurora-rem", "rem", 3 * cfg["AURORA_REM_TICK_S"] / 60 + 2), ("aurora-harvester", "harvester", 5),
                                  ("aurora-sentinel", "sentinel", 5)):
        state, age = _unit(unit), _beat_age_min(cfg, beat)
        if state != "active":
            add(unit, "down", _t(f"fermo (systemd: {state})", f"stopped (systemd: {state})"))
        elif age is None or age > limit_min:
            add(unit, "warn", _t(f"attivo ma senza battito da {age:.0f} min" if age is not None else "attivo, nessun battito", f"active but no heartbeat for {age:.0f} min" if age is not None else "active, no heartbeat"),
                _t(f"atteso ogni {limit_min:.0f} min", f"expected every {limit_min:.0f} min"))
        else:
            add(unit, "ok", "attivo", _t(f"battito {age * 60:.0f} s fa", f"heartbeat {age * 60:.0f} s ago"))
    silent = syslog_silence(cfg)
    if silent:
        add("syslog firewall", "down", silent[0], silent[1])          # blind: an alert, as a service down is

    du = shutil.disk_usage(cfg.root)
    free = du.free / du.total
    add("disco", "down" if free < 0.03 else "warn" if free < 0.10 else "ok",
        _t(f"{du.free / 2**30:.0f} GB liberi ({free:.0%})", f"{du.free / 2**30:.0f} GB free ({free:.0%})"))
    for g in sys_metrics.sample()["gpus"]:
        used = g["used_mib"] / g["total_mib"]
        add(f"GPU{g['index']}", "warn" if used > 0.97 else "ok",
            f"VRAM {g['used_mib'] / 1024:.1f}/{g['total_mib'] / 1024:.1f} GB · {_t('carico', 'load')} {g['util_pct']}% · {g['temp_c']} °C")

    from . import sys_features                           # what this installation can do, and what contradicts itself
    feats = sys_features.report(cfg)
    for name, f in feats.items():
        if f["required"] and not f["ok"]:
            add(name, "down", _t(f"manca {', '.join(f['missing'])}", f"missing: {', '.join(f['missing'])}"), " / ".join(f["fix"]))
    off = [f["label"][_t("it", "en")] for f in feats.values() if not f["required"] and not f["ok"]]
    add("funzioni", "ok", f"{sum(f['ok'] for f in feats.values())}/{len(feats)} " + _t("disponibili", "available")
        + (_t("; non installate: ", "; not installed: ") + ", ".join(off) if off else ""))
    for p in sys_features.config_problems(cfg):
        add("configurazione", "warn", p)

    from . import mdl_budget                             # a cloud provider stopped by today's ceiling
    for prov in mdl_budget.today(cfg).get("stopped", []):
        add("cloud", "warn", _t(f"{prov}: tetto giornaliero di token raggiunto, passaggi in locale fino a domani", f"{prov}: the daily ceiling of tokens is reached, steps run locally until tomorrow"),
            "AURORA_CLOUD_DAILY_TOKENS")

    from . import sys_backup                             # the owner's data: copied, and recently
    b = sys_backup.status(cfg)
    last = b.get("last") or {}
    age_h = (time.time() - last["at"]) / 3600 if last.get("at") else None
    if not b["configured"] and age_h is not None and age_h <= 30:      # the NAS asleep now, the last copy recent
        add("backup", "warn", _t(f"ultimo {age_h:.0f} h fa; ora il NAS non risponde", f"the last {age_h:.0f} h ago; the NAS does not answer now"), b["problem"])
    elif not b["configured"]:
        add("backup", "warn", _t(f"nessun backup: {b['problem']}", f"no backup: {b['problem']}"), "AURORA_BACKUP_DIR + svc_backup.py init")
    elif age_h is None or age_h > 30:
        add("backup", "warn", _t("nessun backup riuscito" + (f" da {age_h:.0f} ore" if age_h else " ancora"), "no backup succeeded" + (f" for {age_h:.0f} hours" if age_h else " yet")), b.get("dest", ""))
    elif (why := sys_backup.unit_failure(after=last.get("at"))):
        add("backup", "warn", _t(f"ultimo tentativo fallito: {why}", f"the last attempt failed: {why}"), b.get("dest", ""))
    else:
        add("backup", "ok", _t(f"ultimo {age_h:.0f} h fa: {last.get('files')} file, {last.get('bytes', 0) / 1e9:.1f} GB, "
            f"{len(b['snapshots'])} copie", f"the last {age_h:.0f} h ago: {last.get('files')} files, {last.get('bytes', 0) / 1e9:.1f} GB, "
            f"{len(b['snapshots'])} copies"), b.get("dest", ""))

    try:                                                 # this installation's own lines (aurora/local), if any
        from . import local
        for line in getattr(local, "health", lambda c: [])(cfg):
            add(*line)
    except ImportError:
        pass

    from . import sys_ethics                             # the code as the owner signed it (second tier)
    drift = sys_ethics.drift_summary(sys_ethics.code_drift(cfg.root))
    add("firma del codice", "warn" if drift else "ok", drift or _t("ogni file come firmato dal proprietario", "every file as the owner signed it"))

    worst = max((LEVEL[i["level"]] for i in items), default=0)
    return {"level": [k for k, v in LEVEL.items() if v == worst][0], "items": items,
            "problems": [f"{i['name']}: {i['text']}" for i in items if i["level"] != "ok"],
            "checked": datetime.now().astimezone().isoformat(timespec="seconds")}

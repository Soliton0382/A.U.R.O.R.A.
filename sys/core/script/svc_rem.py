# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-rem: Aurora's autonomic cycle. Decides *when*; the work runs in aurora-api.

Every AURORA_REM_TICK_S it reads GET /v1/aurora/rem/state and starts at most one task:
 consolidate  closed sessions exist and the owner has been silent AURORA_REM_IDLE_MIN
 dream        inside AURORA_REM_DREAM_HOURS (local), once per night, owner silent
 introspect   once a day, owner silent: a self-review from the logs (problems, causes, proposals)
 repair       after a self-review with problems (AURORA_SELF_REPAIR): an agent investigates, fixes in
              the sandbox, proposes the change (the owner approves, AURORA_FORGE_MODE=ask)
 routines     every tick, also with REM off: the owner's periodic checks that are due (sys_routines)
 review       inside AURORA_REVIEW_HOURS, owner silent: past answers answered again; a better one is told
              in the chat (kno_review)
 reflect      boredom: silent for AURORA_REM_BORED_MIN (halved when it rains or the sky is
              overcast with low pressure: the previous installation's "melancholy"), and no
              thought in the last AURORA_REM_REFLECTION_GAP_MIN
Housekeeping, once a day: log files older than AURORA_LOG_RETENTION_DAYS are deleted.
One autonomic task at a time; the owner's silence (AURORA_REM_IDLE_MIN) keeps them away from
conversations, and a task queued behind other work (a migration batch) simply waits its turn.
"""
from __future__ import annotations

import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sns_clock, sys_config, sys_health, sys_log  # noqa: E402

cfg = sys_config.get()
log = sys_log.get_logger("rem")
BASE = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
HEADERS = {"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}
_stop = False


def _minutes_since(iso: str | None) -> float:
    if not iso:
        return float("inf")
    return (sns_clock.now(cfg) - datetime.fromisoformat(iso)).total_seconds() / 60


def in_dream_window(now: datetime) -> bool:
    start, end = (int(x) for x in str(cfg["AURORA_REM_DREAM_HOURS"]).split("-"))
    return start <= now.hour < end if start <= end else (now.hour >= start or now.hour < end)


def dreamt_tonight(last_dream: str | None, now: datetime) -> bool:
    """A dream already exists since the start of tonight's window."""
    if not last_dream:
        return False
    start = int(str(cfg["AURORA_REM_DREAM_HOURS"]).split("-")[0])
    night = now.replace(hour=start, minute=0, second=0, microsecond=0)
    if now < night:
        night -= timedelta(days=1)
    return datetime.fromisoformat(last_dream) >= night


def choose(st: dict, system: bool = True) -> tuple[str | None, str]:
    """The task to start now and why (or None and why not). `system`: the admin's turn, the only one with Aurora's
    own self-review and repairs; each user's social pages have their own report."""
    if st.get("rem_running"):
        return None, "an autonomic task is already running or queued"
    if st.get("morning_due"):                         # the good morning: a short count, no reasoning, owner or not
        return "morning", "the morning hour, no good morning yet today"
    idle = st["idle_min"] if st["idle_min"] is not None else float("inf")
    if idle < cfg["AURORA_REM_IDLE_MIN"]:
        return None, f"owner active {idle:.0f} min ago"
    stress = ((st.get("mood") or {}).get("emotions") or {}).get("stress") or {}
    if (stress.get("value") or 0) >= float(cfg["AURORA_MOOD_STRESS_PAUSE"]):     # 💗 kno_mood: the machine is busy
        return None, f"stressed ({stress['value']}: {', '.join(stress['causes'])}): waiting"
    now = sns_clock.now(cfg)
    if st["sessions_to_consolidate"]:
        return "consolidate", f"{st['sessions_to_consolidate']} closed sessions"
    if in_dream_window(now) and not dreamt_tonight(st["last"]["dream"], now):
        return "dream", "night window, no dream yet"
    if in_dream_window(now) and st.get("to_study") and not st.get("studied_tonight"):
        return "study", f"night window, {st['to_study']} questions declined and not studied yet"
    if in_dream_window(now) and st.get("train_due"):
        return "train", "night window, the shadow not trained tonight"
    if system and _minutes_since(st["last"].get("self_review")) >= 24 * 60:
        return "introspect", "no self-review in the last 24 hours"
    if st.get("social_platforms") and _minutes_since(st["last"].get("social_report")) >= 24 * 60:   # each user's pages
        return "social", f"{st['social_platforms']} social platforms connected, no report in the last 24 hours"
    review, repair = st["last"].get("self_review"), st["last"].get("repair")
    if system and cfg["AURORA_SELF_REPAIR"] and review and st.get("review_problems") and (not repair or repair < review):
        return "repair", f"the last self-review found problems in {st['review_problems']} components"
    if st.get("review_due"):
        return "review", f"{st['review_due']} past answers to think again about"
    w = st.get("weather") or {}
    bored_after = cfg["AURORA_REM_BORED_MIN"] * (0.5 if w.get("condition") in ("rain", "low_pressure_overcast") else 1)
    since_thought = _minutes_since(st["last"]["thought"])
    if idle >= bored_after and since_thought >= cfg["AURORA_REM_REFLECTION_GAP_MIN"]:
        return "reflect", f"bored: silent {idle:.0f} min (threshold {bored_after:.0f}, weather {w.get('condition', '-')})"
    return None, "nothing to do"


def wait_for_api(client: httpx.Client, limit_s: int = 300) -> None:
    """Units start together: give aurora-api time to come up before the first look."""
    end = time.time() + limit_s
    while not _stop and time.time() < end:
        try:
            if client.get(f"{BASE}/health", timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)


def main() -> int:
    def stop(*_):
        global _stop
        _stop = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    from aurora import sys_ethics
    sys_ethics.require_intact(log)
    log.info("aurora-rem started: tick %d s, enabled %s", cfg["AURORA_REM_TICK_S"], cfg["AURORA_REM_ENABLED"])
    client = httpx.Client(headers=HEADERS, timeout=30)
    wait_for_api(client)
    last_reason, last_purge, last_update = "", 0.0, 0.0
    while not _stop:
        if cfg["AURORA_UPDATE_MODE"] != "off" and time.time() - last_update > cfg["AURORA_UPDATE_INTERVAL_H"] * 3600:
            last_update = time.time()                 # updates: checked by the API, decided by the owner (or auto)
            try:
                u = client.post(f"{BASE}/v1/aurora/update/check", timeout=600).raise_for_status().json()
                log.info("update check: %s", u.get("error") or f"{u.get('behind', 0)} new commits")
            except (httpx.HTTPError, ValueError) as e:
                log.warning("update check failed: %s", e)
        sys_health.heartbeat(cfg, "rem")
        try:                                          # the owner's routines: not autonomic, so even with REM off
            t = client.post(f"{BASE}/v1/aurora/routines/tick").raise_for_status().json()
            if t["started"] or t["welcomed"]:
                log.info("routines started: %s; plugins welcomed: %s", t["started"], t["welcomed"])
            elif t.get("deferred"):
                log.info("routines wait: %s", t["deferred"])
            client.post(f"{BASE}/v1/aurora/synapses/level2", params={"if_due": "true"})   # synapses of synapses when due
            f = client.post(f"{BASE}/v1/aurora/forge/tick").raise_for_status().json()
            if f["started"]:
                log.info("forge: building a missing capability, run %s", f["started"])
        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.warning("routines tick failed: %s", e)
        if time.time() - last_purge > 86400:          # daily: retention of every component's logs
            removed = sys_log.purge_all(cfg)
            log.info("log retention: %d old files removed", len(removed))
            leaks = sys_log.scan_secrets(cfg)              # no key or token may ever sit in a log
            if leaks:
                log.warning("SECRETS IN LOGS: %s", ", ".join(f"{k} in {f}" for f, k in leaks[:10]))
                try:
                    client.post(f"{BASE}/v1/aurora/activity", json={"source": "rem", "event": "incident", "payload": {
                        "title": f"segreti nei log: {', '.join(sorted({k for _, k in leaks}))}"}})
                except httpx.HTTPError:
                    pass
            else:
                log.info("secret scan of the logs: clean")
            try:                                      # attached files follow their conversation turns
                client.post(f"{BASE}/v1/aurora/uploads/purge", timeout=300).raise_for_status()
            except httpx.HTTPError as e:
                log.warning("uploads purge failed: %s", e)
            try:                                      # synapses: new links between domains, then the fade
                client.post(f"{BASE}/v1/aurora/synapses/grow").raise_for_status()
            except httpx.HTTPError as e:
                log.warning("synapses round not started: %s", e)
            try:                                      # the public lists of attackers and the MAC makers (sec_intel)
                from aurora import sec_baseline, sec_intel
                if cfg["AURORA_INTEL_ENABLED"]:
                    log.info("threat lists: %s", sec_intel.refresh(cfg))
                    log.info("MAC makers: %d lines", sec_baseline.refresh_makers(cfg))
            except Exception as e:  # noqa: BLE001 — a list that cannot be read waits for tomorrow
                log.warning("threat lists not refreshed: %s", e)
            try:                                      # the soak, measured by itself: one snapshot a day
                from aurora import sys_soak
                sys_soak.record(cfg)
            except Exception as e:  # noqa: BLE001 — a measure never stops the cycle
                log.warning("soak snapshot failed: %s", e)
            last_purge = time.time()
        if cfg["AURORA_REM_ENABLED"]:
            try:                                      # every user's memory, one task at a time (one GPU)
                who = client.get(f"{BASE}/v1/aurora/rem/users").raise_for_status().json()
                reason = "nothing to do"
                for user in who["users"]:
                    q = {"user": user} if user else {}
                    st = client.get(f"{BASE}/v1/aurora/rem/state", params=q).raise_for_status().json()
                    task, reason = choose(st, system=user in (None, who["admin"]))
                    if task:
                        run = client.post(f"{BASE}/v1/aurora/rem/{task}", params=q).raise_for_status().json()
                        log.info("started %s for %s (%s): run %s", task, "the admin" if user == who["admin"] else
                                 "a user", reason, run["run_id"])
                        sys_log.trace("rem", "rem.task", {"task": task, "reason": reason, "run_id": run["run_id"]})
                        break
                else:
                    if reason != last_reason:
                        log.info("idle: %s", reason)
                last_reason = reason
            except (httpx.HTTPError, KeyError, ValueError) as e:
                log.warning("state or task failed: %s", e)
        for _ in range(cfg["AURORA_REM_TICK_S"]):
            if _stop:
                break
            time.sleep(1)
    log.info("aurora-rem stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())

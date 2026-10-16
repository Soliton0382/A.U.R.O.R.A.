# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The values advised (ROADMAP N28; owner, 16 Oct: «una tabella di valori consigliati da impostare in PHD etc, con
possibilità di modificarli… campionamento… se l'attrezzatura non è correttamente dimensionata… per gli astrofili»):
from anyone's equipment — the inventory of the telescope's PC (N.I.N.A.'s profile, PHD2's profile and its Guiding
Assistant runs), the guide logs, the darks' library — plus the few facts only the person knows (seeing, the mount's
capacity, the payload, the counterweight, the mount's meridian limit), each value the programs use: what is set now,
what Aurora advises and why (the formula and its numbers), the person's own choice when they want another one, and
whether the equipment is sized right (sampling, guide scope, payload, torque, counterweight).

Every number comes from a formula written here or from a measure (the Guiding Assistant's, the logs'); the rules of
thumb are said as such. Nothing is set on the telescope's PC: the person sets it, the table says where."""
from __future__ import annotations

import json
import math
import re
import statistics
import time

ARCSEC = 206.265
SIDEREAL = 15.041                        # ″/s at the celestial equator
# the facts only the person knows: key, unit, default (None: unknown until given), kind
FACTS = (("seeing_arcsec", "″", 3.0, "num"), ("mount_drive", "", None, ("strain_wave", "worm", "belt")),
         ("mount_capacity_kg", "kg", None, "num"), ("mount_capacity_cw_kg", "kg", None, "num"),
         ("mount_torque_nm", "N·m", None, "num"), ("saddle_to_ra_m", "m", None, "num"),
         ("payload_kg", "kg", None, "num"), ("com_from_saddle_m", "m", None, "num"),
         ("cw_kg", "kg", None, "num"), ("cw_arm_m", "m", None, "num"),
         ("cw_bar_kg", "kg", None, "num"), ("cw_bar_from_m", "m", None, "num"), ("cw_bar_len_m", "m", None, "num"),
         ("cw_stack_m", "m", None, "num"),
         ("mount_limit_min", "min", None, "num"), ("focuser_step_um", "µm", None, "num"),
         ("dither_img_px", "px", 10.0, "num"))


def _f(x):
    try:
        return float(str(x).strip().split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def facts_of(saved: dict | None) -> dict:
    """The person's facts with the defaults; a select keeps only its choices, a number only a number."""
    out = {}
    for k, _, default, kind in FACTS:
        v = (saved or {}).get(k)
        if isinstance(kind, tuple):
            out[k] = v if v in kind else default
        else:
            out[k] = _f(v) if _f(v) is not None else default
    return out


class Phd2:
    """PHD2's current profile as the inventory keeps it: its keys in order (the algorithms' blocks, each assistant run)."""

    def __init__(self, pairs: list):
        self.pairs = [(str(k), str(v)) for k, v in pairs or []]

    def last(self, key: str):
        return next((v for k, v in reversed(self.pairs) if k == key), None)

    def every(self, key: str) -> list:
        return [v for k, v in self.pairs if k == key]

    def before(self, marker: str, key: str):
        """The key's value in the block that ends with marker (Resist Switch's minMove sits before its fastSwitch)."""
        i = next((n for n, (k, _) in enumerate(self.pairs) if k == marker), None)
        if i is None:
            return None
        return next((v for k, v in reversed(self.pairs[:i]) if k == key), None)

    def assistant(self) -> list[dict]:
        """Each Guiding Assistant run: its advice and measures (the inventory keeps them in order)."""
        runs, cur = [], None
        for k, v in self.pairs:
            if k == "timestamp" and re.match(r"\d{4}-\d\d-\d\d", v):
                cur = {"when": v[:10]}
                runs.append(cur)
            elif cur is not None and k in ("rec_ra_minmove", "rec_dec_minmove", "pa_error", "backlash_info",
                                           "ra_drift_exposure", "total_hpf_rms", "recommendations"):
                cur.setdefault(k, v)
        return [r for r in runs if len(r) > 1]


def _row(key, group, where, current, advised, unit="", status="info", why="", **n) -> dict:
    return {"key": key, "group": group, "where": where, "current": current, "advised": advised, "unit": unit,
            "status": status, "why": why or key, "n": n}


def _range(cur, lo, hi, soft=0.0) -> str:
    if cur is None:
        return "unknown"
    if lo is not None and cur < lo * (1 - soft) or hi is not None and cur > hi * (1 + soft):
        return "warn"
    return "ok"


def _r(x, d=2):
    return round(x, d) if isinstance(x, (int, float)) else x


def advise(profile: dict | None, facts: dict, nights: list[dict] | None = None, darks: list[dict] | None = None,
           darks_temp: float | None = None, live: dict | None = None) -> list[dict]:
    """The rows of the table, grouped: sampling, guiding, dither and settle, meridian, mount, camera and focus. live: what
    PHD2 and N.I.N.A. have now (live_settings), over the inventory's snapshot; each row says where its value came from."""
    p = profile or {}
    rig = dict(p.get("rig") or {})
    n0 = dict((p.get("nina") or [{}])[0])
    lv = live or {}
    if lv.get("nina"):                                     # N.I.N.A.'s active profile now, over the inventory's
        n0.update({k: v for k, v in lv["nina"].items() if v})
        cam = lv["nina"].get("CameraSettings") or {}
        rig.update({k: v for k, v in (("gain", cam.get("Gain")), ("offset", cam.get("Offset")),
                                      ("cooling_c", _f(cam.get("Temperature")))) if v is not None})
    gs, flip, foc, cam = (n0.get("GuiderSettings", {}), n0.get("MeridianFlipSettings", {}), n0.get("FocuserSettings", {}),
                          n0.get("CameraSettings", {}))
    ph = Phd2((p.get("phd2") or {}).get("pairs") or [])
    ga = ph.assistant()
    rows: list[dict] = []
    img, focal, pixel = rig.get("scale_arcsec_px"), rig.get("focal_mm"), rig.get("pixel_um")
    ratio_f = rig.get("focal_ratio")
    g = rig.get("guiding") or {}
    gpx = _f(ph.last("pixelsize")) or g.get("pixel_um")
    gfocal = _f(ph.last("focal_length")) or _f(ph.last("focalLength")) or g.get("focal_mm")
    gscale = _f(ph.last("image_scale")) or (ARCSEC * gpx / gfocal if gpx and gfocal else None)
    seeing = facts["seeing_arcsec"]

    # ---- sampling ------------------------------------------------------------------------------------------------
    if img:
        lo, hi = seeing / 3.5, seeing / 2
        st = "ok" if lo <= img <= hi else ("bad" if img > seeing / 1.5 or img < seeing / 5 else "warn")
        why = "sampling_ok" if st == "ok" else ("sampling_under" if img > hi else "sampling_over")
        rows.append(_row("sampling", "sampling", "optics", _r(img), f"{lo:.2f}–{hi:.2f}", "″/px", st, why,
                         seeing=seeing, per_star=_r(seeing / img, 1), bin2=_r(img * 2)))
        aperture = focal / ratio_f if focal and ratio_f else None
        if aperture:
            rows.append(_row("resolution", "sampling", "optics", _r(116 / aperture, 2), None, "″", "info", "dawes",
                             d=_r(aperture, 0), seeing=seeing))
    # ---- the guide scope -------------------------------------------------------------------------------------------
    if img and gscale:
        ratio = gscale / img
        st = "ok" if ratio <= 5 else ("warn" if ratio <= 8 else "bad")
        rows.append(_row("guide_ratio", "guiding", "guide_optics", _r(ratio, 1), "≤ 5", "×", st, "guide_ratio",
                         guide=_r(gscale), img=_r(img), fmin=_r(focal * gpx / (pixel * 5), 0) if focal and gpx and pixel else None))
    last = next((n for n in nights or [] if n.get("sessions")), None)
    sess = [s for s in (last or {}).get("sessions", []) if not s.get("assistant")]
    long = [s for s in sess if s["minutes"] >= 10 and s["rms"]["total"] is not None]
    if img and long:
        rms = statistics.median(s["rms"]["total"] for s in long)
        st = "ok" if rms <= img else ("warn" if rms <= 1.5 * img else "bad")
        rows.append(_row("guide_rms", "guiding", "measured", _r(rms), f"≤ {img:.2f} (≤ {img / 2:.2f})", "″", st, "guide_rms",
                         night=last.get("night"), n=len(long)))
    # the exposure: PHD2's own assistant gives the range for this mount and sky
    exp_now = (lv.get("phd2") or {}).get("exposure_ms") or \
        next((s["settings"].get("exposure_ms") for s in reversed(sess) if s["settings"].get("exposure_ms")), None)
    rng = next((re.findall(r"([\d.]+)s", r.get("recommendations", "")) for r in reversed(ga) if "range" in r.get("recommendations", "")), [])
    lo_e, hi_e = (_f(rng[0]), _f(rng[1])) if len(rng) >= 2 else (2.0, 4.0)      # PHD2's own starting point otherwise
    drift = next((_f(r.get("ra_drift_exposure")) for r in reversed(ga) if r.get("ra_drift_exposure")), None)
    rows.append(_row("guide_exposure", "guiding", "phd2_main", _r(exp_now / 1000, 1) if exp_now else None, f"{lo_e:g}–{hi_e:g}", "s",
                     _range(exp_now / 1000 if exp_now else None, lo_e, hi_e), "guide_exposure" if rng else "guide_exposure_rule",
                     drift=drift, snr=(sess[-1]["snr"] if sess else None)))
    # minimum moves: the assistant's advice, the median of its runs (one run is noisy)
    xalgo = str(ph.last("XGuideAlgorithm") or "")
    ra_now = _f(ph.last("gp_min_move")) if xalgo == "5" else _f(ph.before("hysteresis", "minMove") or ph.last("minMove"))
    dec_now = _f(ph.before("fastSwitch", "minMove"))
    if lv.get("phd2"):                                     # PHD2 now
        ra_now, dec_now = lv["phd2"].get("ra_min_move", ra_now), lv["phd2"].get("dec_min_move", dec_now)
    for key, rec, now, axis in (("min_move_ra", "rec_ra_minmove", ra_now, "RA"), ("min_move_dec", "rec_dec_minmove", dec_now, "DEC")):
        vals = [_f(r.get(rec)) for r in ga if _f(r.get(rec)) is not None]
        if vals:
            adv = statistics.median(vals)
            rows.append(_row(key, "guiding", "phd2_algo", now, _r(adv), "px", _range(now, adv * 0.75, adv * 1.3), "min_move",
                             runs=len(vals), lo=_r(min(vals)), hi=_r(max(vals)), axis=axis))
        else:
            rows.append(_row(key, "guiding", "phd2_algo", now, "0.15–0.20", "px", _range(now, 0.15, 0.2, 0.1), "min_move_rule", axis=axis))
    # calibration step: PHD2's calculator — the distance in pixels covered in about 12 steps at the guide rate
    rate = _f(ph.last("ra_guide_rate"))
    rate_as = rate * 3600 if rate else None
    dist, step = _f(ph.last("CalibrationDistance")) or 25, _f(ph.last("CalibrationDuration"))
    if rate_as and gscale:
        adv = dist * gscale / (rate_as * 12) * 1000
        rows.append(_row("cal_step", "guiding", "phd2_cal", step, round(adv / 50) * 50, "ms", _range(step, adv * 0.8, adv * 1.2),
                         "cal_step", dist=dist, scale=_r(gscale), rate=_r(rate_as, 1), x=_r(rate_as / SIDEREAL, 2)))
    for key, k in (("max_ra", "MaxRaDuration"), ("max_dec", "MaxDecDuration")):
        now = _f(ph.last(k))
        if now is not None:
            hit = sum(1 for n in nights or [] for f in n.get("findings", []) if f["code"] in ("ra_at_limit",)) if key == "max_ra" else 0
            rows.append(_row(key, "guiding", "phd2_algo", now, "1000–2500", "ms", _range(now, 1000, 2500), "max_duration",
                             corr=_r((now / 1000) * rate_as, 1) if rate_as else None, hits=hit))
    snr_min = _f(ph.last("StarMinSNR")) or _f(ph.last("target_snr"))
    snr_seen = statistics.median(s["snr"] for s in sess if s.get("snr")) if any(s.get("snr") for s in sess) else None
    rows.append(_row("snr", "guiding", "phd2_star", _r(snr_seen, 0), "≥ 15", "", _range(snr_seen, 15, None), "snr", min=snr_min,
                     lost=sum(s["lost"] for s in sess)))
    # backlash: a strain-wave gear has next to none; the assistant's reads must agree before compensating
    bl = [_f(r.get("backlash_info")) for r in ga if _f(r.get("backlash_info")) is not None]
    on = ph.last("BacklashCompEnabled") == "1"
    if facts["mount_drive"] == "strain_wave":
        rows.append(_row("backlash", "guiding", "phd2_algo", "on" if on else "off", "off", "", "warn" if on else "ok",
                         "backlash_swg", reads=", ".join(f"{x:g}" for x in bl)))
    elif bl:
        med = statistics.median(bl)
        agree = len(bl) > 1 and (max(bl) - min(bl)) <= 0.5 * med
        rows.append(_row("backlash", "guiding", "phd2_algo", "on" if on else "off", f"on {med:g} ms" if agree and med > 100 else "—",
                         "", ("ok" if on else "warn") if agree and med > 100 else "info",
                         "backlash_agree" if agree else "backlash_scatter", reads=", ".join(f"{x:g}" for x in bl)))
    # polar alignment: the latest Guiding Assistant, from the inventory or a night's log; a portable mount is set up
    # again each night, so a measure older than POLAR_DAYS says nothing of tonight's
    pa = [(_f(r.get("pa_error")), r["when"]) for r in ga if _f(r.get("pa_error")) is not None]
    pa += [(n["advice"]["pa_arcmin"], n["night"]) for n in nights or [] if (n.get("advice") or {}).get("pa_arcmin") is not None]
    if pa:
        v, when = max(pa, key=lambda x: x[1])
        old = (time.time() - time.mktime(time.strptime(when, "%Y-%m-%d"))) / 86400 > POLAR_DAYS
        rows.append(_row("polar", "guiding", "measured", v, "≤ 5 (≤ 3)", "′", "unknown" if old else ("ok" if v <= 5 else "warn"),
                         "polar_old" if old else "polar", when=when, drift=_r(v * 60 * 2 * math.pi / 1436, 1)))
    # ---- dither and settle -----------------------------------------------------------------------------------------
    if img and gscale:
        want = facts["dither_img_px"] * img / gscale
        now = _f(gs.get("DitherPixels"))
        rows.append(_row("dither", "dither", "nina_guider", now, _r(want, 1), "px", _range(now, want * 0.7, want * 1.4), "dither",
                         img_px=facts["dither_img_px"], img=_r(img), guide=_r(gscale), arcsec=_r(now * gscale, 1) if now else None))
    seqs_every = [s.get("dither_every") for s in (p.get("_sequences") or []) if s.get("dither_every")]
    if seqs_every:
        rows.append(_row("dither_every", "dither", "nina_seq", seqs_every[0], "1–3", "", _range(seqs_every[0], 1, 3), "dither_every"))
    for key, k, lo, hi in (("settle_px", "SettlePixels", 0.5, 1.5), ("settle_time", "SettleTime", 5, 15),
                           ("settle_timeout", "SettleTimeout", 40, 120)):
        now = _f(gs.get(k))
        if now is not None:
            rows.append(_row(key, "dither", "nina_guider", now, f"{lo:g}–{hi:g}", "px" if key == "settle_px" else "s",
                             _range(now, lo, hi), key, arcsec=_r(now * gscale, 1) if key == "settle_px" and gscale else None))
    # ---- meridian ----------------------------------------------------------------------------------------------------
    after, mx = _f(flip.get("MinutesAfterMeridian")), _f(flip.get("MaxMinutesAfterMeridian"))
    stopped = [f for n in nights or [] for f in n.get("findings", []) if f["code"] == "runaway_meridian"]
    if after is not None:
        rows.append(_row("flip_after", "meridian", "nina_flip", after, "≥ 1", "min", _range(after, 1, None), "flip_after", max=mx))
    lim = facts["mount_limit_min"]
    if mx is not None:
        need = mx + 3
        st = "unknown" if lim is None else ("ok" if lim >= need else "bad")
        if stopped and (lim is None or lim < need):
            st = "bad"
        rows.append(_row("mount_limit", "meridian", "mount_app", lim, f"≥ {need:g}", "min", st,
                         "mount_limit_stopped" if stopped else "mount_limit", max=mx, at=stopped[0].get("min") if stopped else None,
                         night=next((n["night"] for n in nights or [] if any(f["code"] == "runaway_meridian" for f in n["findings"])), None)))
    # ---- mount and payload -------------------------------------------------------------------------------------------
    pay, cap, capcw = facts["payload_kg"], facts["mount_capacity_kg"], facts["mount_capacity_cw_kg"]
    cw, arm, com, s2ra, tq = facts["cw_kg"], facts["cw_arm_m"], facts["com_from_saddle_m"], facts["saddle_to_ra_m"], facts["mount_torque_nm"]
    if pay is not None:
        limit = capcw if cw and capcw else cap
        if limit:
            share = pay / limit
            rows.append(_row("payload", "mount", "mount", _r(pay, 2), f"≤ {0.7 * limit:.1f}", "kg",
                             "ok" if share <= 0.7 else ("warn" if share <= 1 else "bad"), "payload", limit=limit, pct=round(share * 100),
                             cw=bool(cw)))
        if com is not None and s2ra is not None:
            moment = pay * 9.8 * (s2ra + com)
            if tq:
                rows.append(_row("torque", "mount", "mount", _r(moment, 1), f"< {tq:g}", "N·m", "ok" if moment < tq * 0.85 else
                                 ("warn" if moment < tq else "bad"), "torque", com_max=_r(tq / (pay * 9.8) - s2ra, 2), pct=round(moment / tq * 100)))
            if cw:
                # the bar's own weight acts at its middle (from where it leaves the mount to its end), when it is given
                bar, root, blen = facts["cw_bar_kg"], facts["cw_bar_from_m"], facts["cw_bar_len_m"]
                bar_m = bar * (root + blen / 2) if None not in (bar, root, blen) else 0.0
                balance = (pay * (s2ra + com) - bar_m) / cw
                # the farthest the weights' centre can go: the bar's end (its usable length, the cap left out) less half
                # the weights' thickness, when given
                reach = root + blen - (facts["cw_stack_m"] or 0) / 2 if None not in (root, blen) else None
                st = "info" if arm is None else ("ok" if abs(arm - balance) <= 0.02 else "warn")
                why = ("cw_short" if reach is not None and balance > reach else
                       "cw_ok" if arm is not None and abs(arm - balance) <= 0.02 else     # a tape's reading: balanced
                       "cw_arm" if arm is None or arm <= balance else "cw_heavy")
                share = (cw * reach + bar_m) / (pay * (s2ra + com)) if reach is not None else None   # the weights at the end
                if why == "cw_short" and facts["mount_drive"] == "strain_wave" and share >= 0.85:
                    why, st = "cw_end_ok", "ok"    # a strain-wave gear likes the tube side a little heavier: one side of the teeth
                rows.append(_row("cw_arm", "mount", "mount", arm, _r(balance, 3), "m", "warn" if why == "cw_short" else st, why,
                                 cw=cw, diff_cm=_r((arm - balance) * 100, 1) if arm is not None else None,
                                 bar=bool(bar_m), reach=_r(reach, 3), pct=round(share * 100) if share is not None else None))
    # ---- camera, darks, focus ------------------------------------------------------------------------------------------
    usable = [d for d in darks or [] if not d.get("old")]
    gain, off = _f(rig.get("gain")), _f(rig.get("offset"))
    if usable:
        ok = any(_f(d.get("gain")) == gain and _f(d.get("offset")) == off for d in usable)
        rows.append(_row("gain_offset", "camera", "nina_camera", f"{gain:g} / {off:g}" if gain is not None and off is not None else None,
                         " · ".join(sorted({f"{_f(d.get('gain')):g} / {_f(d.get('offset')):g}" for d in usable if d.get('gain') is not None
                                            and d.get('offset') is not None})), "", "ok" if ok else "bad", "gain_offset",
                         exposures=", ".join(f"{d['exposure_s']:g}" for d in usable if d.get("exposure_s") and _f(d.get("gain")) == gain
                                             and _f(d.get("offset")) == off)))
    cool = rig.get("cooling_c")
    if cool is not None and darks_temp is not None:
        rows.append(_row("cooling", "camera", "nina_camera", cool, darks_temp, "°C", "ok" if cool == darks_temp else "bad", "cooling"))
    if ratio_f:
        cfz = 4.88 * 0.55 * ratio_f ** 2
        stepu = facts["focuser_step_um"]
        now = _f(foc.get("AutoFocusStepSize"))
        if stepu:
            s = cfz / stepu
            rows.append(_row("af_step", "camera", "nina_focus", now, f"{s:.0f}–{3 * s:.0f}", "", _range(now, s, 3 * s, 0.2), "af_step",
                             cfz=_r(cfz, 0), n=_r(ratio_f, 1), steps=_r(s, 1)))
        else:
            rows.append(_row("af_step", "camera", "nina_focus", now, None, "", "unknown", "af_step_need", cfz=_r(cfz, 0), n=_r(ratio_f, 1)))
    for r in rows:                                         # where each value came from
        src = LIVE_FROM.get(r["key"])
        r["src"] = "live" if src and lv.get(src) else ("measured" if r["where"] == "measured" else "inventory")
        if r["key"] in FACT_ROWS:                          # a value only the person knows: they set it, not choose it
            r["fact"], r["src"] = FACT_ROWS[r["key"]], "fact"
    return rows


POLAR_DAYS = 3                  # a Guiding Assistant's polar alignment older than this: tonight's is not known

# the rows whose current value is one of the person's facts: the table's box sets the fact itself
FACT_ROWS = {"mount_limit": "mount_limit_min"}

# the rows whose value is read live, and from which program
LIVE_FROM = {"guide_exposure": "phd2", "min_move_ra": "phd2", "min_move_dec": "phd2", "dither": "nina", "settle_px": "nina",
             "settle_time": "nina", "settle_timeout": "nina", "flip_after": "nina", "mount_limit": "nina", "gain_offset": "nina",
             "cooling": "nina", "af_step": "nina"}


def live_settings(host: str) -> dict:
    """What PHD2 (JSON-RPC, read only) and N.I.N.A. (its Advanced API, the active profile) have now; a part that does
    not answer is None. The site is never read."""
    from aurora import ast_autoguide, ast_nina
    out: dict = {"phd2": None, "nina": None, "at": time.time()}
    if not host:
        return out
    try:
        out["phd2"] = {k: v for k, v in ast_autoguide.Phd2Params(host, 4400, lambda h, p, m, a=None: ast_autoguide.rpc(h, p, m, a, 2.0)).get().items()}
    except (OSError, RuntimeError, ValueError, TypeError):
        pass
    out["nina"] = ast_nina.profile(host, timeout=2.0)
    return out


def summary(rows: list[dict]) -> dict:
    """How many rows are fine, to look at, wrong, unknown."""
    c = {"ok": 0, "warn": 0, "bad": 0, "unknown": 0, "info": 0}
    for r in rows:
        c[r["status"]] = c.get(r["status"], 0) + 1
    return c


def choose(rows: list[dict], choices: dict) -> list[dict]:
    """The person's own value for a row, kept beside the advised one: the row is judged against the choice."""
    for r in rows:
        v = (choices or {}).get(r["key"])
        if v in (None, "") or r.get("fact"):
            continue
        r["choice"] = v
        cur, ch = _f(r["current"]), _f(v)
        if cur is not None and ch is not None:
            r["status"] = "ok" if abs(cur - ch) <= max(abs(ch) * 0.05, 1e-9) else "warn"
        elif r["current"] is not None:
            r["status"] = "ok" if str(r["current"]).strip().lower() == str(v).strip().lower() else "warn"
    return rows


SETUP = "astro_setup.json"               # in the person's astro folder: their facts and own choices


def setup(folder) -> dict:
    try:
        x = json.loads((folder / SETUP).read_text(encoding="utf-8"))
        return x if isinstance(x, dict) else {}
    except (OSError, ValueError):
        return {}


def save_part(folder, part: str, value) -> None:
    """One part of the setup replaced (the guiding tuner's mode and limits)."""
    saved = setup(folder)
    saved[part] = value
    (folder / SETUP).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")


def save(cfg, body: dict) -> list[str]:
    """Merges the person's facts and choices into the setup (an empty value forgets it); returns the keys changed.
    An unknown fact or a strange key: ValueError."""
    from aurora import ast_inventory as A
    d = A.folder(cfg)
    saved = setup(d)
    known = {k for k, *_ in FACTS}
    changed = []
    for part, ok in (("facts", lambda k: k in known), ("choices", lambda k: re.fullmatch(r"[a-z_]{2,30}", k))):
        cur = dict(saved.get(part) or {})
        for k, v in dict(body.get(part) or {}).items():
            if not ok(str(k)):
                raise ValueError(f"unknown {part[:-1]}: {k}")
            if v in (None, ""):
                cur.pop(k, None)
            else:
                cur[k] = str(v)[:40]
            changed.append(str(k))
        saved[part] = cur
    (d / SETUP).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    return sorted(set(changed))


def report(cfg, with_live: bool = True) -> dict:
    """Everything the 🎛️ tab and the chat need: the rows with the person's choices, the facts and their spec, the
    sequences of the astro folder (and its «sequences» subfolder) checked against the darks; the values PHD2 and
    N.I.N.A. have now when the telescope's PC answers (with_live), else the inventory's."""
    from aurora import ast_guidelog as G, ast_inventory as A, ast_sequence as S
    d = A.folder(cfg)
    p = A.profile(cfg) or {}
    rig = p.get("rig") or {}
    saved = setup(d)
    facts = facts_of(saved.get("facts"))
    nights = G.nights(d, rig.get("scale_arcsec_px"), rig.get("meridian_flip"))
    lib = A.darks_library(cfg)
    seqs = S.sequences(d) + S.sequences(d / "sequences")
    temp = _f(cfg["AURORA_ASTRO_DARKS_TEMP"])
    live = live_settings(telescope_host(cfg, p)[0]) if with_live else {}
    rows = choose(advise({**p, "_sequences": seqs}, facts, nights, lib["darks"], temp, live), saved.get("choices") or {})
    cam = (live.get("nina") or {}).get("CameraSettings") or {}
    rig_now = {**rig, **{k: v for k, v in (("gain", cam.get("Gain")), ("offset", cam.get("Offset")),
                                           ("cooling_c", _f(cam.get("Temperature")))) if v is not None}}
    for q in seqs:
        q["findings"] = S.check(q, rig_now, lib["darks"]) if "error" not in q else []
    return {"rows": rows, "summary": summary(rows), "facts": facts, "choices": saved.get("choices") or {},
            "facts_spec": [{"key": k, "unit": u, "default": dv, "choices": list(kind) if isinstance(kind, tuple) else None}
                           for k, u, dv, kind in FACTS],
            "sequences": seqs[:60], "inventory": bool(rig), "written": p.get("written", ""),
            "live": {"phd2": bool(live.get("phd2")), "nina": bool(live.get("nina")), "at": live.get("at")}}


def telescope_host(cfg, profile: dict | None = None) -> tuple[str, int]:
    """The telescope's PC: AURORA_ASTRO_PC (host[:PHD2 port]), else the address the PC gave in its inventory."""
    from aurora import ast_inventory as A, ast_phd2
    host = str(cfg["AURORA_ASTRO_PC"] or "").strip()
    if not host:
        p = profile if profile is not None else A.profile(cfg)
        host = next((a.split("/")[0] for a in ((p or {}).get("links") or {}).get("addresses", [])), "")
    name, _, port = host.partition(":")
    return name, int(port) if port.isdigit() else ast_phd2.PORT

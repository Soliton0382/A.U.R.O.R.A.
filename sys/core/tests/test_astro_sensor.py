# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The camera and the sky measured from frames (ROADMAP N28): synthetic frames of a known camera — 0.5 e-/ADU, 2 e-
of read noise, a bias at 1000 ADU, a sky of 0.25 e-/s — written as XISF and FITS; the photon transfer must find the
camera, the lights the sky, and the plan the exposure the formula gives, the best of the person's darks, the HDR set."""
import json
from pathlib import Path

import numpy as np

from aurora import ast_frames as F
from aurora import ast_sensor as S

G, RN, BIAS, SKY = 0.5, 2.0, 1000.0, 0.25
rng = np.random.default_rng(7)


def frame(electrons: float, size: int = 256) -> np.ndarray:
    e = rng.poisson(electrons, (size, size)) if electrons else np.zeros((size, size))
    return np.clip(np.round(BIAS + e / G + rng.normal(0, RN / G, (size, size))), 0, 65535).astype("<u2")


def xisf(path: Path, data: np.ndarray, kind: str, exp: float, filt: str = "") -> None:
    kw = {"IMAGETYP": kind, "EXPTIME": exp, "GAIN": 100, "OFFSET": 30, "FILTER": filt, "BAYERPAT": "RGGB",
          "DATE-OBS": "2026-01-05T21:00:00"}
    keys = "".join(f'<FITSKeyword name="{k}" value="{v}" comment=""/>' for k, v in kw.items())
    h, w = data.shape
    fmt = "Float32" if data.dtype.kind == "f" else "UInt16"
    xml = (f'<xisf version="1.0"><Image geometry="{w}:{h}:1" sampleFormat="{fmt}" imageType="{kind}" '
           f'location="attachment:4096:{data.nbytes}">{keys}</Image></xisf>').encode()
    head = b"XISF0100" + len(xml).to_bytes(4, "little") + b"\0" * 4 + xml
    path.write_bytes(head.ljust(4096, b"\0") + data.tobytes())


def fits(path: Path, data: np.ndarray, kind: str, exp: float, filt: str) -> None:
    cards = [("SIMPLE", "T"), ("BITPIX", "16"), ("NAXIS", "2"), ("NAXIS1", str(data.shape[1])), ("NAXIS2", str(data.shape[0])),
             ("BZERO", "32768"), ("IMAGETYP", f"'{kind}'"), ("EXPTIME", str(exp)), ("GAIN", "100"), ("OFFSET", "30"),
             ("FILTER", f"'{filt}'"), ("BAYERPAT", "'RGGB'"), ("DATE-OBS", "'2026-01-06T21:00:00'")]
    head = "".join(f"{k:<8}= {v:>20}".ljust(80) for k, v in cards) + "END".ljust(80)
    head = head.ljust(-(-len(head) // 2880) * 2880)
    body = (data.astype(np.int32) - 32768).astype(">i2").tobytes()
    path.write_bytes(head.encode() + body.ljust(-(-len(body) // 2880) * 2880, b"\0"))


def night(tmp: Path) -> Path:
    d = tmp / "frames"
    (d / "cal").mkdir(parents=True)
    for i in range(2):
        xisf(d / "cal" / f"flat_{i}.xisf", frame(10000), "Flat", 2.0, "L-eXtreme")
        xisf(d / "cal" / f"darkflat_{i}.xisf", frame(0), "Dark", 2.0, "L-eXtreme")
    for i in range(3):
        xisf(d / f"light_{i}.xisf", frame(SKY * 100), "Light", 100.0, "Optolong L-eXtreme")
    fits(d / "light_bb.fits", frame(4.0 * 60), "Light Frame", 60.0, "IDAS LPS D2")
    xisf(d / "integrated_dark.xisf", frame(0).astype("<f4") / 65535, "Dark", 100.0)   # floating point: an integration
    return d


def test_the_photon_transfer_finds_the_camera(tmp_path):
    frames = F.scan(night(tmp_path))
    assert {h["kind"] for h in frames} == {"flat", "dark", "light"} and len(frames) == 8
    s = S.transfer(*S._pairs(frames)[(100.0, 30.0)])
    assert abs(s["gain_e_adu"] - G) / G < 0.05 and abs(s["read_noise_e"] - RN) / RN < 0.1
    assert abs(s["bias_adu"] - BIAS) < 2 and s["full_well_e"] == round((65535 - s["bias_adu"]) * s["gain_e_adu"]) and s["zero_share"] == 0


def test_the_sky_and_the_plan(tmp_path):
    frames = F.scan(night(tmp_path))
    sensors = {(100.0, 30.0): S.transfer(*S._pairs(frames)[(100.0, 30.0)])}
    skies = {x["filter"]: x for x in S.sky(frames, sensors, [])}
    nb, bb = skies["Optolong L-eXtreme"], skies["IDAS LPS D2"]                        # the FITS light read too
    assert nb["narrow"] and not bb["narrow"] and abs(nb["rate"] - SKY) / SKY < 0.1 and abs(bb["rate"] - 4.0) / 4.0 < 0.1
    darks = [{"gain": 100.0, "offset": 30.0, "exposure_s": e, "old": False} for e in (60.0, 120.0, 180.0, 300.0)]
    measured = {"sensors": list(sensors.values()), "sky": list(skies.values())}
    p = S.plan(measured, darks, {"rig": {"gain": "100", "offset": "30"}, "nina": [{"GuiderSettings": {"SettleTime": "10"}}]}, 3,
               "M42 Orion Nebula")
    k = p["kinds"]["narrowband"]
    t_min = 10 * k["best"]["read_noise_e"] ** 2 / k["rate"]                            # ≈ 160 s
    assert k["best"]["exposure_s"] == S.nice(1.2 * t_min) and k["with_darks"]["exposure_s"] == 180.0
    assert p["kinds"]["broadband"]["best"]["exposure_s"] == S.nice(p["floor_s"])       # a bright sky: the overhead decides
    assert p["overhead_s"] == 7.0 and p["kinds"]["hdr"]["exposures"] == [60.0, 120.0, 300.0]
    assert p["object"] == {"name": "M42 Orion Nebula", "kind": "hdr", "guessed": True}
    json.dumps(p)                                                                       # numbers, not numpy's


def test_an_objects_kind():
    assert S.kind_of("Galassia di Andromeda") == "broadband" and S.kind_of("Pleiadi") == "hdr"
    assert S.kind_of("Nebulosa Velo Dell'Ovest") == "narrowband" and S.kind_of("Barnard 33") == "broadband"
    assert S.kind_of("Nebulosa Velo Dell'Ovest", {"Nebulosa Velo Dell'Ovest": "broadband"}) == "broadband"


def test_a_header_is_read_again_only_when_its_file_changed(tmp_path, monkeypatch):
    d, cache = night(tmp_path), tmp_path / "frames.json"
    first = F.scan(d, cache=cache)
    monkeypatch.setattr(F, "header", lambda f: (_ for _ in ()).throw(AssertionError(f"read again: {f}")))
    assert F.scan(d, cache=cache) == first                                       # all from the cache
    xisf(d / "light_0.xisf", frame(SKY * 200), "Light", 200.0, "Optolong L-eXtreme")  # a frame changed
    monkeypatch.undo()
    again = {h["file"]: h for h in F.scan(d, cache=cache)}
    assert again[str(d / "light_0.xisf")]["exposure_s"] == 200.0 and len(again) == len(first)

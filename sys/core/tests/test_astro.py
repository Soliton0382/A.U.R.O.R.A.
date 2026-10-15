# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 Astro (ROADMAP 79 step 0): the inventory of a telescope's PC read into a profile, the darks' library of this
machine read from names and headers (never the site), the files of the person's folder. Made-up equipment."""
import json
import struct
from pathlib import Path

from aurora import ast_inventory as A

INV = """\ufeff# astro inventory 2026-01-02 21:00 (script 2)

== system
Microsoft Windows 11 Pro 10.0.1; CPU Example N100 (4 threads); RAM 8 GB
disk C: 50 GB free of 200 GB ()

== astronomy software installed
N.I.N.A. - Nighttime Imaging 'N' Astronomy | 3.1.0 | C:\\x
PHD 2 version 2.6.13 | 2.6.13 | C:\\y

== ASCOM: platform and drivers
platform: 7.0
Telescope : ASCOM.Simulator.Telescope | Telescope Simulator for .NET
Telescope : ASCOM.Example.Telescope | Example Mount

== devices (USB / serial)
ZWO ASI224MC | OK

== N.I.N.A. profiles
-- a.profile name=Garden (01/01/2026 20:00:00)
  site: lat 41.9 lon 12.5 elevation 50 m (rounded)
  CameraSettings : Gain=120; Offset=30; PixelSize=3.76; Temperature=-5; LastDeviceName=Example Cam
  TelescopeSettings : FocalLength=400; FocalRatio=5; MountName=Example Mount; Name=Refractor 80; Id=ASCOM.Example.Telescope
  GuiderSettings : GuiderName=PHD2_Single
  ImageFileSettings : FilePath=E:\\\\Images; FileType=FITS
N.I.N.A. sequences: M31.json, M42.json
N.I.N.A. last log, errors and warnings:
  2026-01-01T20:00:00|ERROR|X.cs|Get|1|Focuser timeout
  2026-01-01T20:01:00|ERROR|X.cs|Get|1|Focuser timeout
  2026-01-01T20:02:00|ERROR|X.cs|Get|1|Focuser timeout

== PHD2: the current profile, its settings and the guide logs
profile 1: Garden guide (current)
settings of the current profile:
  name=Garden guide
  focalLength=160
  pixelsize=3.75
  XGuideAlgorithm=5
  YGuideAlgorithm=4
  ExposureDurationMs=2000
guide logs in: C:\\Users\\x\\Documents\\PHD2
guide logs: 3; the latest: PHD2_GuideLog_a.txt (120 KB)

== ASTAP
program: C:\\Program Files\\astap\\astap.exe
star databases: d50

== darks (folders with 'dark' in the name: count and an example file name, which usually holds exposure, gain, temperature)
looked in: E:\\Images\\
E:\\Images\\Darks: 20 files, e.g. dark_120s_-5C.fits

# end
"""


def test_the_inventory_becomes_a_profile_with_its_scales_and_checks():
    p = A.parse(INV)
    r = p["rig"]
    assert p["script"] == 2 and r["telescope"] == "Refractor 80" and r["focal_mm"] == 400 and r["mount"] == "Example Mount"
    assert r["scale_arcsec_px"] == round(206.265 * 3.76 / 400, 2)                     # 1.94″/px
    g = r["guiding"]
    assert g["profile"] == "Garden guide" and g["ra_algorithm"] == "Predictive PEC (GP)" and g["dec_algorithm"] == "Resist Switch"
    assert g["scale_arcsec_px"] == round(206.265 * 3.75 / 160, 2) and g["ratio"] == round(g["scale_arcsec_px"] / r["scale_arcsec_px"], 1)
    assert p["drivers"]["Telescope"] == ["Example Mount"]                               # simulators left out
    assert p["darks"][0]["files"] == 20 and r["site"] == {"lat": 41.9, "lon": 12.5, "elevation_m": 50.0}
    assert any("Focuser timeout" in c["why"] for c in p["checks"])                       # an error that repeats
    assert "Refractor 80" in A.text(p)


def _xisf(path: Path, keywords: dict, frames: int) -> None:
    xml = ('<?xml version="1.0"?><xisf version="1.0"><Image id="integration">'
           + "".join(f'<FITSKeyword name="{k}" value="{v}" comment=""/>' for k, v in keywords.items())
           + f'<Property id="PixInsight:ProcessingHistory" type="String">&lt;parameter id=&quot;numberOfImages&quot; value=&quot;{frames}&quot;/&gt;</Property>'
           + "</Image></xisf>").encode()
    path.write_bytes(b"XISF0100" + struct.pack("<I", len(xml)) + b"\0\0\0\0" + xml + b"\0" * 1024)


def test_the_darks_library_says_what_matches_the_camera_and_never_reads_the_site(cfg, tmp_path):
    lib_dir = tmp_path / "Darks"
    (lib_dir / "old").mkdir(parents=True)
    _xisf(lib_dir / "Dark_BIN-1_EXPOSURE-120.00s_120Gain_30Offset.xisf",
          {"IMAGETYP": "'Integrated dark'", "EXPTIME": "120.000", "INSTRUME": "'Example Cam'", "XBINNING": "1",
           "DATE-OBS": "'2025-12-01T20:00:00'", "LAT-OBS": "41.90123", "LONG-OBS": "12.49876"}, 30)
    _xisf(lib_dir / "old" / "Dark_EXPOSURE-60.00s_120g_10o.xisf", {"IMAGETYP": "'Integrated dark'", "EXPTIME": "60"}, 20)
    cfg.values["AURORA_ASTRO_DARKS_DIR"] = str(lib_dir)
    lib = A.darks_library(cfg)
    now = next(d for d in lib["darks"] if not d["old"])
    assert (now["exposure_s"], now["gain"], now["offset"], now["frames"], now["date"]) == (120.0, 120.0, 30.0, 30, "2025-12-01")
    assert "41.9" not in json.dumps(lib) and "12.49" not in json.dumps(lib)               # the site never read
    m = A.darks_for(lib, A.parse(INV)["rig"])
    assert m["match"] == [120.0] and m["other"] == []                                    # the old one left out


def test_the_page_the_api_and_the_plugin_are_there():
    core = Path(__file__).resolve().parents[1]
    api = (core / "aurora" / "api" / "astro.py").read_text(encoding="utf-8")
    assert '"/v1/aurora/astro/script"' in api and "x-file-name" in api and "Depends(auth)" in api
    assert (core.parents[0] / "plugins" / "astro" / "astro_inventory.ps1").is_file()
    m = json.loads((core.parents[0] / "plugins" / "astro" / "plugin.json").read_text(encoding="utf-8"))
    assert m["page"] == "astro" and set(m["effects"].values()) == {"read"} and m["sandbox"]["network"] is False
    js = (core / "webui" / "js" / "modules" / "astro.js").read_text(encoding="utf-8")
    assert 'id: "astro"' in js and "AURORA_ASTRO_DARKS_DIR" in js


def test_every_settings_box_has_its_guided_window_made_from_what_is_written():
    """Owner, 16 Oct: «un tasto wizard in ogni sezione che richiede una configurazione… si compone dinamicamente»."""
    core = Path(__file__).resolve().parents[1] / "webui" / "js" / "modules"
    form = (core / "settings_form.js").read_text(encoding="utf-8")
    assert "openWizard(specs" in form and "wz.open" in form                         # in every settings box
    plugins = (core / "plugins.js").read_text(encoding="utf-8")
    assert "guide: { title: p.name, intro: setup[code]" in plugins                   # a plugin's own guide first
    wz = (core / "wizard.js").read_text(encoding="utf-8")
    assert 's.type === "bool"' in wz and "s.secret" in wz and '"/v1/aurora/settings"' in wz


def test_of_a_server_only_its_version_is_kept_and_a_public_network_warns_only_with_the_firewall_on():
    """Script 3 copied Stellarium's status into the inventory — the exact site and its name (16 Oct): never kept."""
    links = INV.replace("== ASTAP", "== connections\nnetwork profile: Wi-Fi = Public\n"
                        'server: Stellarium remote control answers 200: {"location":{"latitude":41.90123,"name":"Somewhere"}}\n'
                        'server: PHD2 event server answers: {"Event":"Version","PHDVersion":"2.6.14","Host":"PC"}\n\n== ASTAP')
    p = A.parse(links.replace("(script 2)", "(script 3)"))
    assert "41.90123" not in json.dumps(p) and "Somewhere" not in json.dumps(p)          # the rounded site stays
    assert [s["text"] for s in p["links"]["servers"]] == ["", "versione 2.6.14"]
    assert any("Pubblica" in c["what"] for c in p["checks"])
    off = A.parse(links.replace("(script 2)", "(script 4)").replace("Public\n", "Public\nwindows firewall: Public = off\n", 1))
    assert not any("Pubblica" in c["what"] for c in off["checks"])

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌌 The sky to choose from (ROADMAP N30): the Sun, the Moon and an object where astropy puts them (reference values
computed once with astropy 8 for a made-up site, M235), the public catalogues read from made-up rows, the night's
ranking and the field's fit on a made-up catalogue and equipment. No network: the forecast is given."""
import json
from pathlib import Path

import numpy as np
import pytest

from aurora import ast_catalog as C, ast_sky as S, ast_skyplan as P

LAT, LON = 44.0, 11.0
# instant (unix), the Sun's, the Moon's (from the ground) and M31's altitude, the Moon's lit fraction — astropy 8
REF = [(1772744400, -40.011, 12.666, 11.619, 0.9384),
       (1784511000, -19.027, -41.752, 60.997, 0.3602),
       (1798153200, -69.148, 65.858, 34.597, 0.9869)]


@pytest.mark.parametrize("t,sun,moon,m31,lit", REF)
def test_the_sun_the_moon_and_an_object_are_where_astropy_puts_them(t, sun, moon, m31, lit):
    j = S.jd(np.array([t]))
    sra, sdec, _ = S.sun(j)
    assert abs(S.altitude(sra, sdec, LAT, LON, j)[0, 0] - sun) < 0.05
    mra, mdec, _, _, par = S.moon(j)
    geo = S.altitude(mra, mdec, LAT, LON, j)[0, 0]
    ground = geo - np.degrees(np.arcsin(np.sin(np.radians(par[0])) * np.cos(np.radians(geo))))
    assert abs(ground - moon) < 0.4
    ra, dec = S.precess(np.array([10.6847]), np.array([41.2690]), j[0])
    assert abs(S.altitude(ra, dec, LAT, LON, j)[0, 0] - m31) < 0.05
    assert abs(S.moon_lit(j)[0] - lit) < 0.01


@pytest.mark.parametrize("noon,dusk", [(1782043200, 1782077280), (1797854400, 1797873960)])
def test_the_astronomical_dusk_is_within_two_minutes(noon, dusk):
    n = S.night(LAT, LON, noon, step_min=1)
    assert abs(n["dusk"] - dusk) <= 120


NGC = """Name;Type;RA;Dec;Const;MajAx;MinAx;PosAng;B-Mag;V-Mag;J-Mag;H-Mag;K-Mag;SurfBr;Hubble;Pax;Pm-RA;Pm-Dec;RadVel;Redshift;Cstar U-Mag;Cstar B-Mag;Cstar V-Mag;M;NGC;IC;Cstar Names;Identifiers;Common names;NED notes;OpenNGC notes;Sources
NGC0224;G;00:42:44.35;+41:16:08.6;And;177.83;69.66;35;4.29;3.44;;;;23.63;;;;;;;;;;031;;;;;Andromeda Galaxy;;;
NGC9001;G;01:00:00.00;+40:00:00.0;And;0.5;0.4;;15.2;14.9;;;;;;;;;;;;;;;;;;;;;;
NGC9002;HII;20:59:17.14;+44:31:43.6;Cyg;120.00;30.00;;4.00;;;;;;;;;;;;;;;;;;;;Example Nebula;;;
NGC9003;Dup;20:59:17.14;+44:31:43.6;Cyg;;;;;;;;;;;;;;;;;;;;;;;;;;;
NGC9004;OCl;03:00:00.00;+60:00:00.0;Cas;10;10;;;12.5;;;;;;;;;;;;;;;;;;;;;;
NGC9005;*;03:00:00.00;+60:00:00.0;Cas;;;;;;;;;;;;;;;;;;;;;;;;;;;
"""
SH2 = """#comment
_RAJ2000\t_DEJ2000\trecno\tSh2\tDiam\tBright
deg\tdeg\t \t \tarcmin\t
----\t----\t--\t--\t--\t-
314.8214\t44.5288\t1\t117\t240\t3
100.0000\t10.0000\t2\t900\t20\t1
"""


def test_the_catalogues_keep_what_a_camera_can_take_and_a_known_region_becomes_an_alias():
    objs = C.openngc(NGC)
    names = [o["name"] for o in objs]
    assert names == ["M31", "NGC 9002"]            # the faint galaxy, the duplicate, the star and the faint cluster out
    assert objs[0]["aliases"] == ["NGC 224"] and objs[0]["common"] == ["Andromeda Galaxy"]
    merged = C.merge(objs, C.sharpless(SH2))
    assert [o["name"] for o in merged] == ["M31", "NGC 9002", "Sh2-900"]
    assert merged[1]["aliases"] == ["Sh2-117"]
    assert C.find(merged, "m 31")["name"] == "M31" and C.find(merged, "andromeda")["name"] == "M31"
    assert C.find(merged, "sh2-117")["name"] == "NGC 9002" and C.find(merged, "nothing here") is None


FIELD = {"w_deg": 1.457, "h_deg": 0.978, "px": [4164, 2795], "scale": 1.26}


def test_the_field_says_what_fits_what_is_small_and_the_mosaics_panels():
    assert P.fit({"maj": 80, "min": 50}, FIELD)["panels"] == 1            # fits with its long side along the field's
    # M31's catalogue size (2.97° × 1.17°, its faint outskirts) against 1.46° × 0.98°: 3 columns × 2 rows
    assert P.fit({"maj": 178, "min": 70}, FIELD)["panels"] == 6
    assert P.fit({"maj": 150, "min": 40}, FIELD)["words"] == "non entra: mosaico 3×1"
    assert P.fit({"maj": 2, "min": 2}, FIELD)["weight"] == 0.2            # 2′ in a degree: tiny
    assert P.fit({"maj": 6, "min": 6}, FIELD)["weight"] == 0.5            # 6′: small
    assert P.fit({"maj": None}, FIELD)["words"] == "dimensione non nota"


def _profile():
    return {"rig": {"site": {"lat": LAT, "lon": LON}, "scale_arcsec_px": 1.26}}


def _folder(tmp_path):
    (tmp_path / "frames.json").write_text(json.dumps({"x": {"h": {"kind": "light", "pixels": {"w": 4164, "h": 2795}}}}))
    return tmp_path


OBJS = [{"name": "North", "aliases": [], "common": [], "type": "HII", "ra": 0.0, "dec": 60.0, "maj": 40, "min": 40,
         "mag": None},
        {"name": "Galaxy", "aliases": [], "common": [], "type": "G", "ra": 10.0, "dec": 45.0, "maj": 30, "min": 10, "mag": 9},
        {"name": "South", "aliases": [], "common": [], "type": "HII", "ra": 0.0, "dec": -70.0, "maj": 40, "min": 40,
         "mag": None}]


def test_the_night_ranks_what_is_up_and_never_what_never_rises(tmp_path):
    cfg = {"AURORA_TIMEZONE": "UTC"}
    p = P.plan(cfg, _profile(), _folder(tmp_path), "2026-10-20", objects=OBJS, fc={"hours": {}, "seeing": {}})
    names = [r["name"] for r in p["targets"]]
    assert "South" not in names and set(names) == {"North", "Galaxy"}    # dec −70° never rises at 44° N
    assert p["field"]["w_deg"] == 1.457 and p["night"]["dusk"] and p["night"]["dark_h"] > 9
    one = P.plan(cfg, _profile(), _folder(tmp_path), "2026-10-20", objects=OBJS, fc={"hours": {}, "seeing": {}}, name="north")
    assert one["targets"][0]["name"] == "North" and one["hourly"]
    assert "Notte del 2026-10-20" in P.text(p) and "North" in P.text(p)


def test_a_clouded_night_is_said_and_the_ranking_holds_only_if_it_opens(tmp_path):
    cfg = {"AURORA_TIMEZONE": "UTC"}
    t0 = int(P.start_of("2026-10-20", P.ZoneInfo("UTC")).timestamp())
    fc = {"hours": {t0 + h * 3600: 100 for h in range(30)}, "seeing": {}}
    p = P.plan(cfg, _profile(), _folder(tmp_path), "2026-10-20", objects=OBJS, fc=fc)
    assert p["clouds_ignored"] and p["night"]["clear_dark_h"] == 0 and p["targets"]
    assert "solo se il cielo si apre" in P.text(p)


def test_no_site_no_plan(tmp_path):
    p = P.plan({"AURORA_TIMEZONE": "UTC", "AURORA_WEATHER_LAT": "", "AURORA_WEATHER_LON": ""}, None, tmp_path,
               objects=OBJS, fc={})
    assert "nessun sito" in p["error"]


def test_the_page_the_api_and_the_plugin_are_there():
    core = Path(__file__).resolve().parents[1]
    api = (core / "aurora" / "api" / "astro.py").read_text(encoding="utf-8")
    assert '"/v1/aurora/astro/sky"' in api and "sky_catalog.json" in api
    m = json.loads((core.parents[0] / "plugins" / "sky" / "plugin.json").read_text(encoding="utf-8"))
    # read only but the sequence for N.I.N.A. (N29 phase 2), written in the astro folder alone
    assert {t: e for t, e in m["effects"].items() if e != "read"} == {"sky_sequence": "write_local",
                                                                                "sky_rotation": "write_local"}
    assert m["sandbox"]["write"] == ["AURORA_ASTRO_DIR"]
    js = (core / "webui" / "js" / "modules" / "astro.js").read_text(encoding="utf-8")
    assert 'data-tab="sky"' in js and "skyTab" in js

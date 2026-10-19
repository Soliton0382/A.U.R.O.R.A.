# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A written sequence for other programs (owner, 19 Oct: «compatibile anche con altri software di pianificazione»): the
exposures read from an invented N.I.N.A. sequence, Ekos's .esq and .esl as its loader reads them, CCDciel's .targets
as XMLConfig writes it, the target list with Telescopius's columns; the coordinates back from each text."""
import csv
import io
import re
import zipfile
from xml.etree import ElementTree as ET

import pytest

from aurora import ast_seqexport as X, ast_seqwrite as W
from tests.test_ast_seqwrite import TARGET, items, node, template


def written():
    seq, _ = W.build(template(), {**TARGET, "dec_deg": 44.401, "ra_deg": 312.753}, 180, 38, 1600, 20, 3, -10.0)
    take = next(n for n in _all(seq) if X._kind(n) == "TakeManyExposures")
    take["Items"]["$values"].insert(0, node("SequenceItem.FilterWheel.SwitchFilter", take["$id"], Filter={"_name": "Ha 7nm"}))
    return seq


def _all(n):
    if isinstance(n, dict):
        yield n
        for v in n.values():
            yield from _all(v)
    elif isinstance(n, list):
        for v in n:
            yield from _all(v)


def test_the_exposures_read_back():
    p = X.read(written(), "NGC 7000 Aurora")
    assert p["jobs"] == [{"count": 38, "s": 180.0, "gain": 1600, "offset": 20, "bin": (1, 1), "filter": "Ha 7nm"}]
    assert p["dither_every"] == 3 and p["cool_c"] == -10.0


def test_ekos_as_its_loader_reads_it():
    data, name, media = X.export(written(), "NGC 7000 Aurora", "ekos", "/home/someone/Ekos/")
    z = zipfile.ZipFile(io.BytesIO(data))
    assert name == "NGC 7000 Aurora Ekos.zip" and media == "application/zip"
    q = ET.fromstring(z.read("NGC 7000 Aurora.esq"))
    job = q.find("Job")
    assert q.get("version") == "2.6" and job.findtext("Exposure") == "180" and job.findtext("Count") == "38"
    assert job.find("Temperature").get("force") == "true" and job.findtext("Filter") == "Ha 7nm"
    assert job.findtext("GuideDitherPerJob") == "3"
    props = {v.get("name"): {e.get("name"): e.text for e in v} for v in job.find("Properties")}
    assert props == {"CCD_GAIN": {"GAIN": "1600"}, "CCD_OFFSET": {"OFFSET": "20"}, "CCD_CONTROLS": {"Gain": "1600", "Offset": "20"}}
    s = ET.fromstring(z.read("NGC 7000 Aurora.esl"))
    assert s.findtext("Job/Sequence") == "/home/someone/Ekos/NGC 7000 Aurora.esq"
    assert abs(float(s.findtext("Job/Coordinates/J2000RA")) - 312.753 / 15) < 1e-4
    assert abs(float(s.findtext("Job/Coordinates/J2000DE")) - 44.401) < 1e-4


def test_ccdciel_as_xmlconfig_writes_it():
    data, name, _ = X.export(written(), "NGC 7000 Aurora", "ccdciel")
    root = ET.fromstring(data)
    v = lambda path: root.find(path).get("Value")  # noqa: E731
    assert name.endswith(".targets") and root.tag == "CONFIG" and v("Version") == "5" and v("TargetNum") == "1"
    assert v("Targets/Target1/RA") == "20h51m00.72s" and v("Targets/Target1/Dec") == "+44d24m03.60s"
    step = "Targets/Target1/Plan/Steps/Step1/"
    assert (v(step + "Exposure"), v(step + "Count"), v(step + "Filter"), v(step + "Dither")) == ("180", "38", "Ha 7nm", "True")


def test_the_target_list_with_telescopius_columns():
    data, name, _ = X.export(written(), "NGC 7000 Aurora", "csv", common="Nord America")
    rows = list(csv.DictReader(io.StringIO(data.decode())))
    assert name.endswith(".csv") and len(rows) == 1 and "Right Ascension" not in rows[0]   # N.I.N.A.'s bug avoided
    r = rows[0]
    assert r["Catalogue Entry"] == "NGC 7000" and r["Familiar Name"] == "Nord America"
    nums = [float(x) for x in re.findall(r"[0-9.]+", r["Right Ascension (j2000)"])]
    assert abs(nums[0] + nums[1] / 60 + nums[2] / 3600 - 312.753 / 15) < 1e-4
    assert "38x180s gain 1600 offset 20 Ha 7nm" in r["Notes"]


def test_a_negative_declination_and_an_unknown_format():
    assert X.sexa(-5.3833, False, ("d", "m", "s"), True) == "-05d22m59.88s"
    assert X.sexa(23.999999, True, ("h", "m", "s"), False) == "00h00m00.00s"
    with pytest.raises(ValueError):
        X.export(written(), "x", "voyager")

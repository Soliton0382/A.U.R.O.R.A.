# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A sequence for N.I.N.A. written from a template (ROADMAP N29 phase 2, step 1): only the target and the exposures
change, the rotator's instructions go, a mosaic keeps its first panel, the progress is set back, the template is never
overwritten. An invented template with N.I.N.A.'s shapes ($id, $ref, $values)."""
import json

import pytest

from aurora import ast_sequence, ast_seqwrite as W

SEQ = "NINA.Sequencer."
_ids = iter(range(1, 10_000))


def node(kind: str, parent: str | None = None, **kw) -> dict:
    n = {"$id": str(next(_ids)), "$type": f"{SEQ}{kind}, NINA.Sequencer", **kw}
    if parent:
        n["Parent"] = {"$ref": parent}
    return n


def items(*xs) -> dict:
    return {"$type": "System.Collections.ObjectModel.ObservableCollection", "$values": list(xs)}


def coords(h, m, s, d, dm, ds) -> dict:
    return {"$type": "NINA.Astrometry.InputCoordinates, NINA.Astrometry", "RAHours": h, "RAMinutes": m, "RASeconds": s,
            "NegativeDec": False, "DecDegrees": d, "DecMinutes": dm, "DecSeconds": ds}


def panel(name: str, parent: str, rotate: bool) -> dict:
    p = node("Container.DeepSkyObjectContainer", parent, Name=name,
             Target={"TargetName": name, "PositionAngle": 125.0, "InputCoordinates": coords(5, 35, 0, -5, 23, 0)},
             ExposureInfoList={"$values": [{"Count": 41, "ExposureTime": 120.0}]})
    me = p["$id"]
    take = node("SequenceItem.Imaging.TakeManyExposures", me, Name="Take Many Exposures",
                Conditions=items(node("Conditions.LoopCondition", None, Iterations=20, CompletedIterations=17)))
    take["Items"] = items(node("SequenceItem.Imaging.TakeExposure", take["$id"], ExposureTime=120.0, Gain=-1, Offset=-1,
                               ImageType="LIGHT", ExposureCount=52))
    first = (node("SequenceItem.Platesolving.CenterAndRotate", me, PositionAngle=125.0, Coordinates=coords(5, 35, 0, -5, 23, 0))
             if rotate else node("SequenceItem.Platesolving.Center", me, Coordinates=coords(5, 35, 0, -5, 23, 0)))
    group = node("Container.SequentialContainer", me, Name="20x120s")
    group["Items"] = items(take)
    p["Items"] = items(first, node("SequenceItem.Platesolving.SolveAndRotate", me, PositionAngle=125.0),
                       node("SequenceItem.Utility.MessageBox", me, Text="Fix rotator's screws"), group)
    p["Triggers"] = items(node("Trigger.Guider.DitherAfterExposures", me, AfterExposures=3))
    return p


def template(panels: int = 1) -> dict:
    root = node("Container.SequenceRootContainer", None, Name="Old target")
    start = node("Container.StartAreaContainer", root["$id"])
    start["Items"] = items(node("SequenceItem.Camera.CoolCamera", start["$id"], Temperature=-5.0))
    area = node("Container.TargetAreaContainer", root["$id"])
    area["Items"] = items(*[panel(f"Old target Panel {i + 1}", area["$id"], rotate=panels > 1) for i in range(panels)])
    root["Items"] = items(start, area)
    return root


TARGET = {"name": "NGC 7000", "ra_deg": 314.75, "dec_deg": -44.53}


def test_only_the_target_and_the_exposures_change():
    seq, notes = W.build(template(), TARGET, 180, 40, 1600, 20, dither_every=4, cool_c=-10)
    back = ast_sequence.parse(json.dumps(seq))
    assert back["targets"] == [{"name": "NGC 7000", "ra_h": 20.9833, "dec_deg": -44.53}]
    assert back["exposures"] == [{"s": 180.0, "gain": 1600.0, "offset": 20.0}]
    assert back["cool_c"] == -10.0 and back["dither_every"] == 4
    text = json.dumps(seq)
    assert '"Iterations": 40' in text and '"CompletedIterations": 17' not in text and '"Count": 41' not in text
    assert '"ExposureCount": 52' not in text and '"ExposureCount": 0' in text      # the files numbered from 0
    assert "40x180s" in text and "Old target" not in text


def test_the_rotator_goes_and_a_mosaic_keeps_its_first_panel():
    seq, notes = W.build(template(panels=3), TARGET, 60, 10, 1600, 20)
    text = json.dumps(seq)
    assert "Rotate" not in text and "rotator" not in text and '"PositionAngle": 125.0' not in text
    assert text.count("DeepSkyObjectContainer") == 1 and "Center, NINA" in text
    assert any("3 pannelli" in n for n in notes) and any("CenterAndRotate" in n for n in notes)


def test_the_coordinates_are_ninas_own_fields():
    c = W.coords(83.8221, -5.3911)                         # an invented place
    assert (c["RAHours"], c["RAMinutes"], c["DecDegrees"], c["DecMinutes"], c["NegativeDec"]) == (5, 35, -5, 23, True)
    assert abs(c["RASeconds"] - 17.304) < 0.01 and abs(c["DecSeconds"] - 27.96) < 0.01


def test_a_reference_to_a_node_taken_out_is_never_written():
    t = template()
    t["Items"]["$values"][1]["Items"]["$values"][0]["Extra"] = {"$ref": "99999"}
    with pytest.raises(ValueError, match="rimanda"):
        W.build(t, TARGET, 60, 10, 1600, 20)


def test_written_next_to_the_template_never_over_it(tmp_path):
    (tmp_path / "sequences").mkdir()
    (tmp_path / "sequences" / "narrow.json").write_text(json.dumps(template()), encoding="utf-8")
    r = W.write(tmp_path, "narrowband", {"narrowband": "narrow.json"}, TARGET, 180, 40, 1600, 20,
                {"gain": 1600, "offset": 20}, [{"gain": 1600, "offset": 20, "exposure_s": 180}])
    assert r["file"] == "NGC 7000 Aurora.json" and r["count"] == 40
    assert {c["code"] for c in r["checks"]} == {"seq_no_flip", "seq_no_guiding", "seq_no_autofocus"}   # the darks fit
    assert json.loads((tmp_path / "sequences" / "narrow.json").read_text())["Name"] == "Old target"
    with pytest.raises(ValueError, match="modello"):
        W.write(tmp_path, "broadband", {"narrowband": "narrow.json"}, TARGET, 60, 10, 1600, 20, {}, [])
    with pytest.raises(ValueError, match="pose"):
        W.write(tmp_path, "narrowband", {"narrowband": "narrow.json"}, TARGET, 180, 0, 1600, 20, {}, [])


def test_only_a_file_of_the_sequences_folder_is_given(tmp_path):
    (tmp_path / "sequences").mkdir()
    (tmp_path / "sequences" / "M1 Aurora.json").write_text("{}", encoding="utf-8")
    (tmp_path / "secret.json").write_text("{}", encoding="utf-8")
    assert W.written(tmp_path, "M1 Aurora.json").name == "M1 Aurora.json"
    for bad in ("../secret.json", "missing.json", "M1 Aurora.txt", "/etc/passwd"):
        with pytest.raises(ValueError):
            W.written(tmp_path, bad)


def test_sent_to_nina_as_its_api_asks(tmp_path, monkeypatch):
    # an invented N.I.N.A.: POST sequence/load with the file as body, loaded and never started
    import http.server
    import threading
    from aurora import ast_advice, ast_inventory, ast_rotate
    got = {}

    class Nina(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            got["path"] = self.path
            got["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            busy = got.get("busy")
            self.send_response(400 if busy else 200)
            self.end_headers()
            self.wfile.write(json.dumps({"Success": not busy, "Error": "Sequence is already running" if busy else "",
                                         "Response": "" if busy else "Sequence updated"}).encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Nina)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (tmp_path / "sequences").mkdir()
    (tmp_path / "sequences" / "M1 Aurora.json").write_text('{"Name": "M1"}', encoding="utf-8")
    monkeypatch.setattr(ast_inventory, "folder", lambda cfg: tmp_path)
    monkeypatch.setattr(ast_advice, "telescope_host", lambda cfg: ("127.0.0.1", 4400))
    monkeypatch.setattr(ast_rotate, "PORT", srv.server_port)
    try:
        r = W.send(None, "M1 Aurora.json")
        assert r["sent"] == "M1 Aurora.json" and got["path"] == "/v2/api/sequence/load"
        assert json.loads(got["body"]) == {"Name": "M1"}
        got["busy"] = True
        assert "già in corso" in W.send(None, "M1 Aurora.json")["error"]
    finally:
        srv.shutdown()
    monkeypatch.setattr(ast_rotate, "PORT", 9)                      # nothing listens: said, not raised
    assert "non risponde" in W.send(None, "M1 Aurora.json", timeout=2)["error"]

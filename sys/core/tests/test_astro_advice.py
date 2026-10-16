# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The values advised (ROADMAP N28): an invented rig — the formulas give the numbers they should (sampling, guide
ratio, PHD2's calibration step, dither in guide pixels, torque and counterweight, the critical focus zone), the Guiding
Assistant's runs give the minimum moves, the person's choice judges the row, and a sequence at an offset no dark has
is found before the night."""
import json
import math

from aurora import ast_advice as V
from aurora import ast_sequence as S


def profile() -> dict:
    """A 1000 mm f/5 with 3.76 µm pixels (0.78″/px); a 200 mm guide scope with 2.9 µm pixels (2.99″/px)."""
    rig = {"focal_mm": 1000.0, "focal_ratio": 5.0, "pixel_um": 3.76, "scale_arcsec_px": round(206.265 * 3.76 / 1000, 2),
           "gain": "100", "offset": "50", "cooling_c": -10.0, "meridian_flip": {"MinutesAfterMeridian": "0", "MaxMinutesAfterMeridian": "10"}}
    pairs = [("pixelsize", "2.9"), ("CalibrationDistance", "25"), ("CalibrationDuration", "600"), ("MaxRaDuration", "2500"),
             ("MaxDecDuration", "2500"), ("BacklashCompEnabled", "0"), ("XGuideAlgorithm", "1"), ("minMove", "0.30"),
             ("hysteresis", "0.1"), ("aggression", "0.7"), ("minMove", "0.40"), ("aggression", "1.0"), ("fastSwitch", "1"),
             ("timestamp", "2026-01-01 21:00:00"), ("rec_ra_minmove", "0.20"), ("rec_dec_minmove", "0.25"), ("pa_error", "2.0 arc-min"),
             ("backlash_info", "800 +/- 50 ms"), ("recommendations", "Exp:Try to keep your exposure times in the range of 1.0s to 2.0s"),
             ("timestamp", "2026-01-02 21:00:00"), ("rec_ra_minmove", "0.24"), ("rec_dec_minmove", "0.27"), ("backlash_info", "820 +/- 40 ms"),
             ("timestamp", "2026-01-03 21:00:00"), ("rec_ra_minmove", "0.22"), ("rec_dec_minmove", "0.29"), ("backlash_info", "780 +/- 60 ms"),
             ("focal_length", "200"), ("ra_guide_rate", str(7.5 / 3600))]
    nina = {"GuiderSettings": {"DitherPixels": "5", "SettlePixels": "1.5", "SettleTime": "10", "SettleTimeout": "40"},
            "MeridianFlipSettings": rig["meridian_flip"], "FocuserSettings": {"AutoFocusStepSize": "30"}}
    return {"rig": rig, "phd2": {"pairs": pairs}, "nina": [nina]}


def rows(**facts) -> dict:
    return {r["key"]: r for r in V.advise(profile(), V.facts_of(facts))}


def test_the_formulas_give_their_numbers():
    r = rows(seeing_arcsec=2.0, dither_img_px=10, focuser_step_um=4)
    assert r["sampling"]["current"] == 0.78 and r["sampling"]["status"] == "ok"            # 2.0″ / 0.78 = 2.6 px a star
    assert r["resolution"]["current"] == 0.58                                              # 116 / 200 mm
    guide = 206.265 * 2.9 / 200
    assert r["guide_ratio"]["current"] == round(guide / 0.78, 1) and r["guide_ratio"]["status"] == "ok"
    assert r["cal_step"]["advised"] == round(25 * guide / (7.5 * 12) * 1000 / 50) * 50        # PHD2's calculator: 800 ms
    assert r["cal_step"]["status"] == "warn"                                               # 600 is 25 % short
    assert r["dither"]["advised"] == round(10 * 0.78 / guide, 1) and r["dither"]["status"] == "warn"   # 5 set: 2× too wide
    cfz = 4.88 * 0.55 * 25
    assert r["af_step"]["n"]["cfz"] == round(cfz) and r["af_step"]["advised"] == f"{cfz / 4:.0f}–{3 * cfz / 4:.0f}"


def test_the_assistant_runs_give_the_minimum_moves_and_the_backlash():
    r = rows()
    assert r["min_move_ra"]["current"] == 0.30 and r["min_move_ra"]["advised"] == 0.22      # Hysteresis's own block
    assert r["min_move_dec"]["current"] == 0.40 and r["min_move_dec"]["advised"] == 0.27    # Resist Switch's, before fastSwitch
    assert r["guide_exposure"]["advised"] == "1–2"
    assert r["backlash"]["advised"] == "on 800 ms" and r["backlash"]["status"] == "warn"    # three reads that agree, off
    assert rows(mount_drive="strain_wave")["backlash"]["advised"] == "off"                 # a strain-wave gear: none


def test_sampling_under_and_over():
    assert rows(seeing_arcsec=1.2)["sampling"]["why"] == "sampling_under"
    assert rows(seeing_arcsec=4.0)["sampling"]["why"] == "sampling_over"


def test_payload_torque_and_counterweight():
    r = rows(payload_kg=12, mount_capacity_kg=13, mount_capacity_cw_kg=20, mount_torque_nm=40, saddle_to_ra_m=0.1,
             com_from_saddle_m=0.2, cw_kg=4, cw_arm_m=0.2)
    assert r["payload"]["status"] == "ok" and r["payload"]["n"]["pct"] == 60                 # 12 of 20 with the counterweight
    assert r["torque"]["current"] == round(12 * 9.8 * 0.3, 1) and r["torque"]["status"] == "warn"  # 35.3 of 40 N·m: 88 %
    assert r["torque"]["n"]["com_max"] == round(40 / (12 * 9.8) - 0.1, 2)
    assert rows(payload_kg=12, mount_torque_nm=30, saddle_to_ra_m=0.1, com_from_saddle_m=0.2)["torque"]["status"] == "bad"
    assert r["cw_arm"]["advised"] == 0.9 and r["cw_arm"]["status"] == "warn"                # 12 × 0.3 / 4: it sits too close
    r = rows(payload_kg=12, mount_capacity_kg=13)
    assert r["payload"]["status"] == "warn" and "torque" not in r                           # 92 %; no distances, no torque


def test_the_mount_limit_against_the_flip():
    assert rows()["mount_limit"]["status"] == "unknown"
    assert rows(mount_limit_min=15)["mount_limit"]["status"] == "ok"                         # ≥ 10 + 3
    assert rows(mount_limit_min=5)["mount_limit"]["status"] == "bad"
    stopped = [{"night": "2026-01-03", "sessions": [], "findings": [{"code": "runaway_meridian", "min": -1}]}]
    r = {x["key"]: x for x in V.advise(profile(), V.facts_of({}), stopped)}
    assert r["mount_limit"]["status"] == "bad" and r["mount_limit"]["why"] == "mount_limit_stopped"


def test_the_choice_judges_the_row():
    rs = V.choose(V.advise(profile(), V.facts_of({})), {"min_move_ra": "0.30", "settle_px": "1.0"})
    r = {x["key"]: x for x in rs}
    assert r["min_move_ra"]["status"] == "ok" and r["min_move_ra"]["choice"] == "0.30"     # set as the person wants
    assert r["settle_px"]["status"] == "warn"                                               # 1.5 set, 1.0 wanted


def test_facts_keep_only_what_they_can_be():
    f = V.facts_of({"seeing_arcsec": "abc", "mount_drive": "magic", "payload_kg": "9.5"})
    assert f["seeing_arcsec"] == 3.0 and f["mount_drive"] is None and f["payload_kg"] == 9.5


def sequence(offset: int, flip: bool = True) -> str:
    items = [{"$type": "NINA.Sequencer.SequenceItem.Camera.CoolCamera, NINA.Sequencer", "Temperature": -10.0},
             {"$type": "NINA.Sequencer.SequenceItem.Guider.StartGuiding, NINA.Sequencer"},
             {"$type": "NINA.Sequencer.SequenceItem.Imaging.TakeExposure, NINA.Sequencer", "ExposureTime": 120.0,
              "Gain": 100, "Offset": offset, "ImageType": "LIGHT"}]
    if flip:
        items.append({"$type": "NINA.Sequencer.Trigger.MeridianFlip.MeridianFlipTrigger, NINA.Sequencer"})
    dso = {"$type": "NINA.Sequencer.Container.DeepSkyObjectContainer, NINA.Sequencer",
           "Target": {"TargetName": "Test target", "InputCoordinates": {"RAHours": 5, "RAMinutes": 30, "RASeconds": 0,
                                                                         "DecDegrees": -5, "DecMinutes": 30, "DecSeconds": 0}},
           "Items": {"$values": items}}
    return json.dumps({"$type": "NINA.Sequencer.Container.SequenceRootContainer, NINA.Sequencer", "Items": {"$values": [dso]}})


def test_a_sequence_is_read_and_checked(tmp_path):
    (tmp_path / "ok.json").write_text(sequence(50), encoding="utf-8")
    (tmp_path / "bad.json").write_text(sequence(30, flip=False), encoding="utf-8")
    (tmp_path / "other.json").write_text('{"a": 1}', encoding="utf-8")
    seqs = {s["name"]: s for s in S.sequences(tmp_path)}
    assert set(seqs) == {"ok", "bad"}
    q = seqs["ok"]
    assert q["targets"][0]["ra_h"] == 5.5 and math.isclose(q["targets"][0]["dec_deg"], -5.5)
    assert q["exposures"] == [{"s": 120.0, "gain": 100.0, "offset": 50.0}] and q["cool_c"] == -10 and q["guiding"] and q["flip"]
    darks = [{"exposure_s": 120.0, "gain": 100.0, "offset": 50.0, "old": False}, {"exposure_s": 120.0, "gain": 100.0, "offset": 30.0, "old": True}]
    rig = profile()["rig"]
    assert [f["code"] for f in S.check(q, rig, darks)] == ["seq_no_autofocus"]
    codes = [f["code"] for f in S.check(seqs["bad"], rig, darks)]
    assert codes[0] == "seq_offset" and "seq_no_flip" in codes                               # the old dark at 30 does not count


def test_what_the_programs_have_now_wins_over_the_inventory():
    live = {"phd2": {"exposure_ms": 2000, "ra_min_move": 0.22, "dec_min_move": 0.27},
            "nina": {"GuiderSettings": {"DitherPixels": "3", "SettlePixels": "1.5", "SettleTime": "10", "SettleTimeout": "60"},
                     "CameraSettings": {"Gain": "100", "Offset": "50", "Temperature": "-10"}}}
    r = {x["key"]: x for x in V.advise(profile(), V.facts_of({}), live=live)}
    assert r["min_move_ra"]["current"] == 0.22 and r["min_move_ra"]["status"] == "ok" and r["min_move_ra"]["src"] == "live"
    assert r["guide_exposure"]["current"] == 2.0 and r["guide_exposure"]["status"] == "ok"
    assert r["settle_timeout"]["current"] == 60 and r["settle_timeout"]["src"] == "live"
    assert r["cal_step"]["src"] == "inventory"                                              # not readable live
    assert {x["key"]: x for x in V.advise(profile(), V.facts_of({}))}["min_move_ra"]["src"] == "inventory"


def test_a_value_only_the_person_knows_is_set_not_chosen():
    rs = V.choose(V.advise(profile(), V.facts_of({"mount_limit_min": 15})), {"mount_limit": "8"})
    r = {x["key"]: x for x in rs}["mount_limit"]
    assert r["fact"] == "mount_limit_min" and r["src"] == "fact" and r["current"] == 15
    assert "choice" not in r and r["status"] == "ok"                                     # an old choice there is ignored

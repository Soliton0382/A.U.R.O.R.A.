# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's quick fixes of 2026-10-04: dictation cut to 0.1 s (C121), the backup timer that ignored a new time
(C122), Aurora's PDFs deletable and only those."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))

from aurora import doc_pdf, sns_av  # noqa: E402
import sys_backup_retime  # noqa: E402


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_recording_with_a_timestamp_jump_is_decoded_whole(cfg, tmp_path):
    # what a browser's first recording after the microphone permission looks like: 6 s, a jump of 60 s inside
    f = tmp_path / "jump.webm"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=440:d=6",
                        "-af", r"asetpts='if(gt(N\,4)\,PTS+60/TB\,PTS)'", "-c:a", "libopus", "-f", "webm", str(f)])
    if r.returncode != 0:
        pytest.skip("ffmpeg without libopus")
    assert len(sns_av.decode(f.read_bytes(), cfg)) / 16000 == pytest.approx(6.0, abs=0.1)
    assert len(sns_av.decode(f.read_bytes(), cfg, max_s=2)) / 16000 == pytest.approx(2.0, abs=0.01)


def test_the_backup_time_becomes_a_drop_in_and_nothing_else():
    text = sys_backup_retime.dropin("23:00")
    assert "OnCalendar=\nOnCalendar=*-*-* 23:00:00" in text
    for bad in ("24:00", "23:00\nExecStart=/bin/sh", "7:30", "", "23:00:00"):
        with pytest.raises(ValueError):
            sys_backup_retime.dropin(bad)


def _pdf(path: Path, creator: str | None) -> Path:
    w = PdfWriter()
    w.add_blank_page(100, 100)
    if creator:
        w.add_metadata({"/Creator": creator})
    with path.open("wb") as fh:
        w.write(fh)
    return path


def test_only_a_pdf_aurora_wrote_is_deletable(tmp_path):
    assert doc_pdf.made_by_aurora(_pdf(tmp_path / "a.pdf", "Aurora"))
    assert not doc_pdf.made_by_aurora(_pdf(tmp_path / "b.pdf", "LibreOffice"))     # one of the owner's own
    assert not doc_pdf.made_by_aurora(_pdf(tmp_path / "c.pdf", None))
    (tmp_path / "d.pdf").write_bytes(b"not a pdf")
    assert not doc_pdf.made_by_aurora(tmp_path / "d.pdf")

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Dates as each person writes them (owner, 19 Oct: «la selezione del tipo di formato della data, sai dd-mm-aaaa o
mm-dd-aaaa»): webui/js/dates.js under node — shown in the chosen format, read back from it, a day that does not exist
refused; the preference allowed by the server, chosen beside the time zone, the calendar in the astro date fields."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "webui"


def run(expr: str):
    js = f"const D = await import({json.dumps((WEB / 'js' / 'dates.js').as_uri())}); console.log(JSON.stringify({expr}))"
    out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_shown_in_each_format_and_read_back():
    shown = run('D.FORMATS.map((f) => D.fmtDate("2026-10-19", f))')
    assert shown == ["19/10/2026", "19-10-2026", "10/19/2026", "10-19-2026", "2026-10-19"]
    back = run('D.FORMATS.map((f) => D.parseDate(D.fmtDate("2026-03-04", f), f))')
    assert back == ["2026-03-04"] * 5


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_day_and_month_read_in_the_persons_order_and_impossible_days_refused():
    got = run('[D.parseDate("03/04/2026", "dd/mm/yyyy"), D.parseDate("03/04/2026", "mm/dd/yyyy"), '
              'D.parseDate("31/02/2026", "dd/mm/yyyy"), D.parseDate("2026.10.9"), D.parseDate("ieri")]')
    assert got == ["2026-04-03", "2026-03-04", "", "2026-10-09", ""]


def test_the_preference_the_settings_row_and_the_astro_fields():
    users = (WEB.parent / "aurora" / "api" / "users.py").read_text()
    assert '"date_format": ("dd/mm/yyyy", "dd-mm-yyyy", "mm/dd/yyyy", "mm-dd-yyyy", "yyyy-mm-dd")' in users
    settings = (WEB / "js" / "modules" / "settings.js").read_text()
    assert 's.key === "AURORA_TIMEZONE"' in settings and "dateRow" in settings
    for m in ("astro_sky.js", "astro_collim.js"):
        src = (WEB / "js" / "modules" / m).read_text()
        assert "datePicker(" in src and 'type = "date"' not in src
    assert "/static/js/dates.js" in (WEB / "sw.js").read_text()
    for lang in ("it_IT", "en_US"):
        words = json.loads((WEB / "i18n" / f"{lang}.json").read_text())
        assert {"date.pick", "date.today", "date.clear", "date.format", "date.format_help", "date.saved"} <= set(words)

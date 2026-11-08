# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Every action answers on screen (owner, 9 Nov): a change done from a click redraws the page shown."""
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "webui" / "js"


def test_a_change_from_a_click_redraws_the_page_shown():
    api, main = (JS / "api.js").read_text(), (JS / "main.js").read_text()
    assert "navigator.userActivation" in api and 'new CustomEvent("aurora:acted"' in api     # a click, not a poll
    assert 'addEventListener("aurora:acted"' in main and "v.enter()" in main
    for live in ("chat", "projects", "dj"):                                                  # their own live view
        assert f'"{live}"' in main.split("SELF_LIVE = new Set(")[1].split(")")[0]

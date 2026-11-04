# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C502: what an exception carries (a command line whole) never reaches a log with a password in it."""
import logging

from aurora import sys_log


def test_the_login_of_an_address_and_a_token_are_blanked():
    said = sys_log.hide_secrets("Command '['ffmpeg', '-i', 'rtsp://someone:s3cret%3F@10.0.0.9:554/stream1']' timed out; "
                                "Authorization: Bearer abcdefgh12345678")
    assert "s3cret" not in said and "someone" not in said and "abcdefgh" not in said
    assert "rtsp://***@10.0.0.9:554/stream1" in said


def test_an_ordinary_line_is_left_as_it_is():
    line = "push to https://example.org/a:b failed at 12:30:01, 3 of 4; ratio 1:2 @home"
    assert sys_log.hide_secrets(line) == line


def test_the_traceback_passes_through_too():
    f = sys_log._Formatter("%(message)s")
    try:
        raise RuntimeError("rtsp://someone:s3cret@10.0.0.9/x")
    except RuntimeError as e:
        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "stopped", None, (type(e), e, e.__traceback__))
    assert "s3cret" not in f.format(rec)

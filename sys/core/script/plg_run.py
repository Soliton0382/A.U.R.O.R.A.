#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A plugin with its own libraries and programs (aurora/plg_deps.py, ROADMAP 101): run from the plugin's folder,
<plugin>/.deps first on the import path and <plugin>/.bin first on PATH — in this process only, never in Aurora's.

    "command": ["{python}", "{root}/sys/core/script/plg_run.py", "server.py"]
"""
import os
import runpy
import sys
from pathlib import Path

here = Path.cwd()
if (here / ".deps").is_dir():
    sys.path.insert(0, str(here / ".deps"))
sys.path.insert(0, str(here))                        # its own modules first, as «python server.py» would (C309)
if (here / ".bin").is_dir():
    os.environ["PATH"] = str(here / ".bin") + os.pathsep + os.environ.get("PATH", "")
server = sys.argv[1] if len(sys.argv) > 1 else "server.py"
sys.argv = sys.argv[1:] or [server]
runpy.run_path(str(here / server), run_name="__main__")

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The agent's tools that make something — a proposed change of her own code, an interactive page, a picture — a part
of the Agent (agt_loop) kept apart: no monoliths."""
from __future__ import annotations

import re

import json
import time

from . import agt_change, sys_tests
from .sys_approvals import needs_owner


class AgentMakers:
    """Mixed into agt_loop.Agent: uses its cfg, host, approvals, notify and produced."""

    def _propose(self, args: dict, emit, run_id: str) -> str:
        sid = str(args.get("sandbox_id", ""))
        box = self.cfg.path("AURORA_SANDBOX_DIR") / sid
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", sid) or not box.is_dir():   # a name, never «../..» (C420)
            return f"ERROR: no sandbox {sid!r}"
        files = agt_change.changed_files(box, self.cfg.root)
        if not files:
            return "ERROR: the sandbox has no differences from the live code"
        from . import sys_ethics
        if (protected := [f for f in files if f in sys_ethics.PROTECTED]):
            return ("REFUSED: these files belong to the code of conduct and change only with the owner's own "
                    f"signature: {', '.join(protected)}. Report the need instead.")
        t = sys_tests.run_suite(box, caged=True)        # the agent's code: in the cage (C420)
        emit("change.tests.sandbox", {"ok": t["ok"], "summary": t["summary"]})
        if not t["ok"]:
            return f"REFUSED: the sandbox tests fail ({t['summary']}). Fix them first.\n{t['output'][-3000:]}"
        diff = self.host.call("self", "sandbox_diff", {"sandbox_id": sid}, run_id)["text"]
        preview = {"sandbox_id": sid, "files": files, "diff": diff[:60000], "tests": t["summary"],
                   "services": agt_change.services_for(files)}
        if needs_owner("code_change", self.cfg):
            req = self.approvals.request("code_change", "code_change", args.get("title", "change"),
                                         args.get("purpose", ""), preview, {"sandbox_id": sid}, run_id)
            emit("approval.request", {"id": req["id"], "kind": "code_change", "title": req["title"], "files": files})
            self.notify("approval.pending", {"id": req["id"], "kind": "code_change", "title": req["title"]})
            return f"PROPOSED: waiting for the owner's approval (request {req['id']}). Tests: {t['summary']}."
        out = agt_change.apply(sid, emit, self.cfg)
        return f"APPLIED (forging is automatic): {json.dumps(out, ensure_ascii=False)[:2000]}"

    def _artifact(self, args: dict, emit, run_id: str) -> str:
        """An interactive page (doc_artifact), kept with this turn and shown live in the conversation."""
        from . import doc_artifact
        try:
            f = doc_artifact.create(self.cfg, run_id, str(args.get("title", "")), str(args.get("html", "")))
        except ValueError as e:
            return f"ERROR: {e}"
        self.produced.append(f)
        emit("agent.file", f)
        return f"MADE: {f['name']}, shown live to the owner in the conversation (it has no network: data must be inline)"

    def _picture(self, args: dict, emit, run_id: str) -> str:
        """A new picture (mdl_image.paint, the dream painter), kept with this turn of the conversation."""
        from . import mdl_image, sys_features, sys_uploads
        try:
            sys_features.need(self.cfg, "dreams", "it")
        except sys_features.Missing as e:
            return f"ERROR: {e}"
        prompt, title = str(args.get("prompt", "")).strip()[:900], str(args.get("title", "immagine")).strip()[:80]
        if len(prompt) < 10:
            return "ERROR: describe the picture in English (subject, style, light)"
        name = f"aurora-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            out = mdl_image.paint(prompt, name, self.cfg, emit, title=title)
        except Exception as e:                           # a failed painting is said, never hidden
            return f"ERROR: the picture was not painted: {type(e).__name__}: {str(e)[:300]}"
        path = self.cfg.path("AURORA_IMAGE_DIR") / out["file"]
        item = sys_uploads.public(sys_uploads.save(self.cfg, run_id, out["file"], "image/png", path.read_bytes(),
                                                   role="assistant"))
        f = {"name": out["file"], "url": item["url"], "mime": "image/png"}
        self.produced.append(f)
        emit("agent.file", f)
        return f"PAINTED: {out['file']} ({out.get('seconds', '?')} s), shown to the owner in the conversation"

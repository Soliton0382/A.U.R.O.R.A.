# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia import docids  # noqa: E402

# invented collections for the tests (never a real release's): a Bates-like one and a named one
TEST_COLLECTIONS = [{"name": "ABCD", "pattern": r"^(ABCD\d{8})(?:_dup_\d+)?$", "upper": True},
                    {"name": "REL", "pattern": r"^(REL[-_A-Za-z0-9.]+)$", "upper": False}]


@pytest.fixture(autouse=True)
def _collections():
    docids.configure(TEST_COLLECTIONS)
    yield
    docids._loaded = None


def make_pdf(path: Path, pages: list[str]) -> Path:
    """A real, minimal PDF with one line of text a page (no library: the objects and the xref written by hand)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 11 Tf 40 760 Td ({safe}) Tj ET".encode()
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
        content = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    return path


@pytest.fixture()
def pdfs(tmp_path):
    src = tmp_path / "sources"
    src.mkdir()
    pad = " Received and recorded by the clerk of the office on the same day, copy to the file."
    make_pdf(src / "ABCD00000001.pdf", ["Wire transfer to IBAN GB82 WEST 1234 5698 7654 32 on 12 March 2004." + pad,
                                        "Flight N908JE from Teterboro, pallets bound for the depot." + pad])
    make_pdf(src / "ABCD00000002.pdf", ["Bill of lading: consignee Acme Ltd, IBAN GB82WEST12345698765432"])
    make_pdf(src / "REL-OGR-00012345.pdf", ["Deposition transcript, page one"])
    return src

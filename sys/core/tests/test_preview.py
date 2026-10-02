# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import shutil

import pytest

from aurora import doc_preview as P


def two_pages() -> bytes:
    """A minimal valid PDF of two blank A4 pages (offsets computed, as the format wants)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_only_aurora_s_documents_and_chat_files_are_previewed(cfg):
    docs = cfg.path("AURORA_DOCUMENTS_DIR")
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "rapporto.pdf").write_bytes(two_pages())
    assert P.resolve(cfg, "/v1/aurora/documents/rapporto.pdf") == (docs / "rapporto.pdf").resolve()
    for bad in ("/v1/aurora/documents/../.env", "/v1/aurora/documents/x/../../.env.pdf", "/etc/passwd",
                "/v1/aurora/uploads/../../x", "/v1/aurora/documents/manca.pdf", "/v1/aurora/uploads/0123456789abcdef"):
        with pytest.raises(P.PreviewError):
            P.resolve(cfg, bad)


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="poppler-utils not installed")
def test_a_pdf_becomes_pictures_of_its_pages_and_a_non_pdf_is_refused(cfg, tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(two_pages())
    assert P.pages(f) == 2
    png = P.page_png(cfg, f, 2)
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and P.page_png(cfg, f, 2) == png    # drawn once, then cached
    with pytest.raises(P.PreviewError):
        P.page_png(cfg, f, 3)
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"<html>not a pdf</html>")
    with pytest.raises(P.PreviewError):
        P.pages(fake)

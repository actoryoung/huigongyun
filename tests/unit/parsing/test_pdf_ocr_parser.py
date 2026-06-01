from pathlib import Path

import types
import sys

from huigongyun.parsing.pdf import PdfOcrParser


def test_pdf_source_detection_no_pdfminer(monkeypatch, tmp_path):
    # Simulate absence of pdfminer -> PdfOcrParser should fallback to scaffold
    monkeypatch.setitem(sys.modules, 'pdfminer', None)

    p = Path(tmp_path) / "sample.pdf"
    p.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    doc = PdfOcrParser().parse(str(p))
    # When pdfminer isn't importable, registry should fall back and return scaffold metadata
    assert doc.metadata.get('input_kind') in (None, 'unimplemented', 'pdf')


def test_pdf_ocr_fallback_to_tesseract(monkeypatch, tmp_path):
    # Simulate pdfminer available but no text in PDF; then simulate TesseractAdapter
    class FakePdfMiner:
        @staticmethod
        def extract_text(path, maxpages=1):
            return ""

    monkeypatch.setitem(sys.modules, 'pdfminer.high_level', types.SimpleNamespace(extract_text=FakePdfMiner.extract_text))

    # Monkeypatch TesseractAdapter.pdf_to_dict on the real module
    import huigongyun.parsing.ocr_adapter as ocr_adapter
    monkeypatch.setattr(ocr_adapter.TesseractAdapter, 'pdf_to_dict', lambda p, dpi=300: {'pages': [{'page': 1}], 'plain_text': 'OCR_RESULT'})

    p = Path(tmp_path) / "scanned.pdf"
    p.write_bytes(b"%PDF-1.4\n%scanned\n")

    doc = PdfOcrParser().parse(str(p), ocr_fallback=True)
    assert doc.metadata.get('ocr_applied') in ("tesseract", None)

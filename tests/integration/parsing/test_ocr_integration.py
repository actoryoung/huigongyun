import os
import pytest


@pytest.mark.skipif(os.environ.get('OCR_POC') != '1', reason='OCR integration tests are skipped by default')
def test_ocr_integration(ocr_sample_path):
    from src.parsing.ocr_adapter import TesseractAdapter

    # This will run a real OCR pass; ensure system tesseract and poppler are installed.
    out = TesseractAdapter.image_to_dict(str(ocr_sample_path))
    assert 'pages' in out
    assert isinstance(out['pages'], list)

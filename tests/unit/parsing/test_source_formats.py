from pathlib import Path

from src.parsing.registry import build_default_source_registry


def test_source_registry_routes_pdf_inputs(tmp_path):
    document = build_default_source_registry().parse(str(Path(tmp_path) / "drawing.pdf"))

    assert document.metadata["input_kind"] == "pdf"
    assert document.metadata["source_format"] == "pdf"


def test_source_registry_routes_word_inputs(tmp_path):
    document = build_default_source_registry().parse(str(Path(tmp_path) / "specification.docx"))

    assert document.metadata["input_kind"] == "word"
    assert document.metadata["source_format"] == "word"


def test_source_registry_routes_image_inputs(tmp_path):
    document = build_default_source_registry().parse(str(Path(tmp_path) / "capture.png"))

    assert document.metadata["input_kind"] == "image"
    assert document.metadata["source_format"] == "image"


def test_source_registry_routes_dwg_inputs(tmp_path):
    document = build_default_source_registry().parse(str(Path(tmp_path) / "layout.dwg"))

    assert document.metadata["input_kind"] == "dwg"
    assert document.metadata["source_format"] == "dwg"

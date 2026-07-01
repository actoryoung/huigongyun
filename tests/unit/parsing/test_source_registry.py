from pathlib import Path

from openpyxl import Workbook

from src.parsing.registry import build_default_source_registry


def test_source_registry_uses_excel_parser_for_workbooks(tmp_path):
    workbook_path = Path(tmp_path) / "sample.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "主元件清单"
    sheet.append(["柜号", "物料名称", "数量"])
    sheet.append(["K1", "断路器", 2])
    workbook.save(workbook_path)

    document = build_default_source_registry().parse(str(workbook_path))

    assert document.metadata["input_kind"] == "excel"
    assert document.metadata["parse_status"] == "ok"
    assert document.metadata["sheets"][0]["records"][0]["柜号"] == "K1"


def test_source_registry_uses_generic_scaffold_for_unknown_formats(tmp_path):
    source_path = Path(tmp_path) / "drawing.xyz"

    document = build_default_source_registry().parse(str(source_path))

    assert document.metadata["input_kind"] == "unimplemented"
    assert document.metadata["parse_status"] == "scaffold"
    assert document.metadata["source_format"] == "xyz"
from pathlib import Path

from openpyxl import Workbook

from src.parsing.excel import ExcelProjectParser


def test_directory_input_returns_ambiguous_marker(tmp_path):
    first = Path(tmp_path) / "a.xlsx"
    second = Path(tmp_path) / "b.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["柜号", "物料名称", "数量"])
    ws.append(["K1", "断路器", 1])
    wb.save(first)
    wb.save(second)

    document = ExcelProjectParser().parse(str(tmp_path))

    assert document.metadata["input_kind"] == "directory"
    assert document.metadata["parse_status"] == "ambiguous"
    assert len(document.metadata["candidate_files"]) == 2
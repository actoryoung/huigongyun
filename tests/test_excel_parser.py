from pathlib import Path

from openpyxl import Workbook

from huigongyun.adapters import DefaultProjectParser
from huigongyun.parsing.excel import ExcelProjectParser


def test_excel_project_parser_reads_sheet_metadata(tmp_path):
    workbook_path = Path(tmp_path) / "sample.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "主元件清单"
    sheet.append(["柜号", "物料名称", "数量"])
    sheet.append(["K1", "断路器", 2])
    sheet.append(["K2", "接触器", 4])
    workbook.save(workbook_path)

    document = ExcelProjectParser().parse(str(workbook_path))

    assert document.project_name == "sample"
    assert document.metadata["input_kind"] == "excel"
    assert document.metadata["sheet_count"] == 1
    assert document.metadata["sheets"][0]["name"] == "主元件清单"
    assert document.metadata["sheets"][0]["headers"] == ["柜号", "物料名称", "数量"]
    assert document.metadata["sheets"][0]["sample_rows"][0] == ["K1", "断路器", 2]


def test_default_project_parser_uses_excel_parser_for_workbooks(tmp_path):
    workbook_path = Path(tmp_path) / "project.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "主元件清单"
    sheet.append(["柜号", "物料名称", "数量"])
    sheet.append(["K1", "断路器", 2])
    workbook.save(workbook_path)

    document = DefaultProjectParser().parse(str(workbook_path))

    assert document.metadata["input_kind"] == "excel"
    assert document.metadata["sheets"][0]["records"][0]["柜号"] == "K1"

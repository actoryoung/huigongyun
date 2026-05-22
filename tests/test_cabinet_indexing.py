from pathlib import Path

from openpyxl import Workbook

from huigongyun.parsing.excel import ExcelProjectParser
from huigongyun.indexing.cabinets import CabinetIndexBuilder


def test_cabinet_index_builder_returns_markers_for_missing_numbers(tmp_path):
    workbook_path = Path(tmp_path) / "cabinets.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "主元件清单"
    sheet.append(["柜号", "柜型", "物料名称", "数量"])
    sheet.append(["", "进线柜", "断路器", 1])
    sheet.append(["K1", "进线柜", "接触器", 2])
    workbook.save(workbook_path)

    document = ExcelProjectParser().parse(str(workbook_path))
    cabinet_result = CabinetIndexBuilder().build(document)

    assert len(cabinet_result.cabinets) == 2
    assert cabinet_result.cabinets[0].cabinet_no == "UNASSIGNED"
    assert cabinet_result.notes == ["unresolved_cabinet_numbers_present"]
    assert cabinet_result.unresolved_rows[0]["marker"] == "cabinet_no:UNASSIGNED"

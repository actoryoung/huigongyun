from pathlib import Path

from openpyxl import Workbook

from huigongyun.bootstrap import build_context, build_default_pipeline


def test_pipeline_generates_cabinets_and_bom_from_excel(tmp_path):
    workbook_path = Path(tmp_path) / "bom.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "主元件清单"
    sheet.append(["柜号", "柜型", "物料名称", "规格型号", "单位", "数量", "品牌"])
    sheet.append(["K1", "进线柜", "断路器", "MCCB-250A", "台", 1, "施耐德"])
    sheet.append(["K1", "进线柜", "接触器", "LC1D", "只", 2, "施耐德"])
    workbook.save(workbook_path)

    pipeline = build_default_pipeline()
    result = pipeline.run(build_context(input_path=str(workbook_path), output_dir=str(tmp_path / "out")))

    assert result.project.metadata["input_kind"] == "excel"
    assert len(result.cabinets) == 1
    assert result.cabinets[0].cabinet_no == "K1"
    assert result.cabinets[0].cabinet_type == "进线柜"
    assert len(result.bom_lines) == 2
    assert len(result.summary) == 2
    assert result.summary[0].quantity in {1.0, 2.0}

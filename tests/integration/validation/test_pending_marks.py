from pathlib import Path

from openpyxl import Workbook

from src.bootstrap import build_context, build_default_pipeline


def test_pipeline_retains_pending_marks_for_unresolved_fields(tmp_path):
    workbook_path = Path(tmp_path) / "pending.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "主元件清单"
    sheet.append(["柜号", "物料名称", "数量"])
    sheet.append(["", "断路器", 1])
    workbook.save(workbook_path)

    result = build_default_pipeline().run(build_context(str(workbook_path), str(tmp_path / "out")))

    issue_types = {issue.issue_type for issue in result.issues}
    assert "missing_bom_cabinet_no" in issue_types
    assert "missing_cabinet_no" in issue_types
    assert "pending_material_spec" in issue_types
    assert "pending_material_brand" in issue_types

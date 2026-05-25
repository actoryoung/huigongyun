from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from huigongyun.webapp import RUN_STORAGE, create_app


def test_webapp_runs_pipeline_and_renders_download_links(tmp_path):
    workbook_path = Path(tmp_path) / "web.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "主元件清单"
    sheet.append(["柜号", "柜型", "物料名称", "规格型号", "单位", "数量", "品牌"])
    sheet.append(["K1", "进线柜", "断路器", "MCCB-250A", "台", 1, "施耐德"])
    workbook.save(workbook_path)

    app = create_app()
    app.testing = True

    with app.test_client() as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "上传 Excel 主元器件清单" in response.get_data(as_text=True)

        with workbook_path.open("rb") as fh:
            run_response = client.post(
                "/run",
                data={"input_file": (BytesIO(fh.read()), "web.xlsx")},
                content_type="multipart/form-data",
            )

    assert run_response.status_code == 200
    rendered = run_response.get_data(as_text=True)
    assert "运行结果" in rendered
    assert "download" in rendered
    assert "web_result.json" in rendered or "web_result.xlsx" in rendered


def test_webapp_allows_manual_round_trip_edit_and_reexport(tmp_path):
    RUN_STORAGE.clear()

    workbook_path = Path(tmp_path) / "web_edit.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "主元件清单"
    sheet.append(["柜号", "物料名称", "规格型号", "单位", "数量"])
    sheet.append(["K1", "断路器", "MCCB-250A", "台", 1])
    workbook.save(workbook_path)

    app = create_app()
    app.testing = True

    with app.test_client() as client:
        with workbook_path.open("rb") as fh:
            run_response = client.post(
                "/run",
                data={"input_file": (BytesIO(fh.read()), "web_edit.xlsx")},
                content_type="multipart/form-data",
            )

        assert run_response.status_code == 200
        run_id = next(reversed(RUN_STORAGE))

        edit_response = client.post(
            f"/edit/{run_id}",
            data={
                "scope": "bom",
                "target": "K1",
                "material_name": "断路器",
                "field_name": "brand",
                "value": "施耐德",
            },
        )

    assert edit_response.status_code == 200
    rendered = edit_response.get_data(as_text=True)
    assert "人工修正" in rendered
    assert "施耐德" in rendered

    run_state = RUN_STORAGE[run_id]
    result = run_state["result"]
    assert any(edit.field_name == "brand" for edit in result.user_edits)
    assert any(bom_line.material.brand == "施耐德" for bom_line in result.bom_lines)

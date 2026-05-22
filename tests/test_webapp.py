from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from huigongyun.webapp import create_app


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

import pytest
from pathlib import Path


@pytest.fixture
def tmp_project_dir(tmp_path):
    """Wrapper around pytest's tmp_path for creating a lightweight project dir."""
    return tmp_path


@pytest.fixture
def sample_excel_path(tmp_path):
    """Return a path to a sample .xlsx in tests/fixtures if present; otherwise create a tiny workbook.

    TODO: Replace placeholder with real sample files in tests/fixtures/ for integration tests.
    """
    fixtures_dir = Path(__file__).parent / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    xlsx_files = list(fixtures_dir.glob("*.xlsx"))
    if xlsx_files:
        return xlsx_files[0]
    try:
        from openpyxl import Workbook

        p = tmp_path / "sample.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["Header1", "Header2"])
        wb.save(p)
        return p
    except Exception:
        placeholder = fixtures_dir / "SAMPLE_README.md"
        if not placeholder.exists():
            placeholder.write_text("Add real sample .xlsx files here for integration tests.\n")
        return placeholder


@pytest.fixture
def app_client():
    """Provide Flask test client when available; skip otherwise."""
    try:
        from huigongyun.webapp import create_app
    except Exception:
        import pytest as _pytest

        _pytest.skip("webapp.create_app not available in this environment")
    app = create_app()
    app.testing = True
    with app.test_client() as client:
        yield client

# TODO: Add real sample .xlsx files under tests/fixtures/ for integration and e2e tests.


@pytest.fixture
def fake_db_mem():
    """提供一个简单的内存字典，用于模拟 DB 存储（供 fake conn 使用）。"""
    return {}


@pytest.fixture
def sample_run_summary():
    """返回一个简单的运行摘要样例，用于任务层测试。"""
    return {
        "project_name": "sample",
        "cabinet_count": 0,
        "bom_line_count": 0,
        "summary_count": 0,
        "issue_count": 0,
        "outputs": {},
        "issues": [],
        "user_edits": [],
    }

# TODO: Replace placeholder fixtures with real sample files under tests/fixtures/

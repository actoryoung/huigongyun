"""VersionDiffer 集成测试 — 使用真实项目 D Excel 文件。"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

from src.bootstrap import build_context, build_default_pipeline
from src.comparison.differ import VersionDiffer

PROJECT_D_DIR = Path(__file__).parent.parent.parent.parent / "examples" / "项目D_中英文设备清单" / "输入资料"
OLD_EXCEL = PROJECT_D_DIR / "项目D_设备清单_20250701.xlsx"
NEW_EXCEL = PROJECT_D_DIR / "项目D_设备清单_新版.xlsx"


def _is_project_d_available() -> bool:
    return OLD_EXCEL.exists() and NEW_EXCEL.exists()


def _run_pipeline(excel_path: Path):
    """Helper: run pipeline on an Excel file and return ProjectResult."""
    pipeline = build_default_pipeline()
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = build_context(str(excel_path), tmpdir)
        return pipeline.run(ctx)


@pytest.mark.skipif(not _is_project_d_available(), reason="项目D Excel 文件不可用")
class TestProjectDVersionDiff:
    """使用项目 D 实际数据的集成测试。"""

    def test_both_versions_parse_successfully(self):
        """两个版本都应能成功解析。"""
        result_old = _run_pipeline(OLD_EXCEL)
        assert result_old.project.project_name is not None
        assert len(result_old.cabinets) >= 0

        result_new = _run_pipeline(NEW_EXCEL)
        assert result_new.project.project_name is not None

    def test_diff_produces_structured_output(self):
        """差异结果应为有效的 VersionDiff JSON。"""
        result_old = _run_pipeline(OLD_EXCEL)
        result_new = _run_pipeline(NEW_EXCEL)

        differ = VersionDiffer()
        diff = differ.compare(result_old, result_new,
                              old_label="20250701", new_label="新版")

        # 验证 diff 可序列化为 JSON
        diff_dict = asdict(diff)
        json_str = json.dumps(diff_dict, ensure_ascii=False, indent=2, default=str)
        assert len(json_str) > 0

        # 验证 metrics 存在
        assert "cabinet_count" in diff.old_metrics
        assert "cabinet_count" in diff.new_metrics
        assert "bom_line_count" in diff.old_metrics
        assert "bom_line_count" in diff.new_metrics

    def test_diff_detects_material_differences(self):
        """两个版本之间应存在物料差异。"""
        result_old = _run_pipeline(OLD_EXCEL)
        result_new = _run_pipeline(NEW_EXCEL)

        differ = VersionDiffer()
        diff = differ.compare(result_old, result_new,
                              old_label="20250701", new_label="新版")

        # 至少一个维度有差异（结构已知不同）
        total_changes = (
            len(diff.cabinet_changes) +
            len(diff.bom_changes) +
            len(diff.summary_changes)
        )
        assert total_changes > 0, "期望两个版本之间存在至少一类差异"

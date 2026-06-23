"""VersionDiffer 单元测试。

使用合成的 ProjectResult 对象验证各类差异检测：
两结果相同、完全新增、完全删除、混合变更、字段级变更。
"""

from __future__ import annotations

import pytest

from huigongyun.comparison.differ import VersionDiffer
from huigongyun.comparison.models import VersionDiff
from huigongyun.models import (
    BomLine,
    CabinetRecord,
    MaterialRecord,
    ProjectDocument,
    ProjectResult,
)


def _make_result(
    name: str = "test",
    cabinets: list[CabinetRecord] | None = None,
    bom_lines: list[BomLine] | None = None,
    summary: list[MaterialRecord] | None = None,
) -> ProjectResult:
    return ProjectResult(
        project=ProjectDocument(project_name=name),
        cabinets=cabinets or [],
        bom_lines=bom_lines or [],
        summary=summary or [],
    )


class TestVersionDiffer:
    """VersionDiffer 单元测试套件。"""

    def test_identical_results_produce_no_changes(self):
        """两个相同的 ProjectResult 应不产生任何差异。"""
        cabinets = [CabinetRecord(cabinet_no="K1", cabinet_type="馈线柜", quantity=2)]
        materials = [
            BomLine(
                cabinet_no="K1",
                material=MaterialRecord(
                    name="断路器", spec="MCCB-250A", brand="施耐德", quantity=2,
                    normalized_name="断路器", normalized_spec="MCCB-250A",
                ),
            )
        ]

        old = _make_result("test", cabinets=cabinets, bom_lines=materials.copy())
        new = _make_result("test", cabinets=cabinets, bom_lines=materials.copy())

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert isinstance(diff, VersionDiff)
        assert diff.old_version_label == "old"
        assert diff.new_version_label == "new"
        assert diff.cabinet_changes == []
        assert diff.bom_changes == []
        assert diff.summary_changes == []

    def test_empty_results_produce_no_changes(self):
        """两个空结果应不产生差异。"""
        differ = VersionDiffer()
        diff = differ.compare(_make_result(), _make_result())
        assert diff.cabinet_changes == []
        assert diff.bom_changes == []
        assert diff.summary_changes == []
        assert diff.old_metrics["cabinet_count"] == 0
        assert diff.new_metrics["cabinet_count"] == 0

    def test_added_cabinet_detected(self):
        """新增柜体应被检测为 added。"""
        old = _make_result("old")
        new = _make_result("new", cabinets=[CabinetRecord(cabinet_no="K1")])

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert len(diff.cabinet_changes) == 1
        assert diff.cabinet_changes[0].change_type == "added"
        assert diff.cabinet_changes[0].cabinet_no == "K1"
        assert diff.cabinet_changes[0].new is not None
        assert diff.cabinet_changes[0].old is None

    def test_removed_cabinet_detected(self):
        """删除柜体应被检测为 removed。"""
        old = _make_result("old", cabinets=[CabinetRecord(cabinet_no="K1")])
        new = _make_result("new")

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert len(diff.cabinet_changes) == 1
        assert diff.cabinet_changes[0].change_type == "removed"
        assert diff.cabinet_changes[0].cabinet_no == "K1"

    def test_changed_cabinet_field_detected(self):
        """柜体字段变更应被检测为 changed。"""
        old = _make_result("old", cabinets=[CabinetRecord(cabinet_no="K1", quantity=1)])
        new = _make_result("new", cabinets=[CabinetRecord(cabinet_no="K1", quantity=2)])

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert len(diff.cabinet_changes) == 1
        assert diff.cabinet_changes[0].change_type == "changed"
        fc = diff.cabinet_changes[0].field_changes or {}
        assert "quantity" in fc
        assert fc["quantity"] == (1, 2)

    def test_added_bom_line_detected(self):
        """新增 BOM 行应被检测为 added。"""
        old = _make_result("old")
        new = _make_result("new", bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(name="断路器", spec="MCCB-250A", brand="施耐德"))
        ])

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert len(diff.bom_changes) == 1
        assert diff.bom_changes[0].change_type == "added"
        assert diff.bom_changes[0].new_value is not None

    def test_removed_bom_line_detected(self):
        """删除 BOM 行应被检测为 removed。"""
        old = _make_result("old", bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(name="断路器", spec="MCCB-250A", brand="施耐德"))
        ])
        new = _make_result("new")

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert len(diff.bom_changes) == 1
        assert diff.bom_changes[0].change_type == "removed"

    def test_bom_line_quantity_change_detected(self):
        """BOM 行数量变更应被检测为 changed。"""
        old = _make_result("old", bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(
                name="断路器", spec="MCCB-250A", brand="施耐德", quantity=1,
                normalized_name="断路器", normalized_spec="MCCB-250A",
            ))
        ])
        new = _make_result("new", bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(
                name="断路器", spec="MCCB-250A", brand="施耐德", quantity=3,
                normalized_name="断路器", normalized_spec="MCCB-250A",
            ))
        ])

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert len(diff.bom_changes) == 1
        assert diff.bom_changes[0].change_type == "changed"
        fc = diff.bom_changes[0].field_changes or {}
        assert "quantity" in fc
        assert fc["quantity"] == (1, 3)

    def test_brand_change_detected_as_remove_add(self):
        """品牌变更会改变复合键，应体现为 remove + add。"""
        old = _make_result("old", bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(
                name="断路器", spec="MCCB-250A", brand="施耐德",
                normalized_name="断路器", normalized_spec="MCCB-250A",
            ))
        ])
        new = _make_result("new", bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(
                name="断路器", spec="MCCB-250A", brand="ABB",
                normalized_name="断路器", normalized_spec="MCCB-250A",
            ))
        ])

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        # 品牌是复合键的一部分，所以品牌变更 = 1 删除 + 1 新增
        assert len(diff.bom_changes) == 2
        change_types = {c.change_type for c in diff.bom_changes}
        assert change_types == {"removed", "added"}

    def test_metrics_reflect_version_differences(self):
        """metrics 应反映版本间的高级指标差异。"""
        old = _make_result("old", cabinets=[CabinetRecord(cabinet_no="K1")], bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(name="A", quantity=1)),
            BomLine(cabinet_no="K1", material=MaterialRecord(name="B", quantity=1)),
        ])
        new = _make_result("new", cabinets=[
            CabinetRecord(cabinet_no="K1"),
            CabinetRecord(cabinet_no="K2"),
        ], bom_lines=[
            BomLine(cabinet_no="K1", material=MaterialRecord(name="A", quantity=2)),
        ])

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert diff.old_metrics["cabinet_count"] == 1
        assert diff.new_metrics["cabinet_count"] == 2
        assert diff.old_metrics["bom_line_count"] == 2
        assert diff.new_metrics["bom_line_count"] == 1

    def test_custom_labels_preserved(self):
        """自定义标签应被保留在 diff 中。"""
        differ = VersionDiffer()
        diff = differ.compare(_make_result(), _make_result(),
                              old_label="20250701", new_label="新版")
        assert diff.old_version_label == "20250701"
        assert diff.new_version_label == "新版"

    def test_summary_changes_detected(self):
        """汇总物料差异应被检测。"""
        old = _make_result("old", summary=[
            MaterialRecord(name="断路器", spec="MCCB-250A", brand="施耐德",
                           normalized_name="断路器", quantity=5),
        ])
        new = _make_result("new", summary=[
            MaterialRecord(name="断路器", spec="MCCB-250A", brand="施耐德",
                           normalized_name="断路器", quantity=8),
        ])

        differ = VersionDiffer()
        diff = differ.compare(old, new)

        assert len(diff.summary_changes) == 1
        assert diff.summary_changes[0].change_type == "changed"
        fc = diff.summary_changes[0].field_changes or {}
        assert "quantity" in fc

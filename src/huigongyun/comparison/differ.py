"""版本差异比较器 — 对比两个 ProjectResult 的柜体、BOM 行和汇总物料。

使用方式::

    from huigongyun.comparison.differ import VersionDiffer

    differ = VersionDiffer()
    diff = differ.compare(old_result, new_result,
                          old_label="20250701", new_label="新版")
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectResult, QuoteLine
from .models import CabinetDiff, DiffItem, VersionDiff


def _make_cabinet_key(cabinet: CabinetRecord) -> str:
    return cabinet.cabinet_no


def _make_bom_key(line: BomLine) -> str:
    m = line.material
    return (
        f"({line.cabinet_no}, {m.normalized_name or m.name}, "
        f"{m.normalized_spec or m.spec or ''}, {m.brand or ''})"
    )


def _make_summary_key(m: MaterialRecord) -> str:
    return f"({m.normalized_name or m.name}, {m.normalized_spec or m.spec or ''}, {m.brand or ''})"


def _make_quote_key(q: QuoteLine) -> str:
    return f"({q.cabinet_no}, {q.material_name}, {q.spec or ''}, {q.brand or ''})"


def _record_to_dict(obj: Any, skip: tuple[str, ...] = ()) -> dict[str, Any]:
    """Convert a dataclass instance to dict, optionally skipping fields."""
    d = asdict(obj)
    for key in skip:
        d.pop(key, None)
    return d


def _compute_field_changes(old: dict[str, Any], new: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Return only fields that differ between old and new dicts."""
    changes: dict[str, tuple[Any, Any]] = {}
    all_keys = set(old.keys()) | set(new.keys())
    for key in sorted(all_keys):
        ov = old.get(key)
        nv = new.get(key)
        if ov != nv:
            changes[key] = (ov, nv)
    return changes


class VersionDiffer:
    """对比两个 ``ProjectResult`` 并生成 ``VersionDiff`` 报告。"""

    def compare(
        self,
        old: ProjectResult,
        new: ProjectResult,
        old_label: str = "old",
        new_label: str = "new",
    ) -> VersionDiff:
        """执行全维度比较。

        Args:
            old: 旧版本 ProjectResult
            new: 新版本 ProjectResult
            old_label: 旧版本标签（如 "20250701"）
            new_label: 新版本标签（如 "新版"）

        Returns:
            VersionDiff 包含所有维度的差异。
        """
        diff = VersionDiff(
            old_version_label=old_label,
            new_version_label=new_label,
            old_metrics=self._compute_metrics(old),
            new_metrics=self._compute_metrics(new),
            cabinet_changes=self._compare_cabinets(old, new),
            bom_changes=self._compare_bom_lines(old, new),
            summary_changes=self._compare_summary(old, new),
            quote_changes=self._compare_quotes(old, new),
            metadata_changes=self._compare_metadata(old, new),
        )
        return diff

    def _compute_metrics(self, result: ProjectResult) -> dict[str, Any]:
        return {
            "cabinet_count": len(result.cabinets),
            "bom_line_count": len(result.bom_lines),
            "summary_material_count": len(result.summary),
            "quote_line_count": len(result.quote_lines),
            "issue_count": len(result.issues),
            "total_quote": result.quote_totals.get("project_total", None),
        }

    def _compare_cabinets(self, old: ProjectResult, new: ProjectResult) -> list[CabinetDiff]:
        changes: list[CabinetDiff] = []

        old_map: dict[str, CabinetRecord] = {_make_cabinet_key(c): c for c in old.cabinets}
        new_map: dict[str, CabinetRecord] = {_make_cabinet_key(c): c for c in new.cabinets}

        old_keys = set(old_map.keys())
        new_keys = set(new_map.keys())

        # Removed cabinets
        for key in sorted(old_keys - new_keys):
            changes.append(CabinetDiff(
                cabinet_no=key,
                change_type="removed",
                old=_record_to_dict(old_map[key], skip=("sources",)),
            ))

        # Added cabinets
        for key in sorted(new_keys - old_keys):
            changes.append(CabinetDiff(
                cabinet_no=key,
                change_type="added",
                new=_record_to_dict(new_map[key], skip=("sources",)),
            ))

        # Changed cabinets
        for key in sorted(old_keys & new_keys):
            old_dict = _record_to_dict(old_map[key], skip=("sources",))
            new_dict = _record_to_dict(new_map[key], skip=("sources",))
            field_changes = _compute_field_changes(old_dict, new_dict)
            if field_changes:
                changes.append(CabinetDiff(
                    cabinet_no=key,
                    change_type="changed",
                    old=old_dict,
                    new=new_dict,
                    field_changes=field_changes,
                ))

        return changes

    def _compare_bom_lines(self, old: ProjectResult, new: ProjectResult) -> list[DiffItem]:
        return self._compare_dict_items(
            old_items=old.bom_lines,
            new_items=new.bom_lines,
            key_fn=_make_bom_key,
            dict_fn=lambda b: _record_to_dict(b.material, skip=("source",)),
        )

    def _compare_summary(self, old: ProjectResult, new: ProjectResult) -> list[DiffItem]:
        return self._compare_dict_items(
            old_items=old.summary,
            new_items=new.summary,
            key_fn=_make_summary_key,
            dict_fn=lambda m: _record_to_dict(m, skip=("source",)),
        )

    def _compare_quotes(self, old: ProjectResult, new: ProjectResult) -> list[DiffItem]:
        return self._compare_dict_items(
            old_items=old.quote_lines,
            new_items=new.quote_lines,
            key_fn=_make_quote_key,
            dict_fn=lambda q: _record_to_dict(q),
        )

    def _compare_metadata(self, old: ProjectResult, new: ProjectResult) -> dict[str, Any]:
        old_meta = {k: v for k, v in old.project.metadata.items() if k != "risk_dashboard"}
        new_meta = {k: v for k, v in new.project.metadata.items() if k != "risk_dashboard"}
        changes = _compute_field_changes(old_meta, new_meta)

        # Also track project name changes
        result: dict[str, Any] = {"field_changes": changes}
        if old.project.project_name != new.project.project_name:
            result["project_name"] = {
                "old": old.project.project_name,
                "new": new.project.project_name,
            }
        if set(old.project.files) != set(new.project.files):
            result["files"] = {
                "old": old.project.files,
                "new": new.project.files,
            }
        return result

    def _compare_dict_items(
        self,
        old_items: list[Any],
        new_items: list[Any],
        key_fn,
        dict_fn,
    ) -> list[DiffItem]:
        """Generic comparison for list-based collections keyed by a composite key."""
        changes: list[DiffItem] = []

        old_map: dict[str, Any] = {key_fn(item): item for item in old_items}
        new_map: dict[str, Any] = {key_fn(item): item for item in new_items}

        old_keys = set(old_map.keys())
        new_keys = set(new_map.keys())

        # Removed
        for key in sorted(old_keys - new_keys):
            changes.append(DiffItem(
                change_type="removed",
                key=key,
                old_value=dict_fn(old_map[key]),
            ))

        # Added
        for key in sorted(new_keys - old_keys):
            changes.append(DiffItem(
                change_type="added",
                key=key,
                new_value=dict_fn(new_map[key]),
            ))

        # Changed
        for key in sorted(old_keys & new_keys):
            od = dict_fn(old_map[key])
            nd = dict_fn(new_map[key])
            fc = _compute_field_changes(od, nd)
            if fc:
                changes.append(DiffItem(
                    change_type="changed",
                    key=key,
                    old_value=od,
                    new_value=nd,
                    field_changes=fc,
                ))

        return changes

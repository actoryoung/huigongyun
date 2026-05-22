from __future__ import annotations

from collections import Counter

from ..models import BomLine, ProjectResult, ValidationIssue


class DefaultProjectValidator:
    """Apply basic MVP validation rules for cabinets and BOM lines."""

    def validate(self, result: ProjectResult) -> ProjectResult:
        issues: list[ValidationIssue] = []
        issues.extend(self._validate_cabinets(result))
        issues.extend(self._validate_bom_lines(result))
        issues.extend(self._validate_duplicates(result))
        issues.extend(self._validate_pending_marks(result))
        result.issues = issues
        return result

    def _validate_cabinets(self, result: ProjectResult) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not result.cabinets:
            issues.append(
                ValidationIssue(
                    issue_type="missing_cabinet",
                    severity="warning",
                    message="No cabinet records were extracted from the input.",
                )
            )

        for cabinet in result.cabinets:
            if not cabinet.cabinet_no or cabinet.cabinet_no == "UNASSIGNED":
                issues.append(
                    ValidationIssue(
                        issue_type="missing_cabinet_no",
                        severity="warning",
                        message="Cabinet number is missing or unassigned.",
                        cabinet_no=cabinet.cabinet_no,
                    )
                )
            if cabinet.quantity <= 0:
                issues.append(
                    ValidationIssue(
                        issue_type="invalid_cabinet_quantity",
                        severity="warning",
                        message="Cabinet quantity must be greater than zero.",
                        cabinet_no=cabinet.cabinet_no,
                        details={"quantity": cabinet.quantity},
                    )
                )
        return issues

    def _validate_pending_marks(self, result: ProjectResult) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        metadata = result.project.metadata if isinstance(result.project.metadata, dict) else {}
        unresolved_rows = metadata.get("cabinet_index_unresolved_rows", [])
        for unresolved in unresolved_rows:
            if not isinstance(unresolved, dict):
                continue
            issues.append(
                ValidationIssue(
                    issue_type=str(unresolved.get("reason", "pending_marker")),
                    severity="info",
                    message="Unresolved cabinet marker retained for later data confirmation.",
                    cabinet_no="UNASSIGNED",
                    details={
                        "sheet_name": unresolved.get("sheet_name"),
                        "row_no": unresolved.get("row_no"),
                        "marker": unresolved.get("marker"),
                    },
                )
            )

        for bom_line in result.bom_lines:
            material = bom_line.material
            if not material.spec:
                issues.append(
                    ValidationIssue(
                        issue_type="pending_material_spec",
                        severity="info",
                        message="Material spec is not finalized yet.",
                        cabinet_no=bom_line.cabinet_no,
                        material_name=material.name,
                        details={"marker": "spec:pending"},
                    )
                )
            if not material.brand and not material.manufacturer:
                issues.append(
                    ValidationIssue(
                        issue_type="pending_material_brand",
                        severity="info",
                        message="Material brand is not finalized yet.",
                        cabinet_no=bom_line.cabinet_no,
                        material_name=material.name,
                        details={"marker": "brand:pending"},
                    )
                )

        return issues

    def _validate_bom_lines(self, result: ProjectResult) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for bom_line in result.bom_lines:
            material = bom_line.material
            if not bom_line.cabinet_no or bom_line.cabinet_no == "UNASSIGNED":
                issues.append(
                    ValidationIssue(
                        issue_type="missing_bom_cabinet_no",
                        severity="warning",
                        message="BOM line has no cabinet number.",
                        material_name=material.name,
                    )
                )
            if not material.name:
                issues.append(
                    ValidationIssue(
                        issue_type="missing_material_name",
                        severity="error",
                        message="BOM line has no material name.",
                        cabinet_no=bom_line.cabinet_no,
                    )
                )
            if material.quantity <= 0:
                issues.append(
                    ValidationIssue(
                        issue_type="invalid_material_quantity",
                        severity="warning",
                        message="Material quantity must be greater than zero.",
                        cabinet_no=bom_line.cabinet_no,
                        material_name=material.name,
                        details={"quantity": material.quantity},
                    )
                )
            if material.brand and material.normalized_name is None:
                material.normalized_name = material.name
        return issues

    def _validate_duplicates(self, result: ProjectResult) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        cabinet_counter = Counter(cabinet.cabinet_no for cabinet in result.cabinets if cabinet.cabinet_no)
        for cabinet_no, count in cabinet_counter.items():
            if count > 1:
                issues.append(
                    ValidationIssue(
                        issue_type="duplicate_cabinet",
                        severity="warning",
                        message="Cabinet number appears multiple times.",
                        cabinet_no=cabinet_no,
                        details={"count": count},
                    )
                )

        bom_key_counter = Counter(self._bom_key(bom_line) for bom_line in result.bom_lines)
        for key, count in bom_key_counter.items():
            if count > 1:
                cabinet_no, material_name, spec, brand = key
                issues.append(
                    ValidationIssue(
                        issue_type="duplicate_bom_line",
                        severity="warning",
                        message="Duplicate BOM line detected.",
                        cabinet_no=cabinet_no or None,
                        material_name=material_name or None,
                        details={"spec": spec, "brand": brand, "count": count},
                    )
                )

        return issues

    def _bom_key(self, bom_line: BomLine) -> tuple[str, str, str, str]:
        material = bom_line.material
        return (
            bom_line.cabinet_no or "",
            material.normalized_name or material.name or "",
            material.normalized_spec or material.spec or "",
            material.brand or material.manufacturer or "",
        )

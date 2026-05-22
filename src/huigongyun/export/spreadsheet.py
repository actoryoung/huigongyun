from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from openpyxl import Workbook

from ..models import ProjectResult


class ProjectExporter:
    """Export result artifacts to JSON and Excel."""

    def export(self, result: ProjectResult, output_dir: str) -> dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        json_path = output_path / f"{result.project.project_name}_result.json"
        excel_path = output_path / f"{result.project.project_name}_result.xlsx"

        result.outputs = {"json": str(json_path), "excel": str(excel_path)}
        json_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_excel(result, excel_path)
        return result.outputs

    def _write_excel(self, result: ProjectResult, excel_path: Path) -> None:
        workbook = Workbook()

        self._write_project_sheet(workbook, result)
        self._write_cabinets_sheet(workbook, result)
        self._write_bom_sheet(workbook, result)
        self._write_summary_sheet(workbook, result)
        self._write_issues_sheet(workbook, result)

        if "Sheet" in workbook.sheetnames:
            workbook.remove(workbook["Sheet"])
        workbook.save(excel_path)

    def _write_project_sheet(self, workbook: Workbook, result: ProjectResult) -> None:
        sheet = workbook.create_sheet("Project")
        sheet.append(["project_name", result.project.project_name])
        sheet.append(["files", json.dumps(result.project.files, ensure_ascii=False)])
        sheet.append(["metadata", json.dumps(result.project.metadata, ensure_ascii=False, default=str)])

    def _write_cabinets_sheet(self, workbook: Workbook, result: ProjectResult) -> None:
        sheet = workbook.create_sheet("Cabinets")
        sheet.append(["cabinet_no", "cabinet_type", "rated_current", "quantity", "confidence", "remarks"])
        for cabinet in result.cabinets:
            sheet.append([
                cabinet.cabinet_no,
                cabinet.cabinet_type,
                cabinet.rated_current,
                cabinet.quantity,
                cabinet.confidence,
                cabinet.remarks,
            ])

    def _write_bom_sheet(self, workbook: Workbook, result: ProjectResult) -> None:
        sheet = workbook.create_sheet("BOM")
        sheet.append([
            "cabinet_no",
            "material_name",
            "spec",
            "unit",
            "quantity",
            "brand",
            "normalized_name",
            "normalized_spec",
            "confidence",
            "derived_from",
            "risk_tags",
        ])
        for bom_line in result.bom_lines:
            material = bom_line.material
            sheet.append([
                bom_line.cabinet_no,
                material.name,
                material.spec,
                material.unit,
                material.quantity,
                material.brand,
                material.normalized_name,
                material.normalized_spec,
                material.confidence,
                bom_line.derived_from,
                json.dumps(bom_line.risk_tags, ensure_ascii=False),
            ])

    def _write_summary_sheet(self, workbook: Workbook, result: ProjectResult) -> None:
        sheet = workbook.create_sheet("Summary")
        sheet.append(["material_name", "spec", "unit", "quantity", "brand", "normalized_name", "normalized_spec", "confidence"])
        for material in result.summary:
            sheet.append([
                material.name,
                material.spec,
                material.unit,
                material.quantity,
                material.brand,
                material.normalized_name,
                material.normalized_spec,
                material.confidence,
            ])

    def _write_issues_sheet(self, workbook: Workbook, result: ProjectResult) -> None:
        sheet = workbook.create_sheet("Issues")
        sheet.append(["issue_type", "severity", "message", "cabinet_no", "material_name", "details"])
        for issue in result.issues:
            sheet.append([
                issue.issue_type,
                issue.severity,
                issue.message,
                issue.cabinet_no,
                issue.material_name,
                json.dumps(issue.details, ensure_ascii=False, default=str),
            ])

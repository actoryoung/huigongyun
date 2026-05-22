from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from ..models import ProjectDocument


@dataclass(slots=True)
class SheetSnapshot:
    name: str
    row_count: int
    data_row_count: int
    column_count: int
    headers: list[str]
    sample_rows: list[list[Any]]
    records: list[dict[str, Any]]


class ExcelProjectParser:
    """Parse Excel-based project input into a normalized document model.

    The MVP version focuses on workbook discovery and sheet-level structure.
    Later stages can promote rows into cabinets, BOM lines, and validation rules.
    """

    def parse(self, input_path: str) -> ProjectDocument:
        path = Path(input_path)
        source = self._resolve_source(path)
        if source is None:
            return ProjectDocument(
                project_name=path.stem or "project",
                files=[str(path)],
                metadata={
                    "input_kind": "unknown",
                    "parse_status": "missing_input",
                    "message": "Input file not found; returned scaffold document.",
                },
            )

        if source.is_dir():
            return ProjectDocument(
                project_name=path.stem or "project",
                files=[str(source)],
                metadata={
                    "input_kind": "directory",
                    "parse_status": "ambiguous",
                    "candidate_files": self._list_excel_candidates(source),
                    "message": "Directory contains one or more Excel files; choose a specific workbook before parsing.",
                },
            )

        if source.suffix.lower() not in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
            return ProjectDocument(
                project_name=source.stem,
                files=[str(source)],
                metadata={
                    "input_kind": "non_excel",
                    "parse_status": "skipped",
                    "message": "Only Excel parsing is implemented in this stage.",
                },
            )

        workbook = load_workbook(source, data_only=True, read_only=True)
        sheets = [self._snapshot_sheet(sheet_name, workbook[sheet_name]) for sheet_name in workbook.sheetnames]

        return ProjectDocument(
            project_name=source.stem,
            files=[str(source)],
            metadata={
                "input_kind": "excel",
                "parse_status": "ok",
                "sheet_count": len(sheets),
                "sheets": [self._sheet_snapshot_to_dict(snapshot) for snapshot in sheets],
            },
        )

    def _resolve_source(self, path: Path) -> Path | None:
        if path.is_file():
            return path
        if path.is_dir():
            if self._list_excel_candidates(path):
                return path
        return None

    def _list_excel_candidates(self, path: Path) -> list[str]:
        return [
            str(candidate)
            for candidate in sorted(path.iterdir())
            if candidate.is_file() and candidate.suffix.lower() in {".xlsx", ".xlsm", ".xltx", ".xltm"}
        ]

    def _snapshot_sheet(self, sheet_name: str, worksheet: Any) -> SheetSnapshot:
        rows = list(worksheet.iter_rows(values_only=True))
        cleaned_rows: list[tuple[int, list[Any]]] = []
        for row_no, row in enumerate(rows, start=1):
            cleaned_row = self._clean_row(row)
            if any(cell is not None and cell != "" for cell in cleaned_row):
                cleaned_rows.append((row_no, cleaned_row))
        if cleaned_rows:
            header_row_no, header_row = cleaned_rows[0]
            headers = [str(value).strip() if value is not None else "" for value in header_row]
            data_rows = cleaned_rows[1:]
            sample_rows = data_rows[:5]
            records = [self._row_to_record(headers, row, row_no, sheet_name) for row_no, row in data_rows]
        else:
            headers = []
            sample_rows = []
            records = []
            header_row_no = 0
        column_count = max((len(row) for _, row in cleaned_rows), default=0)
        return SheetSnapshot(
            name=sheet_name,
            row_count=len(cleaned_rows),
            data_row_count=len(records),
            column_count=column_count,
            headers=headers,
            sample_rows=[row for _, row in sample_rows],
            records=records,
        )

    def _clean_row(self, row: tuple[Any, ...]) -> list[Any]:
        return [value if value is not None else "" for value in row]

    def _sheet_snapshot_to_dict(self, snapshot: SheetSnapshot) -> dict[str, Any]:
        return {
            "name": snapshot.name,
            "row_count": snapshot.row_count,
            "data_row_count": snapshot.data_row_count,
            "column_count": snapshot.column_count,
            "headers": snapshot.headers,
            "sample_rows": snapshot.sample_rows,
            "records": snapshot.records,
        }

    def _row_to_record(self, headers: list[str], row: list[Any], row_no: int, sheet_name: str) -> dict[str, Any]:
        record: dict[str, Any] = {"_sheet_name": sheet_name, "_row_no": row_no}
        for index, header in enumerate(headers):
            if not header:
                continue
            record[header] = row[index] if index < len(row) else ""
        return record

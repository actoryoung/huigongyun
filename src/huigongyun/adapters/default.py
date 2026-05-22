from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..interfaces import BomGenerator, CabinetExtractor, Exporter, MaterialNormalizer, ProjectParser, Validator
from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectDocument, ProjectResult, ValidationIssue


class DefaultProjectParser(ProjectParser):
    def parse(self, input_path: str) -> ProjectDocument:
        path = Path(input_path)
        return ProjectDocument(project_name=path.stem, files=[str(path)])


class DefaultCabinetExtractor(CabinetExtractor):
    def extract(self, document: ProjectDocument) -> ProjectResult:
        result = ProjectResult(project=document)
        result.cabinets.append(CabinetRecord(cabinet_no="TBD-01", cabinet_type="unknown", remarks="placeholder"))
        return result


class DefaultMaterialNormalizer(MaterialNormalizer):
    def normalize(self, result: ProjectResult) -> ProjectResult:
        for material in result.summary:
            material.normalized_name = material.normalized_name or material.name
            material.normalized_spec = material.normalized_spec or material.spec
        return result


class DefaultBomGenerator(BomGenerator):
    def generate(self, result: ProjectResult) -> ProjectResult:
        if not result.bom_lines:
            placeholder = MaterialRecord(name="placeholder material", unit="set", quantity=1, remarks="placeholder")
            result.bom_lines.append(
                BomLine(
                    cabinet_no=result.cabinets[0].cabinet_no if result.cabinets else "TBD-01",
                    material=placeholder,
                    derived_from="default-scaffold",
                    risk_tags=["needs-implementation"],
                )
            )
        return result


class DefaultValidator(Validator):
    def validate(self, result: ProjectResult) -> ProjectResult:
        if not result.cabinets:
            result.issues.append(
                ValidationIssue(
                    issue_type="missing_cabinet",
                    severity="warning",
                    message="No cabinet extracted yet; scaffold placeholder used.",
                )
            )
        return result


class DefaultExporter(Exporter):
    def export(self, result: ProjectResult, output_dir: str) -> dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        json_path = output_path / f"{result.project.project_name}_result.json"
        result.outputs = {"json": str(json_path)}
        payload = asdict(result)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return result.outputs

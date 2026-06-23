"""默认适配器实现：将具体阶段连接成可运行的流水线。

该模块为示例流水线提供简单且有明确取舍的默认实现，用于组装端到端
工作流。每个类体量较小，并将实际工作委托给对应子模块实现。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..interfaces import BomGenerator, CabinetExtractor, Exporter, MaterialNormalizer, ProjectParser, QuoteGenerator, Validator
from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectDocument, ProjectResult, ValidationIssue
from ..parsing.registry import SourceParserRegistry, build_default_source_registry
from ..validation.default import DefaultProjectValidator
from ..generation.excel_bom import ExcelBomAggregator, ExcelCabinetAndBomExtractor
from ..export.spreadsheet import ProjectExporter
from ..normalization.default import DefaultMaterialNormalizer as _DefaultMaterialNormalizer
from ..pricing.default import DefaultQuoteGenerator as _DefaultQuoteGenerator


class DefaultProjectParser(ProjectParser):
    """从解析器注册表选择合适的源解析器并解析输入。

    I/O：
      - 输入：文件系统路径 `input_path`（文件或目录）
      - 输出：描述已发现文件与元数据的 `ProjectDocument`
    """

    def __init__(self, registry: SourceParserRegistry | None = None) -> None:
        self.registry = registry or build_default_source_registry()

    def parse(self, input_path: str) -> ProjectDocument:
        path = Path(input_path)
        if path.is_file() or path.is_dir():
            return self.registry.parse(str(path))
        return ProjectDocument(project_name=path.stem, files=[str(path)])


class DefaultCabinetExtractor(CabinetExtractor):
    """提取机柜候选项；对于电子表格委托给 Excel 提取器。"""

    def extract(self, document: ProjectDocument) -> ProjectResult:
        if document.metadata.get("input_kind") == "excel":
            return ExcelCabinetAndBomExtractor().extract(document)

        result = ProjectResult(project=document)
        result.cabinets.append(CabinetRecord(cabinet_no="TBD-01", cabinet_type="unknown", remarks="placeholder"))
        return result


class DefaultMaterialNormalizer(MaterialNormalizer):
    """使用默认的归一化实现对物料字段进行规范化。"""

    def normalize(self, result: ProjectResult) -> ProjectResult:
        return _DefaultMaterialNormalizer().normalize(result)


class DefaultBomGenerator(BomGenerator):
    """生成 BOM 行；在无数据时提供占位项。"""

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
        return ExcelBomAggregator().generate(result)


class DefaultQuoteGenerator(QuoteGenerator):
    """将报价生成委托给定价模块。"""

    def generate(self, result: ProjectResult) -> ProjectResult:
        return _DefaultQuoteGenerator().generate(result)


class DefaultValidator(Validator):
    """执行默认的项目级验证检查。"""

    def validate(self, result: ProjectResult) -> ProjectResult:
        return DefaultProjectValidator().validate(result)


class DefaultExporter(Exporter):
    """通过电子表格导出器导出工件。"""

    def export(self, result: ProjectResult, output_dir: str) -> dict[str, str]:
        return ProjectExporter().export(result, output_dir)

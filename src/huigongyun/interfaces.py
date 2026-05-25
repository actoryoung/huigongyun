from __future__ import annotations

"""接口协议与传输对象定义。

本模块定义流水线各阶段使用的协议（Protocol）以及若干轻量数据传输类，
例如 `OCRBlock`、`ExtractedDocument`、`CaseHit` 和 `PipelineContext`。
这些抽象接口用于解耦不同实现（解析器、提取器、归一化器、生成器等）。
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .models import ProjectDocument, ProjectResult


@runtime_checkable
class ProjectParser(Protocol):
    def parse(self, input_path: str) -> ProjectDocument:
        """将项目输入路径解析为规范化的 `ProjectDocument`。

        范围：作为源文件、文件夹或未来源包的顶层入口。
        边界：不应执行业务规则、BOM 生成或定价等工作。
        """


@runtime_checkable
class SourceParser(Protocol):
    def supports(self, input_path: str) -> bool:
        """报告当前解析器是否能处理给定的输入路径。

        范围：仅做格式识别。
        边界：不要在此处解码业务规则或跨文档语义。
        """

    def parse(self, input_path: str) -> ProjectDocument:
        """将特定源格式解析为规范化的文档模型。

        范围：将单一格式转换为共享的 `ProjectDocument` 脚手架。
        边界：保留数据来源信息，但将 OCR、语义解析与机柜/BOM 推断留给下游阶段。
        """


@dataclass(slots=True)
class OCRBlock:
    text: str
    confidence: float | None = None
    bbox: tuple[float, float, float, float] | None = None
    page_no: int | None = None
    source_format: str | None = None


@dataclass(slots=True)
class ExtractedDocument:
    blocks: list[OCRBlock]
    metadata: dict[str, Any] | None = None


@runtime_checkable
class OCRTextExtractor(Protocol):
    def extract_text(self, input_path: str) -> ExtractedDocument:
        """从支持 OCR 的输入中提取文本和排版线索。

        范围：扫描 PDF、图像以及未来渲染的图纸页面。
        边界：仅返回原始文本块与坐标；不解释机柜语义、品牌或 BOM 规则。
        """


@runtime_checkable
class DocumentTextExtractor(Protocol):
    def extract_text(self, input_path: str) -> ExtractedDocument:
        """从 Office/PDF 文档中抽取文本与结构信息。

        范围：用于从 Word/PDF 中挖掘技术规格、约束与注释。
        边界：避免在此生成 BOM；保持提取出的条款与来源信息。
        """


@dataclass(slots=True)
class CaseHit:
    """检索到的历史案例命中（带评分）。

    这是一个轻量的传输对象，用于返回检索结果。`payload` 保持通用，
    以便未来实现能够携带案例元数据、来源引用或基于向量的证据而不改变 API。
    """

    case_id: str
    score: float
    summary: str | None = None
    payload: dict[str, Any] | None = None


@runtime_checkable
class HistoricalCaseRetriever(Protocol):
    """历史案例检索契约。

    边界：
      - 检索历史项目、机柜或报价记录。
      - 仅返回排序后的命中与可追溯的证据。

    未来可扩展点：BM25/关键词检索、向量检索/嵌入、以及带过滤谓词的混合检索。
    """

    def search(self, query: dict[str, Any], top_k: int = 5) -> list[CaseHit]:
        """检索与 BOM 或规则辅助相关的历史相似案例。"""


@runtime_checkable
class SimilarMaterialMatcher(Protocol):
    """物料相似度匹配契约（用于物料归一化）。

    边界：
      - 将一个物料候选与候选物料库进行比较。
      - 返回相似度分数或排序候选，不负责合并记录。

    未来实现可使用 RapidFuzz、基于嵌入的语义匹配或品牌/规格消歧规则。
    """

    def match(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        """对两个物料表示返回相似度分数。"""


@runtime_checkable
class CabinetExtractor(Protocol):
    def extract(self, document: ProjectDocument) -> ProjectResult:
        """从解析后的 `ProjectDocument` 中提取机柜候选记录。

        范围：产生机柜级记录并保留可追溯性信息。
        边界：不执行定价、UI 逻辑或直接调用外部 API。
        """


@runtime_checkable
class MaterialNormalizer(Protocol):
    def normalize(self, result: ProjectResult) -> ProjectResult:
        """对物料名称、规格和品牌进行归一化。

        范围：确定性清洗、别名映射与规范化。
        边界：保持业务规则的明确与可解释性。
        """


@runtime_checkable
class BomGenerator(Protocol):
    def generate(self, result: ProjectResult) -> ProjectResult:
        """生成机柜级与项目级的 BOM 行。

        范围：确定性地组装与聚合 BOM。
        边界：不负责定价与不产生校验副作用。
        """


@runtime_checkable
class QuoteGenerator(Protocol):
    def generate(self, result: ProjectResult) -> ProjectResult:
        """根据 BOM 与价格信息生成报价行与汇总。

        范围：价格查找与小计聚合。
        边界：避免解析源文件或修改提取阶段的数据。
        """


@runtime_checkable
class Validator(Protocol):
    def validate(self, result: ProjectResult) -> ProjectResult:
        """验证 BOM 的完整性与一致性。

        范围：规则检查、警告与可追溯的问题报告。
        边界：仅做验证；不应在无提示的情况下修改源数据。
        """


@runtime_checkable
class Exporter(Protocol):
    def export(self, result: ProjectResult, output_dir: str) -> dict[str, str]:
        """导出结果工件并返回生成的路径映射。

        范围：JSON、Excel 及未来的报告工件。
        边界：仅做序列化，不进行业务推断。
        """


@dataclass(slots=True)
class PipelineContext:
    input_path: str
    output_dir: str

"""流水线编排：组合各处理阶段并执行端到端流程。

`Pipeline` 将解析器、提取器、归一化器、BOM 生成器、报价生成器、
验证器与导出器串联起来。`run(context)` 按顺序执行这些阶段并返回
`ProjectResult`。

I/O 约定（Pipeline.run）：
    - 参数：`context`（PipelineContext），包含 `input_path` 和 `output_dir`。
    - 返回：包含聚合输出与工件的 `ProjectResult`。
    - 副作用：导出器会将工件写入到 `context.output_dir`。
"""

from __future__ import annotations

from dataclasses import dataclass

from .interfaces import (
    BomGenerator,
    CabinetExtractor,
    Exporter,
    HistoricalCaseRetriever,
    MaterialNormalizer,
    PipelineContext,
    ProjectParser,
    QuoteGenerator,
    SimilarMaterialMatcher,
    Validator,
)
from .models import ProjectResult


@dataclass(slots=True)
class Pipeline:
    parser: ProjectParser
    extractor: CabinetExtractor
    normalizer: MaterialNormalizer
    bom_generator: BomGenerator
    quote_generator: QuoteGenerator
    validator: Validator
    exporter: Exporter
    retriever: HistoricalCaseRetriever | None = None
    matcher: SimilarMaterialMatcher | None = None

    def run(self, context: PipelineContext) -> ProjectResult:
        """顺序执行流水线各阶段。

        参数：
            context: 包含 `input_path` 与 `output_dir` 的 `PipelineContext`。

        返回：
            由导出器填充 `outputs` 的 `ProjectResult`。
        """
        document = self.parser.parse(context.input_path)
        result = self.extractor.extract(document)
        result = self.normalizer.normalize(result)
        result = self.bom_generator.generate(result)

        # 可选：在生成报价前执行历史检索，为上下文提供相似案例
        if self.retriever is not None:
            from dataclasses import asdict
            query = {"project_name": result.project.project_name}
            similar = self.retriever.search(query, top_k=3)
            result.project.metadata["similar_cases"] = [
                asdict(h) for h in similar
            ]

        result = self.quote_generator.generate(result)
        result = self.validator.validate(result)
        result.outputs = self.exporter.export(result, context.output_dir)
        return result

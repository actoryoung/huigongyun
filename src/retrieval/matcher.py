"""物料相似度匹配器 — 基于嵌入向量的 SimilarMaterialMatcher 实现。

提供 ``EmbeddingMaterialMatcher``，将两个物料表示编码为嵌入向量后
计算余弦相似度（因嵌入已 L2 归一化，等价于内积）。

用法::

    from src.retrieval.matcher import EmbeddingMaterialMatcher
    from src.retrieval import SentenceTransformerProvider

    provider = SentenceTransformerProvider()
    matcher = EmbeddingMaterialMatcher(provider)

    left = {"name": "断路器", "spec": "NSX250", "brand": "施耐德"}
    right = {"name": "塑壳断路器", "spec": "NSX250", "brand": "Schneider"}
    score = matcher.match(left, right)
"""

from __future__ import annotations

from ..interfaces import SimilarMaterialMatcher
from .embeddings import EmbeddingProvider


class EmbeddingMaterialMatcher(SimilarMaterialMatcher):
    """基于嵌入向量的物料相似度匹配器。

    将两个物料字典拼接为文本后编码，返回余弦相似度分数（范围 [0, 1]）。

    拼接逻辑与 ``CaseIndexer._build_text()`` 保持一致：
    ``<name> <spec> <brand>``。

    Args:
        embedding_provider: 嵌入提供者实例（如 ``SentenceTransformerProvider``）。
    """

    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self._provider = embedding_provider

    def match(self, left: dict[str, str], right: dict[str, str]) -> float:
        """对两个物料表示返回相似度分数。

        ``left`` 和 ``right`` 字典应包含以下键（均为可选）：
            - ``name`` / ``material_name`` / ``normalized_name``: 物料名称
            - ``spec`` / ``normalized_spec``: 规格
            - ``brand`` / ``normalized_brand``: 品牌

        Returns:
            浮点数分数，范围 [0, 1]，1 表示完全相同。
        """
        text_left = self._build_text(left)
        text_right = self._build_text(right)

        if not text_left or not text_right:
            return 0.0

        vec_left = self._provider.embed(text_left)
        vec_right = self._provider.embed(text_right)

        # 嵌入已 L2 归一化，内积 = 余弦相似度
        similarity = sum(a * b for a, b in zip(vec_left, vec_right))
        # 裁剪到 [0, 1] 以应对浮点误差
        return max(0.0, min(1.0, float(similarity)))

    def _build_text(self, material: dict[str, str]) -> str:
        """从物料字典构建拼接文本。

        字段优先级：
            - name: ``normalized_name`` > ``name`` > ``material_name`` > ""
            - spec: ``normalized_spec`` > ``spec`` > ""
            - brand: ``normalized_brand`` > ``brand`` > ""
        """
        name = (
            material.get("normalized_name")
            or material.get("name")
            or material.get("material_name")
            or ""
        )
        spec = material.get("normalized_spec") or material.get("spec") or ""
        brand = material.get("normalized_brand") or material.get("brand") or ""

        parts = [name, spec, brand]
        return " ".join(p for p in parts if p).strip()

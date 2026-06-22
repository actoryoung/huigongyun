"""检索与相似度接口导出。

该包重新导出历史检索与物料相似度匹配的接口契约，便于后续实现
（关键词/向量/混合检索）插拔而不改变公共 API。
"""

from ..interfaces import CaseHit, HistoricalCaseRetriever, SimilarMaterialMatcher

__all__ = ["CaseHit", "HistoricalCaseRetriever", "SimilarMaterialMatcher"]
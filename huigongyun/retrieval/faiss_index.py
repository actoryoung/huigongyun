"""基于 FAISS 的历史案例检索实现。

提供 ``FaissCaseRetriever`` — ``HistoricalCaseRetriever`` 协议的第一个具体实现。
使用 FAISS IndexFlatIP（内积 = 归一化嵌入的余弦相似度）进行向量搜索。

依赖：
    ``pip install faiss-cpu``

若 faiss 或 embedding provider 不可用，``is_available`` 属性返回 False。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..interfaces import CaseHit, HistoricalCaseRetriever
from .embeddings import EmbeddingProvider
from .models import IndexedCase


class FaissCaseRetriever(HistoricalCaseRetriever):
    """基于 FAISS 索引和向量嵌入的历史案例检索器。

    内部维护：
      - ``_index``: FAISS IndexFlatIP 实例
      - ``_case_lookup``: {faiss_id: IndexedCase} 映射
      - ``_embedding_provider``: EmbeddingProvider（如 SentenceTransformer）

    用法::

        retriever = FaissCaseRetriever(provider)
        retriever.index_cases(indexed_cases)
        results = retriever.search({"material_name": "断路器"}, top_k=5)
    """

    def __init__(self, embedding_provider: EmbeddingProvider):
        """初始化检索器。

        Args:
            embedding_provider: 将文本转换为嵌入向量的提供者。
        """
        self._provider = embedding_provider
        self._dimension = embedding_provider.dimension
        self._index = None
        self._case_lookup: dict[int, IndexedCase] = {}
        self._next_id = 0

        # 尝试初始化 FAISS 索引
        try:
            import faiss  # noqa: F811
            self._faiss = faiss
            self._index = faiss.IndexFlatIP(self._dimension)
        except ImportError:
            self._faiss = None
            self._index = None

    @property
    def is_available(self) -> bool:
        """若 FAISS 和 embedding provider 均就绪则返回 True。"""
        return self._faiss is not None and self._index is not None

    @property
    def case_count(self) -> int:
        """当前索引中的案例数。"""
        return len(self._case_lookup)

    def index_cases(self, cases: list[IndexedCase]) -> None:
        """构建/重建 FAISS 索引。

        为每个案例生成嵌入并将其添加到 FAISS 索引。
        案例按添加顺序分配内部 ID。

        Args:
            cases: 要索引的 IndexedCase 对象列表。
        """
        if not self.is_available:
            return
        if not cases:
            return

        texts = [c.text for c in cases]
        embeddings = self._provider.embed_batch(texts)

        import numpy as np
        vectors = np.array(embeddings, dtype=np.float32)

        # 如果之前有案例则重建索引（FAISS 简单索引不支持增量删除）
        if self._case_lookup:
            self._index = self._faiss.IndexFlatIP(self._dimension)

        self._case_lookup.clear()
        self._next_id = 0

        for i, case in enumerate(cases):
            self._case_lookup[i] = case

        self._index.add(vectors)

    def search(self, query: dict[str, Any], top_k: int = 5) -> list[CaseHit]:
        """在已索引的案例中搜索。

        将查询字典拼接为文本进行嵌入，然后执行 FAISS 最近邻搜索。

        Args:
            query: 用于搜索的字段字典。
                  常见的键包括 ``material_name``、``cabinet_no``、``spec``、``brand``。
            top_k: 返回结果的最大数量。

        Returns:
            按分数降序排列的 ``CaseHit`` 对象列表。若未初始化则返回空列表。
        """
        if not self.is_available or not self._case_lookup:
            return []

        # 构建查询文本
        query_parts = [
            str(query.get("material_name", "")),
            str(query.get("cabinet_no", "")),
            str(query.get("spec", "")),
            str(query.get("brand", "")),
            str(query.get("project_name", "")),
        ]
        query_text = " ".join(p for p in query_parts if p).strip()
        if not query_text:
            return []

        query_vec = self._provider.embed(query_text)

        import numpy as np
        q = np.array([query_vec], dtype=np.float32)
        scores, indices = self._index.search(q, min(top_k, len(self._case_lookup)))

        results: list[CaseHit] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx not in self._case_lookup:
                continue
            case = self._case_lookup[idx]
            results.append(CaseHit(
                case_id=case.case_id,
                score=float(score),
                summary=f"{case.project_name} / {case.cabinet_no or 'N/A'}: "
                        f"{case.payload.get('material_name', '')}",
                payload=dict(case.payload),
            ))

        return results

    def save(self, path: str) -> None:
        """将 FAISS 索引和 case_lookup 持久化到磁盘。

        写入两个文件：
          - ``{path}.faiss``: FAISS 索引二进制文件
          - ``{path}.json``: JSON 格式的 case_lookup + 元数据

        Args:
            path: 输出路径（文件前缀，不含扩展名）。
        """
        if not self.is_available:
            return

        index_path = f"{path}.faiss"
        meta_path = f"{path}.json"

        # 保存 FAISS 索引
        self._faiss.write_index(self._index, index_path)

        # 保存案例查找表
        lookup_data = {
            "dimension": self._dimension,
            "case_count": len(self._case_lookup),
            "cases": {
                str(idx): {
                    "case_id": case.case_id,
                    "text": case.text,
                    "payload": case.payload,
                    "project_name": case.project_name,
                    "cabinet_no": case.cabinet_no,
                }
                for idx, case in self._case_lookup.items()
            },
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(lookup_data, f, ensure_ascii=False, indent=2)

    def load(self, path: str) -> None:
        """从磁盘加载 FAISS 索引和 case_lookup。

        Args:
            path: 输入路径（文件前缀，不含扩展名）。
        """
        if not self.is_available:
            return

        index_path = f"{path}.faiss"
        meta_path = f"{path}.json"

        if not os.path.exists(index_path) or not os.path.exists(meta_path):
            raise FileNotFoundError(f"索引文件未找到: {path}.faiss / {path}.json")

        self._index = self._faiss.read_index(index_path)

        with open(meta_path, "r", encoding="utf-8") as f:
            lookup_data = json.load(f)

        self._case_lookup.clear()
        for idx_str, case_data in lookup_data["cases"].items():
            idx = int(idx_str)
            self._case_lookup[idx] = IndexedCase(
                case_id=case_data["case_id"],
                text=case_data["text"],
                payload=case_data["payload"],
                project_name=case_data["project_name"],
                cabinet_no=case_data.get("cabinet_no"),
            )
        self._next_id = max(self._case_lookup.keys()) + 1 if self._case_lookup else 0

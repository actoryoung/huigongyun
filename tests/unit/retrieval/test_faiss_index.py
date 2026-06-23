"""FaissCaseRetriever 和 EmbeddingProvider 单元测试。

使用 FakeEmbeddingProvider 进行确定性测试，不依赖真实的
sentence-transformers 模型。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from huigongyun.retrieval.embeddings import EmbeddingProvider
from huigongyun.retrieval.faiss_index import FaissCaseRetriever
from huigongyun.retrieval.indexer import CaseIndexer
from huigongyun.retrieval.models import IndexedCase
from huigongyun.models import (
    BomLine,
    CabinetRecord,
    MaterialRecord,
    ProjectDocument,
    ProjectResult,
)


class FakeEmbeddingProvider(EmbeddingProvider):
    """为测试提供确定性的嵌入。

    将输入文本映射到固定维度（16 维）的单位向量，使用文本长度
    和字符码位构造出可重复的嵌入。这样避免了运行真实 ML 模型。
    """

    def __init__(self, dim: int = 16):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for i, ch in enumerate(text):
            vec[i % self._dim] += ord(ch) * 0.001
        # 做简单的 L2 归一化
        norm = max(sum(v * v for v in vec) ** 0.5, 1e-8)
        return [v / norm for v in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def _make_case(case_id: str, text: str, **kwargs) -> IndexedCase:
    return IndexedCase(case_id=case_id, text=text, project_name="test", **kwargs)


# ── FAISS 可用性检查 ────────────────────────────────────────────

def _faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
        return True
    except ImportError:
        return False


FAISS_SKIP_REASON = "faiss-cpu 未安装"


@pytest.mark.skipif(not _faiss_available(), reason=FAISS_SKIP_REASON)
class TestFaissCaseRetriever:
    """测试 FAISS 检索器的 CRUD 操作。"""

    def test_initial_state(self):
        provider = FakeEmbeddingProvider(16)
        retriever = FaissCaseRetriever(provider)
        assert retriever.is_available
        assert retriever.case_count == 0

    def test_index_and_search(self):
        provider = FakeEmbeddingProvider(16)
        retriever = FaissCaseRetriever(provider)

        cases = [
            _make_case("a", "断路器 MCCB-250A 施耐德",
                       payload={"material_name": "断路器", "spec": "MCCB-250A"}),
            _make_case("b", "接触器 LC1D-32 西门子",
                       payload={"material_name": "接触器", "spec": "LC1D-32"}),
            _make_case("c", "电缆 YJV-4x25 国产",
                       payload={"material_name": "电缆", "spec": "YJV-4x25"}),
        ]
        retriever.index_cases(cases)
        assert retriever.case_count == 3

        # 搜索断路器 — 应返回结果，且 case "a" 排第一
        results = retriever.search({"material_name": "断路器"}, top_k=2)
        assert len(results) == 2
        assert results[0].case_id == "a"
        assert results[0].score > 0

    def test_empty_index_returns_empty(self):
        provider = FakeEmbeddingProvider(16)
        retriever = FaissCaseRetriever(provider)
        results = retriever.search({"material_name": "测试"}, top_k=5)
        assert results == []

    def test_save_and_load(self):
        provider = FakeEmbeddingProvider(16)
        retriever = FaissCaseRetriever(provider)
        cases = [_make_case("x", "测试物料 规格A 品牌B",
                            payload={"material_name": "测试物料"})]
        retriever.index_cases(cases)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_index")
            retriever.save(path)

            # 检查文件存在
            assert os.path.exists(f"{path}.faiss")
            assert os.path.exists(f"{path}.json")

            # 重新加载
            retriever2 = FaissCaseRetriever(provider)
            retriever2.load(path)
            assert retriever2.case_count == 1

            results = retriever2.search({"material_name": "测试物料"}, top_k=1)
            assert len(results) == 1
            assert results[0].case_id == "x"

    def test_reindex_replaces_previous(self):
        provider = FakeEmbeddingProvider(16)
        retriever = FaissCaseRetriever(provider)

        # 先索引两个案例
        retriever.index_cases([
            _make_case("old1", "旧物料A"),
            _make_case("old2", "旧物料B"),
        ])
        assert retriever.case_count == 2

        # 再重新索引一个新案例
        retriever.index_cases([_make_case("new1", "新物料")])
        assert retriever.case_count == 1
        results = retriever.search({"material_name": "新物料"}, top_k=5)
        assert results[0].case_id == "new1"


@pytest.mark.skipif(not _faiss_available(), reason=FAISS_SKIP_REASON)
class TestFaissCaseRetrieverEdgeCases:
    """边界情况测试。"""

    def test_search_empty_query_text(self):
        provider = FakeEmbeddingProvider(16)
        retriever = FaissCaseRetriever(provider)
        retriever.index_cases([_make_case("a", "断路器")])
        results = retriever.search({}, top_k=5)
        assert results == []

    def test_search_top_k_larger_than_index(self):
        provider = FakeEmbeddingProvider(16)
        retriever = FaissCaseRetriever(provider)
        retriever.index_cases([_make_case("a", "单一案例")])
        results = retriever.search({"material_name": "单一"}, top_k=10)
        assert len(results) == 1  # capped

    def test_index_empty_list(self):
        provider = FakeEmbeddingProvider(16)
        retriever = FaissCaseRetriever(provider)
        retriever.index_cases([])
        assert retriever.case_count == 0


class TestCaseIndexer:
    """CaseIndexer 单元测试（不依赖 FAISS）。"""

    def test_index_project_creates_bom_cases(self):
        result = ProjectResult(
            project=ProjectDocument(project_name="demo"),
            bom_lines=[
                BomLine(
                    cabinet_no="K1",
                    material=MaterialRecord(
                        name="断路器", spec="MCCB-250A", brand="施耐德",
                        normalized_name="断路器", normalized_spec="MCCB-250A",
                    ),
                ),
            ],
        )

        indexer = CaseIndexer()
        cases = indexer.index_project(result)

        assert len(cases) == 1
        assert cases[0].project_name == "demo"
        assert cases[0].cabinet_no == "K1"
        assert "断路器" in cases[0].text
        assert cases[0].payload["material_name"] == "断路器"

    def test_index_project_includes_summary(self):
        result = ProjectResult(
            project=ProjectDocument(project_name="demo"),
            summary=[
                MaterialRecord(
                    name="断路器", spec="MCCB-250A", brand="施耐德",
                    normalized_name="断路器",
                    quantity=10, unit_price=500.0,
                ),
            ],
        )

        indexer = CaseIndexer()
        cases = indexer.index_project(result)

        assert len(cases) == 1
        assert cases[0].payload["quantity"] == 10
        assert cases[0].payload["unit_price"] == 500.0

    def test_index_project_with_both_bom_and_summary(self):
        result = ProjectResult(
            project=ProjectDocument(project_name="demo"),
            bom_lines=[
                BomLine(
                    cabinet_no="K1",
                    material=MaterialRecord(name="A", quantity=1),
                ),
                BomLine(
                    cabinet_no="K2",
                    material=MaterialRecord(name="B", quantity=2),
                ),
            ],
            summary=[
                MaterialRecord(name="A", quantity=3),
                MaterialRecord(name="B", quantity=2),
            ],
        )

        indexer = CaseIndexer()
        cases = indexer.index_project(result)

        # 2 BOM cases + 2 summary cases
        assert len(cases) == 4

    def test_custom_project_name_override(self):
        result = ProjectResult(
            project=ProjectDocument(project_name="original"),
            bom_lines=[
                BomLine(cabinet_no="K1", material=MaterialRecord(name="A")),
            ],
        )

        indexer = CaseIndexer()
        cases = indexer.index_project(result, project_name="custom_name")

        assert cases[0].project_name == "custom_name"

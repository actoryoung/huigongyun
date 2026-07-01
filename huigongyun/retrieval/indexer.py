"""案例索引器 — 将 ``ProjectResult`` 转换为 FAISS 可索引的 ``IndexedCase`` 对象。

为每个物料创建案例，将（物料名 + 规格 + 品牌 + 柜型）拼接为可嵌入的文本。
"""

from __future__ import annotations

from ..models import ProjectResult
from .models import IndexedCase


class CaseIndexer:
    """将管道结果转换为可检索的案例文档。

    用法::

        indexer = CaseIndexer()
        cases = indexer.index_project(result)
        retriever.index_cases(cases)
    """

    def index_project(self, result: ProjectResult, project_name: str = "") -> list[IndexedCase]:
        """将一个 ``ProjectResult`` 转换为扁平化的 ``IndexedCase`` 列表。

        每个 BOM 行生成一个案例。每个汇总物料行也生成一个案例。
        每一个都包含拼接后的文本和包含完整物料数据的 payload。

        Args:
            result: 管道结果。
            project_name: 覆盖项目名称（可选，默认取自 result.project.project_name）。

        Returns:
            IndexedCase 对象列表。
        """
        if not project_name:
            project_name = result.project.project_name

        cases: list[IndexedCase] = []
        case_idx = 0

        # 从 BOM 行创建案例（最细粒度）
        for bom_line in result.bom_lines:
            m = bom_line.material
            text = self._build_text(
                material_name=m.normalized_name or m.name,
                spec=m.normalized_spec or m.spec or "",
                brand=m.brand or "",
                cabinet_no=bom_line.cabinet_no,
            )
            cases.append(IndexedCase(
                case_id=f"{project_name}_bom_{case_idx}",
                text=text,
                payload={
                    "material_name": m.normalized_name or m.name,
                    "spec": m.normalized_spec or m.spec,
                    "brand": m.brand,
                    "manufacturer": m.manufacturer,
                    "unit": m.unit,
                    "quantity": m.quantity,
                    "cabinet_no": bom_line.cabinet_no,
                    "unit_price": m.unit_price,
                    "price_source": m.price_source,
                    "long_lead_time": m.long_lead_time,
                },
                project_name=project_name,
                cabinet_no=bom_line.cabinet_no,
            ))
            case_idx += 1

        # 从汇总物料创建案例
        for material in result.summary:
            text = self._build_text(
                material_name=material.normalized_name or material.name,
                spec=material.normalized_spec or material.spec or "",
                brand=material.brand or "",
                cabinet_no="",
            )
            cases.append(IndexedCase(
                case_id=f"{project_name}_summary_{case_idx}",
                text=text,
                payload={
                    "material_name": material.normalized_name or material.name,
                    "spec": material.normalized_spec or material.spec,
                    "brand": material.brand,
                    "manufacturer": material.manufacturer,
                    "unit": material.unit,
                    "quantity": material.quantity,
                    "unit_price": material.unit_price,
                    "price_source": material.price_source,
                    "long_lead_time": material.long_lead_time,
                },
                project_name=project_name,
            ))
            case_idx += 1

        return cases

    def _build_text(
        self,
        material_name: str,
        spec: str,
        brand: str,
        cabinet_no: str = "",
    ) -> str:
        """将物料字段拼接为嵌入文本。"""
        parts = [material_name, spec, brand]
        if cabinet_no:
            parts.append(cabinet_no)
        return " ".join(p for p in parts if p).strip()

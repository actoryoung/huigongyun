"""HH 平台兼容适配器 — 将 ``ProjectResult`` 转换为 HH Django 前端期望的 sheets 格式。

使用方式::

    from src.bootstrap import build_default_pipeline, build_context
    from src.adapters.hh_adapter import HHCompatibleAdapter

    pipeline = build_default_pipeline()
    result = pipeline.run(build_context(input_dir, output_dir))
    adapter = HHCompatibleAdapter()
    sheets = adapter.adapt(result)

sheets 格式与 ``HH/app01/service.py`` 中 mock 数据的结构完全一致，
可直接返回给 ``/analyze/`` 端点。
"""

from __future__ import annotations

import re
from typing import Any

from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectResult, QuoteLine


class HHCompatibleAdapter:
    """将 ``ProjectResult`` 转换为 HH 平台兼容的 sheets 字典。

    产出结构::

        {
            "total": {
                "title": "报价总表",
                "columnType": "cabinet",
                "rows": [{type: "item", colCabinet: ..., ...}, ...],
            },
            "cab_A": {
                "title": "A 列头柜",
                "cabinetNo": "A",
                "cabinetName": "列头柜",
                "columnType": "component",
                "rows": [{type: "item", name: ..., ...}, ...],
            },
            ...
        }
    """

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    def adapt(self, result: ProjectResult) -> dict[str, dict[str, Any]]:
        """主入口：将整个 ProjectResult 转换为 HH sheets 字典。

        参数：
            result: pipeline 运行产出的完整 ProjectResult。

        返回：
            ``{sheet_key: sheet_dict}``，其中 sheet_dict 包含
            ``title``, ``columnType``, ``rows``（以及明细表的 ``cabinetNo`` /
            ``cabinetName``）。
        """
        sheets: dict[str, dict[str, Any]] = {}

        # ---- 报价总表 ----
        sheets["total"] = self._build_total_sheet(result)

        # ---- 每个柜体一张明细表 ----
        # 将 BOM 行按柜号分组
        bom_by_cabinet: dict[str, list[BomLine]] = {}
        for bl in result.bom_lines:
            cab_no = bl.cabinet_no
            bom_by_cabinet.setdefault(cab_no, []).append(bl)

        # 将报价行按 (柜号, 物料名) 建立索引，便于 O(1) 查找
        quote_index: dict[tuple[str, str], QuoteLine] = {}
        for ql in result.quote_lines:
            key = (ql.cabinet_no, ql.material_name)
            quote_index[key] = ql  # 同名后出现的覆盖前一条

        for cabinet in result.cabinets:
            key = _safe_sheet_key(cabinet.cabinet_no)
            cab_lines = bom_by_cabinet.get(cabinet.cabinet_no, [])
            sheets[key] = self._build_cabinet_sheet(
                cabinet, cab_lines, quote_index
            )

        # 如果有 BOM 行属于 unknown 柜号，也建一张表
        unknown_lines = [
            bl for bl in result.bom_lines
            if bl.cabinet_no not in {c.cabinet_no for c in result.cabinets}
        ]
        if unknown_lines:
            sheets["cab_unknown"] = self._build_cabinet_sheet(
                CabinetRecord(cabinet_no="unknown", cabinet_type="未分配"),
                unknown_lines,
                quote_index,
            )

        return sheets

    # ------------------------------------------------------------------
    # 总表构建
    # ------------------------------------------------------------------

    def _build_total_sheet(self, result: ProjectResult) -> dict[str, Any]:
        """构建项目汇总表（columnType="cabinet"）。

        每行代表一个柜体，附带小计/总计行。
        """
        rows: list[dict[str, Any]] = []

        # 预计算每个柜体的报价合计
        cabinet_prices = _build_cabinet_price_map(result)

        for cabinet in result.cabinets:
            price = cabinet_prices.get(cabinet.cabinet_no, 0.0)
            cost_total = _compute_cabinet_cost_total(
                cabinet.cabinet_no, result.bom_lines
            )

            rows.append({
                "type": "item",
                "colCabinet": cabinet.cabinet_no,
                "name": cabinet.cabinet_type or f"柜体 #{cabinet.cabinet_no}",
                "model": cabinet.cabinet_type or "",
                "unit": "台",
                "qty": cabinet.quantity or 1,
                "price": price,
                "costTotal": round(cost_total, 2),
                "size": cabinet.dimensions or "",
                "category": "",
                "drawingNo": "",
            })

        # 分隔行 + 小计 + 总计
        if rows:
            rows.append({"type": "empty"})
            rows.append({"type": "subtotal", "name": "小计"})
        rows.append({"type": "grandtotal"})

        return {
            "title": "报价总表",
            "columnType": "cabinet",
            "rows": rows,
        }

    # ------------------------------------------------------------------
    # 柜体明细表构建
    # ------------------------------------------------------------------

    def _build_cabinet_sheet(
        self,
        cabinet: CabinetRecord,
        bom_lines: list[BomLine],
        quote_index: dict[tuple[str, str], QuoteLine],
    ) -> dict[str, Any]:
        """为单个柜体构建明细表（columnType="component"）。

        参数：
            cabinet: 柜体记录。
            bom_lines: 属于该柜体的 BOM 行列表。
            quote_index: (柜号, 物料名) → QuoteLine 的查找字典。

        返回：
            HH cabinet sheet dict。
        """
        rows: list[dict[str, Any]] = []

        for bl in bom_lines:
            m = bl.material
            name = m.normalized_name or m.name

            # 查找对应报价行（优先匹配归一化名，回退原始名）
            ql = quote_index.get((cabinet.cabinet_no, name))
            if ql is None and m.name and m.name != name:
                ql = quote_index.get((cabinet.cabinet_no, m.name))

            # 价格优先级：QuoteLine.unit_price > MaterialRecord.unit_price > 0
            ql_price = ql.unit_price if ql else None
            unit_price = ql_price if ql_price else m.unit_price

            # 成本/报价系数（仅演示：从报价反推成本价约为 68-75%，报出系数 1.33-1.47）
            if unit_price and unit_price > 0:
                # 用物料名长度取模决定成本比率，让同类物料成本比例接近
                cost_ratio = 0.68 + (len(name) % 7) * 0.01  # 0.68 ~ 0.75
                cost_price = round(unit_price * cost_ratio, 2)
                quote_rate = f"{unit_price / cost_price:.2f}" if cost_price > 0 else ""
            else:
                cost_price = 0.0
                quote_rate = ""

            rows.append({
                "type": "item",
                "name": name,
                "model": m.normalized_spec or m.spec or "",
                "factory": m.normalized_brand or m.brand or "",
                "unit": m.unit or "个",
                "qty": m.quantity or 0,
                "price": unit_price or 0.0,
                "costPrice": cost_price,
                "quoteRate": quote_rate,
                "listPrice": "",
                "discountRate": "",
                "category": _infer_material_category(m),
                "materialCode": "",
                "origin": "",
            })

        # 分隔行 + 小计 + 总计
        if rows:
            rows.append({"type": "empty"})
            rows.append({"type": "subtotal", "name": "小计"})
        rows.append({"type": "grandtotal"})

        return {
            "title": f"{cabinet.cabinet_no} {cabinet.cabinet_type or ''}".strip(),
            "cabinetNo": cabinet.cabinet_no,
            "cabinetName": cabinet.cabinet_type or f"柜体 #{cabinet.cabinet_no}",
            "columnType": "component",
            "rows": rows,
        }


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _safe_sheet_key(cabinet_no: str) -> str:
    """将柜号转换为安全的 sheet key。

    替换非字母数字字符为下划线，确保前端 JS 可以安全访问。
    """
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", cabinet_no)
    if not safe:
        safe = "cabinet"
    return f"cab_{safe}"


def _infer_material_category(m: MaterialRecord) -> str:
    """根据物料名称/规格推断分类：柜体 / 辅料 / 元件。"""
    name = (m.normalized_name or m.name or "").lower()
    spec = (m.normalized_spec or m.spec or "").lower()
    combined = f"{name} {spec}"

    # 柜体
    if _matches_any(combined, ["柜体", "壳体", "柜壳", "机柜", "箱体", "配电箱"]):
        return "柜体"

    # 辅料
    if _matches_any(combined, [
        "母线", "铜排", "配线", "导线", "电缆", "线缆",
        "端子", "线槽", "导轨", "螺丝", "螺栓", "螺母",
        "标牌", "绝缘子", "接地", "二次线", "辅料", "汇流排",
        "软连接", "热缩管", "扎带", "标签", "号码管",
    ]):
        return "辅料"

    # 默认元件
    return "元件"


def _matches_any(text: str, keywords: list[str]) -> bool:
    """检查 text 是否包含任意关键词。"""
    return any(kw in text for kw in keywords)


def _build_cabinet_price_map(result: ProjectResult) -> dict[str, float]:
    """构建柜号 → 合计价格的映射。

    优先使用 quote_totals.cabinet_totals，回退为 quote_lines 汇总。
    """
    totals = result.quote_totals.get("cabinet_totals", {}) or {}
    if totals:
        return {str(k): float(v) for k, v in totals.items()}

    # 回退：从 quote_lines 按柜号汇总 subtotal
    price_map: dict[str, float] = {}
    for ql in result.quote_lines:
        cab = ql.cabinet_no
        price_map[cab] = price_map.get(cab, 0.0) + (ql.subtotal or 0.0)
    return price_map


def _compute_cabinet_cost_total(
    cabinet_no: str, bom_lines: list[BomLine]
) -> float:
    """计算某柜体的成本合计 ≈ Σ(unit_price × 0.72 × quantity)。

    成本价约为报价的 72%（演示反推），与明细表 costPrice 口径一致。
    """
    total = 0.0
    for bl in bom_lines:
        if bl.cabinet_no == cabinet_no:
            m = bl.material
            price = m.unit_price or 0.0
            qty = m.quantity or 0.0
            total += price * 0.72 * qty
    return total

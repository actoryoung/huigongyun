"""HH adapter 单元测试 — 验证 ProjectResult → HH sheets 格式转换。"""

from __future__ import annotations

import pytest

from src.adapters.hh_adapter import (
    HHCompatibleAdapter,
    _infer_material_category,
    _safe_sheet_key,
)
from src.models import (
    BomLine,
    CabinetRecord,
    MaterialRecord,
    ProjectDocument,
    ProjectResult,
    QuoteLine,
    SourceRef,
)


# ---------------------------------------------------------------------------
# 工厂辅助
# ---------------------------------------------------------------------------

def _make_material(
    name: str = "塑壳断路器",
    spec: str = "NSX250F 3P 250A",
    brand: str = "施耐德",
    unit: str = "只",
    qty: float = 6.0,
    norm_name: str | None = None,
    norm_spec: str | None = None,
    norm_brand: str | None = None,
    unit_price: float | None = 1280.0,
) -> MaterialRecord:
    return MaterialRecord(
        name=name,
        spec=spec,
        unit=unit,
        quantity=qty,
        brand=brand,
        normalized_name=norm_name or name,
        normalized_spec=norm_spec or spec,
        normalized_brand=norm_brand or brand,
        unit_price=unit_price,
        subtotal=(unit_price or 0.0) * qty,
    )


def _make_cabinet(
    no: str = "A",
    ctype: str = "Prisma",
    dims: str | None = "800*300*1200*2200",
    qty: int = 4,
) -> CabinetRecord:
    return CabinetRecord(
        cabinet_no=no,
        cabinet_type=ctype,
        dimensions=dims,
        quantity=qty,
    )


def _make_result(
    cabinets: list[CabinetRecord] | None = None,
    bom_lines: list[BomLine] | None = None,
    quote_lines: list[QuoteLine] | None = None,
    quote_totals: dict | None = None,
) -> ProjectResult:
    return ProjectResult(
        project=ProjectDocument(project_name="测试项目"),
        cabinets=cabinets or [],
        bom_lines=bom_lines or [],
        quote_lines=quote_lines or [],
        quote_totals=quote_totals or {},
    )


# ---------------------------------------------------------------------------
# _safe_sheet_key
# ---------------------------------------------------------------------------

class TestSafeSheetKey:
    def test_plain_letter(self):
        assert _safe_sheet_key("A") == "cab_A"

    def test_with_hyphen(self):
        assert _safe_sheet_key("B-1") == "cab_B-1"

    def test_with_special_chars(self):
        assert _safe_sheet_key("A/B 测试") == "cab_A_B___"

    def test_empty_string(self):
        assert _safe_sheet_key("") == "cab_cabinet"

    def test_only_special_chars(self):
        assert _safe_sheet_key("!!!") == "cab____"


# ---------------------------------------------------------------------------
# _infer_material_category
# ---------------------------------------------------------------------------

class TestInferMaterialCategory:
    def test_cabinet_enclosure(self):
        m = _make_material(name="柜体壳体")
        assert _infer_material_category(m) == "柜体"

    def test_cabinet_enclosure_in_spec(self):
        m = _make_material(name="Prisma", spec="柜体")
        assert _infer_material_category(m) == "柜体"

    def test_auxiliary_busbar(self):
        m = _make_material(name="母线排")
        assert _infer_material_category(m) == "辅料"

    def test_auxiliary_wire(self):
        m = _make_material(name="二次配线")
        assert _infer_material_category(m) == "辅料"

    def test_auxiliary_terminal(self):
        m = _make_material(name="接线端子")
        assert _infer_material_category(m) == "辅料"

    def test_default_component(self):
        m = _make_material(name="塑壳断路器")
        assert _infer_material_category(m) == "元件"

    def test_empty_name(self):
        m = _make_material(name="", norm_name="")
        assert _infer_material_category(m) == "元件"


# ---------------------------------------------------------------------------
# HHCompatibleAdapter
# ---------------------------------------------------------------------------

class TestAdapterEmpty:
    """空结果边界情况。"""

    def test_empty_result(self):
        adapter = HHCompatibleAdapter()
        result = _make_result()
        sheets = adapter.adapt(result)
        assert "total" in sheets
        assert sheets["total"]["columnType"] == "cabinet"
        assert len(sheets["total"]["rows"]) == 1  # only grandtotal

    def test_no_cabinets_with_bom(self):
        """BOM 行存在但无匹配柜体 — 应归入 cab_unknown。"""
        m = _make_material()
        adapter = HHCompatibleAdapter()
        result = _make_result(
            bom_lines=[BomLine(cabinet_no="X99", material=m)],
        )
        sheets = adapter.adapt(result)
        assert "cab_unknown" in sheets
        assert sheets["cab_unknown"]["columnType"] == "component"
        assert len(sheets["cab_unknown"]["rows"]) > 0


class TestAdapterSingleCabinet:
    """单柜体映射。"""

    @pytest.fixture
    def adapter(self):
        return HHCompatibleAdapter()

    def test_total_sheet_structure(self, adapter):
        cab = _make_cabinet()
        result = _make_result(cabinets=[cab], quote_totals={
            "cabinet_totals": {"A": 87957.64},
        })
        sheets = adapter.adapt(result)
        total = sheets["total"]
        assert total["columnType"] == "cabinet"
        assert total["title"] == "报价总表"

        rows = total["rows"]
        assert rows[0]["type"] == "item"
        assert rows[0]["colCabinet"] == "A"
        assert rows[0]["name"] == "Prisma"
        assert rows[0]["qty"] == 4
        assert rows[0]["price"] == 87957.64
        assert rows[0]["unit"] == "台"

        # 确认分隔行 + 小计 + 总计
        types = [r["type"] for r in rows]
        assert "empty" in types
        assert "subtotal" in types
        assert "grandtotal" in types

    def test_cabinet_detail_sheet(self, adapter):
        cab = _make_cabinet()
        m = _make_material()
        ql = QuoteLine(
            cabinet_no="A",
            material_name="塑壳断路器",
            unit_price=1280.0,
            subtotal=7680.0,
        )
        result = _make_result(
            cabinets=[cab],
            bom_lines=[BomLine(cabinet_no="A", material=m)],
            quote_lines=[ql],
        )
        sheets = adapter.adapt(result)

        assert "cab_A" in sheets
        sheet = sheets["cab_A"]
        assert sheet["columnType"] == "component"
        assert sheet["cabinetNo"] == "A"
        assert sheet["cabinetName"] == "Prisma"

        rows = sheet["rows"]
        item_rows = [r for r in rows if r["type"] == "item"]
        assert len(item_rows) == 1
        row = item_rows[0]
        assert row["name"] == "塑壳断路器"
        assert row["model"] == "NSX250F 3P 250A"
        assert row["factory"] == "施耐德"
        assert row["unit"] == "只"
        assert row["qty"] == 6
        assert row["price"] == 1280.0

    def test_cabinet_type_fallback(self, adapter):
        """柜型为空时，name 回退为描述文本。"""
        cab = _make_cabinet(ctype=None)
        result = _make_result(cabinets=[cab])
        sheets = adapter.adapt(result)
        row = sheets["total"]["rows"][0]
        assert "柜体 #A" in row["name"]

    def test_dimensions_none(self, adapter):
        """尺寸为 None 时输出空字符串。"""
        cab = _make_cabinet(dims=None)
        result = _make_result(cabinets=[cab])
        sheets = adapter.adapt(result)
        assert sheets["total"]["rows"][0]["size"] == ""


class TestAdapterMultipleCabinets:
    """多柜体场景。"""

    def test_each_cabinet_gets_sheet(self):
        adapter = HHCompatibleAdapter()
        cabinets = [
            _make_cabinet(no="A", ctype="列头柜"),
            _make_cabinet(no="B", ctype="空调配电柜"),
            _make_cabinet(no="C", ctype="照明配电柜"),
        ]
        result = _make_result(cabinets=cabinets)
        sheets = adapter.adapt(result)

        for no in ["A", "B", "C"]:
            assert f"cab_{no}" in sheets
            assert sheets[f"cab_{no}"]["cabinetNo"] == no

        # total sheet 应有 3 个 item 行
        item_rows = [r for r in sheets["total"]["rows"] if r["type"] == "item"]
        assert len(item_rows) == 3

    def test_bom_routed_to_correct_cabinet(self):
        adapter = HHCompatibleAdapter()
        cabinets = [
            _make_cabinet(no="A", ctype="列头柜"),
            _make_cabinet(no="B", ctype="空调配电柜"),
        ]
        m_a = _make_material(name="塑壳断路器")
        m_b = _make_material(name="交流接触器", spec="LC1D95", brand="施耐德", qty=4.0)
        result = _make_result(
            cabinets=cabinets,
            bom_lines=[
                BomLine(cabinet_no="A", material=m_a),
                BomLine(cabinet_no="B", material=m_b),
            ],
        )

        sheets = adapter.adapt(result)
        a_items = [r for r in sheets["cab_A"]["rows"] if r["type"] == "item"]
        b_items = [r for r in sheets["cab_B"]["rows"] if r["type"] == "item"]

        assert len(a_items) == 1
        assert a_items[0]["name"] == "塑壳断路器"
        assert len(b_items) == 1
        assert b_items[0]["name"] == "交流接触器"


class TestAdapterPriceMapping:
    """价格相关映射。"""

    def test_price_from_quote_totals(self):
        adapter = HHCompatibleAdapter()
        cab = _make_cabinet()
        result = _make_result(
            cabinets=[cab],
            quote_totals={"cabinet_totals": {"A": 50000.0}},
        )
        sheets = adapter.adapt(result)
        assert sheets["total"]["rows"][0]["price"] == 50000.0

    def test_price_fallback_to_quote_lines(self):
        adapter = HHCompatibleAdapter()
        cab = _make_cabinet()
        ql = QuoteLine(cabinet_no="A", material_name="x", unit_price=1000.0, subtotal=5000.0)
        result = _make_result(
            cabinets=[cab],
            quote_lines=[ql],
            # no quote_totals → falls back
        )
        sheets = adapter.adapt(result)
        assert sheets["total"]["rows"][0]["price"] == 5000.0

    def test_price_zero_when_missing(self):
        adapter = HHCompatibleAdapter()
        cab = _make_cabinet()
        result = _make_result(cabinets=[cab])
        sheets = adapter.adapt(result)
        assert sheets["total"]["rows"][0]["price"] == 0.0

    def test_quote_line_matched_to_item(self):
        adapter = HHCompatibleAdapter()
        cab = _make_cabinet()
        m = _make_material(name="断路器", norm_name="断路器", unit_price=None)
        ql = QuoteLine(
            cabinet_no="A", material_name="断路器",
            unit_price=650.0, subtotal=3900.0,
        )
        result = _make_result(
            cabinets=[cab],
            bom_lines=[BomLine(cabinet_no="A", material=m)],
            quote_lines=[ql],
        )
        sheets = adapter.adapt(result)
        item = [r for r in sheets["cab_A"]["rows"] if r["type"] == "item"][0]
        assert item["price"] == 650.0

    def test_quote_line_match_fallback_original_name(self):
        """归一化名不匹配时，回退用原始名匹配。"""
        adapter = HHCompatibleAdapter()
        cab = _make_cabinet()
        m = _make_material(name="ABB断路器", norm_name="塑壳断路器")
        ql = QuoteLine(
            cabinet_no="A", material_name="ABB断路器",
            unit_price=800.0, subtotal=4800.0,
        )
        result = _make_result(
            cabinets=[cab],
            bom_lines=[BomLine(cabinet_no="A", material=m)],
            quote_lines=[ql],
        )
        sheets = adapter.adapt(result)
        item = [r for r in sheets["cab_A"]["rows"] if r["type"] == "item"][0]
        assert item["price"] == 800.0


class TestAdapterNullHandling:
    """None 值序列化。"""

    def test_none_brand_and_spec(self):
        adapter = HHCompatibleAdapter()
        cab = _make_cabinet()
        m = _make_material(
            brand=None, norm_brand=None,
            spec=None, norm_spec=None,
            unit=None,
        )
        result = _make_result(
            cabinets=[cab],
            bom_lines=[BomLine(cabinet_no="A", material=m)],
        )
        sheets = adapter.adapt(result)
        item = [r for r in sheets["cab_A"]["rows"] if r["type"] == "item"][0]
        assert item["factory"] == ""
        assert item["model"] == ""
        assert item["unit"] == "个"  # fallback

    def test_no_none_values_in_output(self):
        """输出中不应出现 Python None。"""
        adapter = HHCompatibleAdapter()
        cab = _make_cabinet()
        m = _make_material(brand=None, norm_brand=None, spec=None, norm_spec=None)
        result = _make_result(
            cabinets=[cab],
            bom_lines=[BomLine(cabinet_no="A", material=m)],
        )
        sheets = adapter.adapt(result)
        # 递归检查所有值
        errors = _find_none(sheets)
        assert not errors, f"Found None values at: {errors}"


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _find_none(obj, path=""):
    """递归查找字典/列表中的 None 值，返回路径列表。"""
    errors = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if v is None:
                errors.append(f"{path}.{k}")
            elif isinstance(v, (dict, list)):
                errors.extend(_find_none(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if v is None:
                errors.append(f"{path}[{i}]")
            elif isinstance(v, (dict, list)):
                errors.extend(_find_none(v, f"{path}[{i}]"))
    return errors

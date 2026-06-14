"""Unit tests for vision_llm.py — JSON parsing, model builders, result dataclass.

These tests exercise the pure-logic components of the Vision LLM adapter
without making actual API calls. Backend integration tests (requiring API keys)
are in tests/integration/parsing/.
"""

from pathlib import Path

import pytest

from huigongyun.parsing.vision_llm import (
    EXTRACTION_SCHEMA,
    SYSTEM_PROMPT,
    VisionLLMExtractionResult,
    VisionLLMExtractor,
    VisionLLMResponse,
    _build_cabinet_records,
    _build_material_records,
    _extract_materials_from_tables,
    _image_to_base64,
    _parse_json_from_text,
    _safe_get,
)


# ---------------------------------------------------------------------------
# _parse_json_from_text
# ---------------------------------------------------------------------------

class TestParseJsonFromText:
    def test_parses_plain_json(self):
        result = _parse_json_from_text('{"cabinets": [], "materials": []}')
        assert result == {"cabinets": [], "materials": []}

    def test_parses_json_in_markdown_fence(self):
        text = 'some text before\n```json\n{"cabinets": [{"cabinet_no": "AA1"}]}\n```\nsome text after'
        result = _parse_json_from_text(text)
        assert result == {"cabinets": [{"cabinet_no": "AA1"}]}

    def test_parses_json_in_plain_fence(self):
        text = '```\n{"materials": [{"name": "断路器"}]}\n```'
        result = _parse_json_from_text(text)
        assert result == {"materials": [{"name": "断路器"}]}

    def test_parses_nested_braces(self):
        text = 'prefix {"cabinets": [{"cabinet_no": "K1", "cabinet_type": "进线柜"}], "materials": []} suffix'
        result = _parse_json_from_text(text)
        assert result["cabinets"][0]["cabinet_no"] == "K1"

    def test_returns_none_for_empty_text(self):
        assert _parse_json_from_text("") is None

    def test_returns_none_for_non_json_text(self):
        assert _parse_json_from_text("This is not JSON at all.") is None

    def test_returns_none_for_none_input(self):
        assert _parse_json_from_text(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _build_cabinet_records
# ---------------------------------------------------------------------------

class TestBuildCabinetRecords:
    def test_builds_basic_cabinet(self):
        raw = [{"cabinet_no": "AA1", "cabinet_type": "进线柜", "rated_current": "2000A"}]
        records = _build_cabinet_records(raw, "test.pdf", 1)
        assert len(records) == 1
        assert records[0].cabinet_no == "AA1"
        assert records[0].cabinet_type == "进线柜"
        assert records[0].rated_current == "2000A"
        assert records[0].confidence == 0.75

    def test_skips_empty_cabinet_no(self):
        raw = [{"cabinet_no": "", "cabinet_type": "未知"}]
        records = _build_cabinet_records(raw, "test.pdf", 1)
        assert len(records) == 0

    def test_skips_non_dict_items(self):
        raw = ["not a dict", {"cabinet_no": "K1"}]
        records = _build_cabinet_records(raw, "test.pdf", 1)
        assert len(records) == 1
        assert records[0].cabinet_no == "K1"

    def test_includes_page_region_in_source(self):
        raw = [{"cabinet_no": "BB2", "page_region": "右下角"}]
        records = _build_cabinet_records(raw, "drawing.pdf", 3)
        assert len(records) == 1
        assert len(records[0].sources) == 1
        assert records[0].sources[0].excerpt == "右下角"
        assert records[0].sources[0].page_no == 3

    def test_empty_page_region_no_source(self):
        raw = [{"cabinet_no": "CC3", "page_region": ""}]
        records = _build_cabinet_records(raw, "drawing.pdf", 1)
        assert len(records[0].sources) == 0

    def test_multiple_cabinets(self):
        raw = [
            {"cabinet_no": "AA1", "cabinet_type": "进线柜"},
            {"cabinet_no": "AA2", "cabinet_type": "出线柜"},
            {"cabinet_no": "AA3", "cabinet_type": "母联柜"},
        ]
        records = _build_cabinet_records(raw, "test.pdf", 1)
        assert len(records) == 3
        assert [r.cabinet_no for r in records] == ["AA1", "AA2", "AA3"]


# ---------------------------------------------------------------------------
# _build_material_records
# ---------------------------------------------------------------------------

class TestBuildMaterialRecords:
    def test_builds_basic_material(self):
        raw = [{"name": "框架断路器", "spec": "3P 2000A", "brand": "施耐德", "quantity": 1}]
        records = _build_material_records(raw, "test.pdf", 1)
        assert len(records) == 1
        assert records[0].name == "框架断路器"
        assert records[0].spec == "3P 2000A"
        assert records[0].brand == "施耐德"
        assert records[0].quantity == 1.0
        assert records[0].confidence == 0.70

    def test_defaults_unit_to_ge(self):
        raw = [{"name": "铜排"}]
        records = _build_material_records(raw, "test.pdf", 1)
        assert records[0].unit == "个"

    def test_uses_provided_unit(self):
        raw = [{"name": "电缆", "unit": "米"}]
        records = _build_material_records(raw, "test.pdf", 1)
        assert records[0].unit == "米"

    def test_skips_empty_name(self):
        raw = [{"name": "", "spec": "xxx"}]
        records = _build_material_records(raw, "test.pdf", 1)
        assert len(records) == 0

    def test_stores_cabinet_ref_in_remarks(self):
        raw = [{"name": "互感器", "cabinet_ref": "AA1"}]
        records = _build_material_records(raw, "test.pdf", 1)
        assert "AA1" in (records[0].remarks or "")

    def test_quantity_defaults_to_1(self):
        raw = [{"name": "继电器"}]
        records = _build_material_records(raw, "test.pdf", 1)
        assert records[0].quantity == 1.0


# ---------------------------------------------------------------------------
# _extract_materials_from_tables
# ---------------------------------------------------------------------------

class TestExtractMaterialsFromTables:
    def test_extracts_from_material_table(self):
        tables = [
            {
                "caption": "设备材料表",
                "headers": ["名称", "规格", "数量", "品牌"],
                "rows": [
                    ["断路器", "3P 250A", "2", "施耐德"],
                    ["互感器", "2000/5A", "3", "正泰"],
                ],
            }
        ]
        records = _extract_materials_from_tables(tables, "test.pdf", 1)
        assert len(records) == 2
        assert records[0].name == "断路器"
        assert records[0].quantity == 2.0
        assert records[0].brand == "施耐德"
        assert records[1].name == "互感器"
        assert records[1].spec == "2000/5A"

    def test_skips_non_material_table(self):
        tables = [
            {
                "caption": "图例表",
                "headers": ["符号", "说明"],
                "rows": [["○", "指示灯"], ["□", "断路器"]],
            }
        ]
        records = _extract_materials_from_tables(tables, "test.pdf", 1)
        assert len(records) == 0

    def test_handles_english_headers(self):
        tables = [
            {
                "headers": ["Description", "Spec", "Qty", "Brand"],
                "rows": [["MCCB", "250A", "5", "ABB"]],
            }
        ]
        records = _extract_materials_from_tables(tables, "test.pdf", 1)
        assert len(records) == 1
        assert records[0].name == "MCCB"

    def test_handles_missing_optional_columns(self):
        tables = [
            {
                "headers": ["名称", "规格"],
                "rows": [["铜排", "40x5mm"]],
            }
        ]
        records = _extract_materials_from_tables(tables, "test.pdf", 1)
        assert len(records) == 1
        assert records[0].name == "铜排"
        assert records[0].quantity == 1.0  # default

    def test_skips_empty_rows(self):
        tables = [
            {
                "headers": ["名称", "规格", "数量"],
                "rows": [["断路器", "250A", "1"], ["", "", ""], ["", "", ""]],
            }
        ]
        records = _extract_materials_from_tables(tables, "test.pdf", 1)
        assert len(records) == 1

    def test_handles_invalid_quantity(self):
        tables = [
            {
                "headers": ["名称", "数量"],
                "rows": [["继电器", "N/A"]],
            }
        ]
        records = _extract_materials_from_tables(tables, "test.pdf", 1)
        assert len(records) == 1
        assert records[0].quantity == 1.0  # defaults on parse error


# ---------------------------------------------------------------------------
# _safe_get
# ---------------------------------------------------------------------------

class TestSafeGet:
    def test_gets_value_at_index(self):
        assert _safe_get(["a", "b", "c"], 1) == "b"

    def test_returns_none_for_out_of_range(self):
        assert _safe_get(["a"], 5) is None

    def test_returns_none_for_none_index(self):
        assert _safe_get(["a", "b"], None) is None

    def test_strips_whitespace(self):
        assert _safe_get(["  hello  "], 0) == "hello"

    def test_returns_none_for_empty_string(self):
        assert _safe_get([""], 0) is None


# ---------------------------------------------------------------------------
# _image_to_base64
# ---------------------------------------------------------------------------

class TestImageToBase64:
    def test_converts_pil_image(self):
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="white")
        b64, media_type = _image_to_base64(img)
        assert isinstance(b64, str)
        assert len(b64) > 0
        assert media_type == "image/png"

    def test_converts_png_file(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (50, 50), color="red")
        filepath = tmp_path / "test.png"
        img.save(str(filepath))

        b64, media_type = _image_to_base64(str(filepath))
        assert isinstance(b64, str)
        assert len(b64) > 0
        assert media_type == "image/png"

    def test_converts_jpg_file(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (50, 50), color="blue")
        filepath = tmp_path / "test.jpg"
        img.save(str(filepath))

        b64, media_type = _image_to_base64(str(filepath))
        assert media_type == "image/jpeg"


# ---------------------------------------------------------------------------
# VisionLLMExtractionResult
# ---------------------------------------------------------------------------

class TestVisionLLMExtractionResult:
    def test_success_when_no_error(self):
        r = VisionLLMExtractionResult()
        assert r.success is True

    def test_not_success_when_error(self):
        r = VisionLLMExtractionResult(error="API timeout")
        assert r.success is False

    def test_total_items_counts_cabinets_and_materials(self):
        from huigongyun.models import CabinetRecord, MaterialRecord

        r = VisionLLMExtractionResult(
            cabinets=[CabinetRecord(cabinet_no="A1")],
            materials=[MaterialRecord(name="M1"), MaterialRecord(name="M2")],
        )
        assert r.total_items == 3

    def test_empty_result_zero_items(self):
        r = VisionLLMExtractionResult()
        assert r.total_items == 0


# ---------------------------------------------------------------------------
# VisionLLMExtractor (unit tests, no API calls)
# ---------------------------------------------------------------------------

class TestVisionLLMExtractor:
    def test_default_provider_openai(self):
        e = VisionLLMExtractor()
        assert e.provider == "openai"

    def test_default_max_tokens(self):
        e = VisionLLMExtractor()
        assert e.max_tokens == 4096

    def test_has_extraction_schema(self):
        e = VisionLLMExtractor()
        assert e.json_schema is not None
        assert "cabinets" in e.json_schema["properties"]

    def test_has_system_prompt(self):
        e = VisionLLMExtractor()
        assert "电气成套" in e.system_prompt
        assert "柜号" in e.system_prompt

    def test_unknown_provider_raises(self):
        e = VisionLLMExtractor(provider="unknown_provider")
        with pytest.raises(ValueError, match="Unknown Vision LLM provider"):
            e._get_backend()


# ---------------------------------------------------------------------------
# EXTRACTION_SCHEMA validation
# ---------------------------------------------------------------------------

class TestExtractionSchema:
    def test_schema_has_required_sections(self):
        props = EXTRACTION_SCHEMA["properties"]
        assert "cabinets" in props
        assert "materials" in props
        assert "tables" in props
        assert "annotations" in props

    def test_cabinet_schema_has_expected_fields(self):
        cab_props = EXTRACTION_SCHEMA["properties"]["cabinets"]["items"]["properties"]
        assert "cabinet_no" in cab_props
        assert "cabinet_type" in cab_props
        assert "rated_current" in cab_props

    def test_material_schema_has_expected_fields(self):
        mat_props = EXTRACTION_SCHEMA["properties"]["materials"]["items"]["properties"]
        assert "name" in mat_props
        assert "spec" in mat_props
        assert "brand" in mat_props
        assert "quantity" in mat_props

    def test_cabinet_no_is_required(self):
        cab_required = EXTRACTION_SCHEMA["properties"]["cabinets"]["items"].get("required", [])
        assert "cabinet_no" in cab_required

    def test_name_is_required_in_materials(self):
        mat_required = EXTRACTION_SCHEMA["properties"]["materials"]["items"].get("required", [])
        assert "name" in mat_required


# ---------------------------------------------------------------------------
# VisionLLMResponse dataclass
# ---------------------------------------------------------------------------

class TestVisionLLMResponse:
    def test_success_response(self):
        r = VisionLLMResponse(
            raw_text='{"ok": true}',
            parsed_json={"ok": True},
            model_used="gpt-4o",
        )
        assert r.error is None

    def test_error_response(self):
        r = VisionLLMResponse(
            raw_text="",
            parsed_json=None,
            error="Failed to parse JSON",
        )
        assert r.error is not None

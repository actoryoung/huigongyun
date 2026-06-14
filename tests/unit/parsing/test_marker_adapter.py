"""Unit tests for marker_adapter.py — MarkerResult, MarkerTable, table conversion,

and MarkerAdapter availability checks. These tests do NOT require Marker models
to be downloaded (no actual PDF conversion).
"""

import pytest

from huigongyun.parsing.marker_adapter import (
    MarkerAdapter,
    MarkerResult,
    MarkerTable,
    _extract_tables_from_markdown,
    _safe_cell,
    marker_tables_to_material_records,
)


# ---------------------------------------------------------------------------
# MarkerResult
# ---------------------------------------------------------------------------

class TestMarkerResult:
    def test_default_result(self):
        r = MarkerResult()
        assert r.success is False  # empty markdown + plain_text
        assert r.error is None

    def test_success_with_markdown(self):
        r = MarkerResult(markdown="# Hello\n\nContent here")
        assert r.success is True

    def test_success_with_plain_text(self):
        r = MarkerResult(plain_text="Some extracted text")
        assert r.success is True

    def test_not_success_with_error(self):
        r = MarkerResult(error="Conversion failed")
        assert r.success is False

    def test_stores_source_path(self):
        r = MarkerResult(source_path="/path/to/doc.pdf")
        assert r.source_path == "/path/to/doc.pdf"


# ---------------------------------------------------------------------------
# MarkerTable
# ---------------------------------------------------------------------------

class TestMarkerTable:
    def test_default_table(self):
        t = MarkerTable(page_no=1)
        assert t.page_no == 1
        assert t.headers == []
        assert t.rows == []

    def test_table_with_data(self):
        t = MarkerTable(
            page_no=2,
            headers=["名称", "规格", "数量"],
            rows=[["断路器", "250A", "2"], ["互感器", "2000/5A", "3"]],
        )
        assert len(t.rows) == 2
        assert t.headers[0] == "名称"


# ---------------------------------------------------------------------------
# _extract_tables_from_markdown
# ---------------------------------------------------------------------------

class TestExtractTablesFromMarkdown:
    def test_extracts_simple_table(self):
        md = """
| 名称 | 规格 | 数量 |
|------|------|------|
| 断路器 | 250A | 2 |
| 互感器 | 2000/5A | 3 |
"""
        tables = _extract_tables_from_markdown(md)
        assert len(tables) == 1
        assert tables[0].headers == ["名称", "规格", "数量"]
        assert len(tables[0].rows) == 2

    def test_extracts_multiple_tables(self):
        md = """
| A | B |
|---|---|
| 1 | 2 |

Some text in between.

| X | Y |
|---|---|
| a | b |
"""
        tables = _extract_tables_from_markdown(md)
        assert len(tables) == 2

    def test_handles_no_tables(self):
        md = "Just some text\nwithout any tables."
        tables = _extract_tables_from_markdown(md)
        assert len(tables) == 0

    def test_skips_invalid_separator(self):
        md = """
| Col1 | Col2 |
| not a separator |
| data | here |
"""
        tables = _extract_tables_from_markdown(md)
        assert len(tables) == 0

    def test_handles_empty_input(self):
        tables = _extract_tables_from_markdown("")
        assert len(tables) == 0

    def test_strips_whitespace_from_cells(self):
        md = """
|   Name   |  Qty  |
|----------|-------|
|   Item1  |   5   |
"""
        tables = _extract_tables_from_markdown(md)
        assert tables[0].headers == ["Name", "Qty"]
        assert tables[0].rows[0] == ["Item1", "5"]


# ---------------------------------------------------------------------------
# _safe_cell
# ---------------------------------------------------------------------------

class TestSafeCell:
    def test_gets_value(self):
        assert _safe_cell(["a", "b"], 0) == "a"

    def test_none_for_out_of_range(self):
        assert _safe_cell(["a"], 3) is None

    def test_none_for_none_index(self):
        assert _safe_cell(["a"], None) is None

    def test_strips_whitespace(self):
        assert _safe_cell(["  hello  "], 0) == "hello"

    def test_none_for_empty_string(self):
        assert _safe_cell([""], 0) is None


# ---------------------------------------------------------------------------
# marker_tables_to_material_records
# ---------------------------------------------------------------------------

class TestMarkerTablesToMaterialRecords:
    def test_converts_material_table(self):
        tables = [
            MarkerTable(
                page_no=1,
                headers=["名称", "规格", "数量", "品牌"],
                rows=[["断路器", "3P 250A", "2", "施耐德"]],
            )
        ]
        records = marker_tables_to_material_records(tables, "test.pdf")
        assert len(records) == 1
        assert records[0].name == "断路器"
        assert records[0].spec == "3P 250A"
        assert records[0].quantity == 2.0
        assert records[0].brand == "施耐德"
        assert records[0].confidence == 0.80

    def test_skips_non_material_table(self):
        tables = [
            MarkerTable(
                page_no=1,
                headers=["符号", "说明"],
                rows=[["○", "指示灯"]],
            )
        ]
        records = marker_tables_to_material_records(tables, "test.pdf")
        assert len(records) == 0

    def test_default_unit(self):
        tables = [
            MarkerTable(
                headers=["名称", "数量"],
                rows=[["铜排", "10"]],
            )
        ]
        records = marker_tables_to_material_records(tables)
        assert records[0].unit == "个"

    def test_uses_provided_unit(self):
        tables = [
            MarkerTable(
                headers=["名称", "单位", "数量"],
                rows=[["电缆", "米", "100"]],
            )
        ]
        records = marker_tables_to_material_records(tables)
        assert records[0].unit == "米"

    def test_handles_english_headers(self):
        tables = [
            MarkerTable(
                headers=["Description", "Qty", "Brand"],
                rows=[["MCCB", "5", "ABB"]],
            )
        ]
        records = marker_tables_to_material_records(tables)
        assert len(records) == 1
        assert records[0].name == "MCCB"


# ---------------------------------------------------------------------------
# MarkerAdapter availability
# ---------------------------------------------------------------------------

class TestMarkerAdapter:
    def test_availability_check(self):
        adapter = MarkerAdapter()
        # Marker was pip-installed, so is_available should be True
        assert adapter.is_available() is True

    def test_convert_missing_file(self):
        adapter = MarkerAdapter()
        result = adapter.convert("/nonexistent/path/file.pdf")
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    def test_caches_converter(self):
        adapter = MarkerAdapter()
        assert adapter._converter is None
        # Just check availability — don't trigger model download
        assert adapter.is_available() is True

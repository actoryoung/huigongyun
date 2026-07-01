"""Unit tests for MultiSourceExtractor.

Covers Vision LLM deserialization, DWG cabinet extraction, cross-source
merging with confidence priority, and empty-input fallback.
"""

import pytest

from src.generation.multi_extractor import MultiSourceExtractor
from src.models import BomLine, CabinetRecord, MaterialRecord, ProjectDocument, ProjectResult, SourceRef


# ── Helpers ──────────────────────────────────────────────────────────


def _make_material(name, spec=None, unit=None, quantity=1.0, brand=None, confidence=0.7):
    return MaterialRecord(
        name=name, spec=spec, unit=unit or "个", quantity=quantity,
        brand=brand,
        source=SourceRef(file_name="excel", file_type="excel", confidence=confidence),
        confidence=confidence,
    )


def _make_bom_line(cabinet_no, material, derived_from="excel:Sheet1:2"):
    return BomLine(cabinet_no=cabinet_no, material=material, derived_from=derived_from)


def _make_cabinet(cabinet_no, cabinet_type=None, confidence=0.7, **kwargs):
    return CabinetRecord(
        cabinet_no=cabinet_no, cabinet_type=cabinet_type,
        confidence=confidence,
        sources=[SourceRef(file_name="test", file_type="test", confidence=confidence)],
        **kwargs,
    )


# ── Vision LLM deserialization ───────────────────────────────────────


class TestVisionLLMDeserialization:
    def test_extracts_cabinets_from_vision_llm_data(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "vision_llm_cabinets": [
                {"cabinet_no": "AA1", "cabinet_type": "进线柜", "rated_current": "2000A"},
                {"cabinet_no": "AA2", "cabinet_type": "出线柜"},
            ],
            "vision_llm_materials": [],
        }
        cabinets, bom_lines = extractor._extract_vision_llm(metadata)
        assert len(cabinets) == 2
        assert cabinets[0].cabinet_no == "AA1"
        assert cabinets[0].cabinet_type == "进线柜"
        assert cabinets[0].rated_current == "2000A"
        assert cabinets[0].confidence == 0.5
        assert cabinets[1].cabinet_no == "AA2"
        assert cabinets[1].cabinet_type == "出线柜"
        assert len(bom_lines) == 0

    def test_extracts_materials_from_vision_llm_data(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "vision_llm_cabinets": [],
            "vision_llm_materials": [
                {"name": "断路器", "spec": "NSX250F", "brand": "施耐德", "quantity": 2, "cabinet_ref": "AA1"},
                {"name": "接触器", "cabinet_ref": "AA1"},
            ],
        }
        cabinets, bom_lines = extractor._extract_vision_llm(metadata)
        assert len(cabinets) == 0
        assert len(bom_lines) == 2
        assert bom_lines[0].cabinet_no == "AA1"
        assert bom_lines[0].material.name == "断路器"
        assert bom_lines[0].material.spec == "NSX250F"
        assert bom_lines[0].material.brand == "施耐德"
        assert bom_lines[0].material.quantity == 2.0
        assert bom_lines[0].material.confidence == 0.5
        assert bom_lines[0].derived_from == "pdf:vision_llm"
        assert bom_lines[1].cabinet_no == "AA1"
        assert bom_lines[1].material.name == "接触器"
        assert bom_lines[1].material.quantity == 1.0
        assert bom_lines[1].material.unit == "个"

    def test_skips_empty_cabinet_no_in_vision_llm(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "vision_llm_cabinets": [
                {"cabinet_no": ""},
                {"cabinet_no": "   "},
                {"cabinet_no": "AA1"},
            ],
            "vision_llm_materials": [],
        }
        cabinets, _ = extractor._extract_vision_llm(metadata)
        assert len(cabinets) == 1
        assert cabinets[0].cabinet_no == "AA1"

    def test_skips_empty_material_name_in_vision_llm(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "vision_llm_cabinets": [],
            "vision_llm_materials": [
                {"name": ""},
                {"name": "   "},
                {"name": "断路器"},
            ],
        }
        _, bom_lines = extractor._extract_vision_llm(metadata)
        assert len(bom_lines) == 1
        assert bom_lines[0].material.name == "断路器"

    def test_missing_cabinet_ref_defaults_to_unknown(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "vision_llm_cabinets": [],
            "vision_llm_materials": [
                {"name": "断路器"},  # no cabinet_ref
            ],
        }
        _, bom_lines = extractor._extract_vision_llm(metadata)
        assert len(bom_lines) == 1
        assert bom_lines[0].cabinet_no in {"UNKNOWN", "未知"}

    def test_handles_non_dict_items_in_vision_llm(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "vision_llm_cabinets": ["not_a_dict", {"cabinet_no": "AA1"}],
            "vision_llm_materials": [123, {"name": "断路器"}],
        }
        cabinets, bom_lines = extractor._extract_vision_llm(metadata)
        assert len(cabinets) == 1
        assert len(bom_lines) == 1


# ── DWG cabinet extraction ───────────────────────────────────────────


class TestDwgCabinetExtraction:
    def test_extracts_known_patterns_from_texts(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "electrical_texts": [
                "K1 进线柜 AC1015 主开关",
                "K2 出线柜 1AA 配电",
                "一些无关文字",
            ],
        }
        cabinets = extractor._extract_dwg_cabinets(metadata)
        nos = {c.cabinet_no for c in cabinets}
        assert "K1" in nos
        assert "K2" in nos
        assert "AC1015" in nos
        assert "1AA" in nos
        assert all(c.confidence == 0.3 for c in cabinets)

    def test_deduplicates_repeated_cabinet_numbers(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "electrical_texts": [
                "K1 断路器", "K1 接触器", "K1 继电器",
            ],
        }
        cabinets = extractor._extract_dwg_cabinets(metadata)
        assert len(cabinets) == 1
        assert cabinets[0].cabinet_no == "K1"

    def test_filters_short_matches(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "electrical_texts": [
                "K",  # too short (< 2 chars)
                "A",  # too short
                "K1",  # valid
            ],
        }
        cabinets = extractor._extract_dwg_cabinets(metadata)
        # regex patterns require at least 2 chars (len >= 2 filter)
        assert len(cabinets) == 1
        assert cabinets[0].cabinet_no == "K1"

    def test_empty_texts_returns_empty(self):
        extractor = MultiSourceExtractor()
        cabinets = extractor._extract_dwg_cabinets({"electrical_texts": []})
        assert len(cabinets) == 0

    def test_missing_electrical_texts_returns_empty(self):
        extractor = MultiSourceExtractor()
        cabinets = extractor._extract_dwg_cabinets({})
        assert len(cabinets) == 0

    def test_stores_source_reference_with_excerpt(self):
        extractor = MultiSourceExtractor()
        metadata = {
            "electrical_texts": [
                "K1 进线柜 额定电流 2000A 施耐德 Masterpact",
            ],
        }
        cabinets = extractor._extract_dwg_cabinets(metadata)
        assert len(cabinets) == 1
        assert len(cabinets[0].sources) == 1
        assert cabinets[0].sources[0].file_name == "dwg-text"
        assert cabinets[0].sources[0].file_type == "dwg"
        assert cabinets[0].sources[0].confidence == 0.3


# ── Merge: cabinets ───────────────────────────────────────────────────


class TestMergeCabinets:
    def test_higher_confidence_wins_and_fills_fields(self):
        extractor = MultiSourceExtractor()
        low = [_make_cabinet("K1", confidence=0.3)]
        high = [_make_cabinet("K1", cabinet_type="进线柜", confidence=0.7)]

        merged = extractor._merge_cabinets([low, high])
        assert len(merged) == 1
        assert merged[0].cabinet_no == "K1"
        assert merged[0].cabinet_type == "进线柜"
        assert merged[0].confidence == 0.7

    def test_lower_confidence_fills_missing_fields(self):
        extractor = MultiSourceExtractor()
        primary = [_make_cabinet("K1", confidence=0.7)]  # no cabinet_type
        secondary = [_make_cabinet("K1", cabinet_type="进线柜", confidence=0.3)]

        merged = extractor._merge_cabinets([primary, secondary])
        assert len(merged) == 1
        assert merged[0].cabinet_type == "进线柜"
        assert merged[0].confidence == 0.7  # primary confidence preserved

    def test_different_cabinets_kept_separate(self):
        extractor = MultiSourceExtractor()
        list1 = [_make_cabinet("K1"), _make_cabinet("K2")]
        list2 = [_make_cabinet("K3")]

        merged = extractor._merge_cabinets([list1, list2])
        assert len(merged) == 3
        assert {c.cabinet_no for c in merged} == {"K1", "K2", "K3"}

    def test_sources_are_merged(self):
        extractor = MultiSourceExtractor()
        c1 = CabinetRecord(cabinet_no="K1", sources=[
            SourceRef(file_name="excel", file_type="excel", confidence=0.7),
        ], confidence=0.7)
        c2 = CabinetRecord(cabinet_no="K1", sources=[
            SourceRef(file_name="dwg", file_type="dwg", confidence=0.3),
        ], confidence=0.3)

        merged = extractor._merge_cabinets([[c1], [c2]])
        assert len(merged) == 1
        assert len(merged[0].sources) == 2
        file_types = {s.file_type for s in merged[0].sources}
        assert file_types == {"excel", "dwg"}

    def test_merges_with_both_cabinet_lists(self):
        extractor = MultiSourceExtractor()
        list1 = [_make_cabinet("K1", cabinet_type="进线柜", confidence=0.7)]
        list2 = [_make_cabinet("K1", rated_current="2000A", confidence=0.5)]

        merged = extractor._merge_cabinets([list1, list2])
        assert len(merged) == 1
        assert merged[0].cabinet_type == "进线柜"  # from list1
        assert merged[0].rated_current == "2000A"  # filled from list2
        assert merged[0].confidence == 0.7  # highest kept


# ── Merge: BOM lines ─────────────────────────────────────────────────


class TestMergeBomLines:
    def test_cross_source_merge_sums_quantities(self):
        extractor = MultiSourceExtractor()
        mat = _make_material("断路器", spec="NSX250F", quantity=2)
        excel_bom = [_make_bom_line("K1", mat, derived_from="excel:Sheet1:2")]

        mat2 = _make_material("断路器", spec="NSX250F", quantity=1, confidence=0.5)
        vision_bom = [_make_bom_line("K1", mat2, derived_from="pdf:vision_llm")]

        merged = extractor._merge_bom_lines([excel_bom, vision_bom])
        assert len(merged) == 1
        assert merged[0].material.quantity == 3.0  # 2 + 1
        assert merged[0].material.confidence == 0.7  # max(0.7, 0.5)

    def test_cross_source_keeps_explicit_brand(self):
        extractor = MultiSourceExtractor()
        mat1 = _make_material("断路器", brand=None)
        mat2 = _make_material("断路器", brand="施耐德", confidence=0.5)

        merged = extractor._merge_bom_lines([
            [_make_bom_line("K1", mat1)],
            [_make_bom_line("K1", mat2)],
        ])
        assert len(merged) == 1
        assert merged[0].material.brand == "施耐德"

    def test_same_source_duplicates_preserved(self):
        extractor = MultiSourceExtractor()
        mat = _make_material("断路器", spec="NSX250F", quantity=1)
        excel_bom = [
            _make_bom_line("K1", mat),
            _make_bom_line("K1", mat),  # same source duplicate
        ]

        merged = extractor._merge_bom_lines([excel_bom])
        assert len(merged) == 2  # both preserved
        assert all(bl.material.quantity == 1.0 for bl in merged)

    def test_derived_from_concatenated_on_cross_source(self):
        extractor = MultiSourceExtractor()
        mat1 = _make_material("断路器")
        mat2 = _make_material("断路器", confidence=0.5)

        merged = extractor._merge_bom_lines([
            [_make_bom_line("K1", mat1, derived_from="excel:Sheet1:2")],
            [_make_bom_line("K1", mat2, derived_from="pdf:vision_llm")],
        ])
        assert len(merged) == 1
        assert "excel" in merged[0].derived_from
        assert "pdf" in merged[0].derived_from

    def test_different_materials_kept_separate(self):
        extractor = MultiSourceExtractor()
        mat1 = _make_material("断路器", spec="A")
        mat2 = _make_material("接触器", spec="B")

        merged = extractor._merge_bom_lines([
            [_make_bom_line("K1", mat1)],
            [_make_bom_line("K1", mat2)],
        ])
        assert len(merged) == 2

    def test_same_material_different_cabinets_kept_separate(self):
        extractor = MultiSourceExtractor()
        mat = _make_material("断路器")

        merged = extractor._merge_bom_lines([
            [_make_bom_line("K1", mat)],
            [_make_bom_line("K2", mat)],
        ])
        assert len(merged) == 2
        cabinets = {bl.cabinet_no for bl in merged}
        assert cabinets == {"K1", "K2"}


# ── Full extract (integration-style) ─────────────────────────────────


class TestFullExtract:
    def test_extract_with_sheets_delegates_to_excel_extractor(self):
        doc = ProjectDocument(
            project_name="test",
            files=["test.xlsx"],
            metadata={
                "input_kind": "excel",
                "sheets": [
                    {
                        "name": "主元件清单",
                        "headers": ["柜号", "物料名称", "规格型号", "数量"],
                        "records": [
                            {"柜号": "K1", "物料名称": "断路器", "规格型号": "NSX250F", "数量": 1, "_row_no": 2},
                        ],
                    }
                ],
            },
        )
        result = MultiSourceExtractor().extract(doc)
        assert len(result.cabinets) >= 1
        assert len(result.bom_lines) >= 1

    def test_extract_with_vision_llm_only(self):
        doc = ProjectDocument(
            project_name="test",
            files=["test.pdf"],
            metadata={
                "input_kind": "pdf",
                "vision_llm_cabinets": [
                    {"cabinet_no": "AA1", "cabinet_type": "进线柜"},
                ],
                "vision_llm_materials": [
                    {"name": "断路器", "spec": "NSX250F", "cabinet_ref": "AA1"},
                ],
            },
        )
        result = MultiSourceExtractor().extract(doc)
        assert len(result.cabinets) == 1
        assert result.cabinets[0].cabinet_no == "AA1"
        assert result.cabinets[0].cabinet_type == "进线柜"
        assert len(result.bom_lines) == 1
        assert result.bom_lines[0].material.name == "断路器"

    def test_extract_with_dwg_texts_only(self):
        doc = ProjectDocument(
            project_name="test",
            files=["test.dwg"],
            metadata={
                "input_kind": "dwg",
                "electrical_texts": [
                    "K1 进线柜", "K2 出线柜", "AC1015 主开关",
                ],
            },
        )
        result = MultiSourceExtractor().extract(doc)
        assert len(result.cabinets) >= 2
        cabinet_nos = {c.cabinet_no for c in result.cabinets}
        assert "K1" in cabinet_nos
        assert "K2" in cabinet_nos

    def test_empty_metadata_produces_placeholder(self):
        doc = ProjectDocument(project_name="test", files=["unknown.txt"], metadata={})
        result = MultiSourceExtractor().extract(doc)
        assert len(result.cabinets) == 1
        assert result.cabinets[0].cabinet_no == "TBD-01"
        assert result.cabinets[0].remarks == "placeholder"
        assert len(result.bom_lines) == 0

    def test_word_constraints_propagated_to_metadata(self):
        doc = ProjectDocument(
            project_name="test",
            files=["spec.docx"],
            metadata={
                "constraints": {
                    "grounding_mode": "TN-S",
                    "specified_brands": ["施耐德"],
                },
            },
        )
        result = MultiSourceExtractor().extract(doc)
        assert "design_constraints" in result.project.metadata
        assert result.project.metadata["design_constraints"]["grounding_mode"] == "TN-S"

    def test_multi_source_merges_cabinets(self):
        """Excel + DWG → cabinets deduplicated by cabinet_no."""
        doc = ProjectDocument(
            project_name="test",
            files=["test.xlsx", "test.dwg"],
            metadata={
                "sheets": [
                    {
                        "name": "主元件清单",
                        "headers": ["柜号", "物料名称", "数量"],
                        "records": [
                            {"柜号": "K1", "物料名称": "断路器", "数量": 1, "_row_no": 2},
                        ],
                    }
                ],
                "electrical_texts": ["K1 进线柜 2000A", "K2 出线柜"],
            },
        )
        result = MultiSourceExtractor().extract(doc)
        cabinet_nos = {c.cabinet_no for c in result.cabinets}
        assert "K1" in cabinet_nos
        assert "K2" in cabinet_nos  # from DWG
        # K1 should have merged (not duplicated)
        k1_count = sum(1 for c in result.cabinets if c.cabinet_no == "K1")
        assert k1_count == 1

    def test_multi_source_merges_bom_lines_across_sources(self):
        """Excel + Vision LLM → same material quantities summed."""
        doc = ProjectDocument(
            project_name="test",
            files=["test.xlsx", "test.pdf"],
            metadata={
                "sheets": [
                    {
                        "name": "主元件清单",
                        "headers": ["柜号", "物料名称", "数量"],
                        "records": [
                            {"柜号": "K1", "物料名称": "断路器", "数量": 2, "_row_no": 2},
                        ],
                    }
                ],
                "vision_llm_materials": [
                    {"name": "断路器", "cabinet_ref": "K1", "quantity": 1},
                ],
            },
        )
        result = MultiSourceExtractor().extract(doc)
        # Find the 断路器 BOM line
        breakers = [bl for bl in result.bom_lines if bl.material.name == "断路器"]
        assert len(breakers) == 1  # merged
        assert breakers[0].material.quantity == 3.0  # 2 + 1

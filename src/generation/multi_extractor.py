"""Multi-source unified cabinet and BOM extractor.

Routes data from various metadata sources (sheets, vision_llm, DWG texts,
Word constraints) into a unified ProjectResult with cabinets and bom_lines,
then deduplicates and merges by cabinet number and material identity.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectDocument, ProjectResult, SourceRef
from .excel_bom import ExcelCabinetAndBomExtractor


# Regex patterns for cabinet numbers commonly found in DWG electrical texts.
_CABINET_PATTERNS = [
    re.compile(r'\bK\d+\b'),            # K1, K2, K12
    re.compile(r'\bAC\d{4}\b'),         # AC1015, AC1018
    re.compile(r'\b\d+AA\b'),           # 1AA, 2AA05
    re.compile(r'\b[A-Z]{1,3}\d+[A-Z]?\b'),  # AA1, M1A, AH01, QF1
]


class MultiSourceExtractor:
    """Unified extractor that handles multiple source formats.

    Routes data from various metadata sources (sheets, vision_llm, DWG texts)
    into a unified ProjectResult with cabinets and bom_lines.
    """

    def extract(self, document: ProjectDocument) -> ProjectResult:
        """Extract cabinets and BOM lines from all available metadata sources."""
        metadata = document.metadata if isinstance(document.metadata, dict) else {}

        all_cabinets: list[list[CabinetRecord]] = []
        all_bom_lines: list[list[BomLine]] = []

        # 1. Excel/PDF sheets (existing path, highest confidence)
        if metadata.get("sheets"):
            excel_result = ExcelCabinetAndBomExtractor().extract(document)
            all_cabinets.append(list(excel_result.cabinets))
            all_bom_lines.append(list(excel_result.bom_lines))

        # 2. Vision LLM output
        if metadata.get("vision_llm_cabinets") or metadata.get("vision_llm_materials"):
            vl_cabs, vl_boms = self._extract_vision_llm(metadata)
            if vl_cabs:
                all_cabinets.append(vl_cabs)
            if vl_boms:
                all_bom_lines.append(vl_boms)

        # 3. DWG cabinet extraction
        dwg_cabs = self._extract_dwg_cabinets(metadata)
        if dwg_cabs:
            all_cabinets.append(dwg_cabs)

        # Merge and deduplicate
        result = ProjectResult(project=document)
        result.cabinets = self._merge_cabinets(all_cabinets)
        result.bom_lines = self._merge_bom_lines(all_bom_lines)

        # Propagate Word constraints to project metadata
        if metadata.get("constraints"):
            merged_meta = dict(result.project.metadata)
            merged_meta.setdefault("design_constraints", metadata["constraints"])
            result.project.metadata = merged_meta

        # If nothing found, return placeholder
        if not result.cabinets:
            result.cabinets.append(CabinetRecord(
                cabinet_no="TBD-01", cabinet_type="unknown", remarks="placeholder"
            ))

        return result

    # ------------------------------------------------------------------
    # Vision LLM deserialization
    # ------------------------------------------------------------------

    def _extract_vision_llm(self, metadata: dict) -> tuple[list[CabinetRecord], list[BomLine]]:
        """Deserialize vision_llm_cabinets and vision_llm_materials from metadata."""
        cabinets_data: list[dict[str, Any]] = metadata.get("vision_llm_cabinets", [])
        materials_data: list[dict[str, Any]] = metadata.get("vision_llm_materials", [])

        cabinets: list[CabinetRecord] = []
        for c in cabinets_data:
            if not isinstance(c, dict):
                continue
            cabinet_no = (c.get("cabinet_no") or "").strip()
            if not cabinet_no:
                continue
            source = SourceRef(
                file_name="pdf-vision-llm",
                file_type="pdf",
                confidence=0.5,
            )
            cabinets.append(CabinetRecord(
                cabinet_no=cabinet_no,
                cabinet_type=c.get("cabinet_type"),
                rated_current=c.get("rated_current"),
                dimensions=c.get("dimensions"),
                circuit_count=c.get("circuit_count"),
                grounding_mode=c.get("grounding_mode"),
                sources=[source],
                confidence=0.5,
                remarks=c.get("remarks"),
            ))

        bom_lines: list[BomLine] = []
        for m in materials_data:
            if not isinstance(m, dict):
                continue
            name = (m.get("name") or "").strip()
            if not name:
                continue
            cabinet_ref = m.get("cabinet_ref") or "UNKNOWN"
            material = MaterialRecord(
                name=name,
                spec=m.get("spec"),
                unit=m.get("unit") or "个",
                quantity=float(m.get("quantity", 1)),
                brand=m.get("brand"),
                source=SourceRef(file_name="pdf-vision-llm", file_type="pdf", confidence=0.5),
                confidence=0.5,
                remarks=m.get("remarks"),
            )
            bom_lines.append(BomLine(
                cabinet_no=cabinet_ref,
                material=material,
                derived_from="pdf:vision_llm",
            ))

        return cabinets, bom_lines

    # ------------------------------------------------------------------
    # DWG cabinet extraction
    # ------------------------------------------------------------------

    def _extract_dwg_cabinets(self, metadata: dict) -> list[CabinetRecord]:
        """Extract cabinet numbers from DWG electrical_texts using regex."""
        texts: list[str] = metadata.get("electrical_texts", [])
        if not texts:
            return []

        seen: set[str] = set()
        cabinets: list[CabinetRecord] = []

        for text in texts:
            text_str = str(text)
            for pattern in _CABINET_PATTERNS:
                for match in pattern.finditer(text_str):
                    cn = match.group(0)
                    if cn not in seen and len(cn) >= 2:
                        seen.add(cn)
                        excerpt = text_str[:80] if len(text_str) > 80 else text_str
                        source = SourceRef(
                            file_name="dwg-text",
                            file_type="dwg",
                            excerpt=excerpt,
                            confidence=0.3,
                        )
                        cabinets.append(CabinetRecord(
                            cabinet_no=cn,
                            sources=[source],
                            confidence=0.3,
                            remarks=f"extracted from DWG text: {text_str[:50]}",
                        ))

        return cabinets

    # ------------------------------------------------------------------
    # Merge logic
    # ------------------------------------------------------------------

    def _merge_cabinets(
        self, cabinets_list: list[list[CabinetRecord]]
    ) -> list[CabinetRecord]:
        """Deduplicate cabinets by cabinet_no, keep highest confidence, merge fields."""
        merged: dict[str, CabinetRecord] = {}

        for cab_list in cabinets_list:
            for cab in cab_list:
                existing = merged.get(cab.cabinet_no)
                if existing is None:
                    merged[cab.cabinet_no] = cab
                    continue

                # Merge sources
                existing.sources.extend(cab.sources)

                if cab.confidence > existing.confidence:
                    # Higher confidence source becomes primary — merge its fields
                    # into existing (but keep existing's non-None values where cab is None)
                    existing.cabinet_type = cab.cabinet_type if cab.cabinet_type is not None else existing.cabinet_type
                    existing.rated_current = cab.rated_current if cab.rated_current is not None else existing.rated_current
                    existing.dimensions = cab.dimensions if cab.dimensions is not None else existing.dimensions
                    existing.circuit_count = cab.circuit_count if cab.circuit_count is not None else existing.circuit_count
                    existing.quantity = cab.quantity
                    existing.inbound_outbound = cab.inbound_outbound if cab.inbound_outbound is not None else existing.inbound_outbound
                    existing.grounding_mode = cab.grounding_mode if cab.grounding_mode is not None else existing.grounding_mode
                    existing.confidence = cab.confidence
                    existing.remarks = cab.remarks if cab.remarks is not None else existing.remarks
                else:
                    # Fill missing fields from lower-confidence source
                    if not existing.cabinet_type:
                        existing.cabinet_type = cab.cabinet_type
                    if not existing.rated_current:
                        existing.rated_current = cab.rated_current
                    if not existing.dimensions:
                        existing.dimensions = cab.dimensions
                    if existing.circuit_count is None:
                        existing.circuit_count = cab.circuit_count
                    if existing.quantity <= 0:
                        existing.quantity = cab.quantity
                    if not existing.inbound_outbound:
                        existing.inbound_outbound = cab.inbound_outbound
                    if not existing.grounding_mode:
                        existing.grounding_mode = cab.grounding_mode
                    if not existing.remarks:
                        existing.remarks = cab.remarks

        return list(merged.values())

    def _merge_bom_lines(
        self, bom_list: list[list[BomLine]]
    ) -> list[BomLine]:
        """Deduplicate BOM lines across different sources only.

        Same-source duplicates are preserved (e.g. identical rows from the
        same Excel sheet remain as separate entries so the validator can
        flag them).
        """
        merged: dict[tuple[str, str, str], BomLine] = {}
        merged_src: dict[tuple[str, str, str], int] = {}
        append: list[BomLine] = []

        for src_idx, bl_list in enumerate(bom_list):
            for bl in bl_list:
                mat = bl.material
                key = (bl.cabinet_no, mat.name, mat.spec or "")
                existing = merged.get(key)
                if existing is None:
                    merged[key] = bl
                    merged_src[key] = src_idx
                    continue

                if merged_src[key] != src_idx:
                    # Cross-source: merge quantities and keep highest confidence
                    existing.material.quantity += mat.quantity
                    existing.material.confidence = max(
                        existing.material.confidence, mat.confidence
                    )
                    if not existing.material.brand and mat.brand:
                        existing.material.brand = mat.brand
                    if bl.derived_from not in existing.derived_from:
                        existing.derived_from = existing.derived_from + ";" + bl.derived_from
                else:
                    # Same-source duplicate: preserve as a separate entry
                    append.append(bl)

        return list(merged.values()) + append

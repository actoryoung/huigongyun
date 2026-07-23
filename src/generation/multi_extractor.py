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
        """Extract cabinets and BOM lines from all available metadata sources.

        Uses a two-pass strategy so that Vision LLM material cabinet_ref
        matching can see all known cabinet numbers (Excel + Vision LLM +
        DWG), not just those from Vision LLM itself.
        """
        metadata = document.metadata if isinstance(document.metadata, dict) else {}

        all_cabinets: list[list[CabinetRecord]] = []
        all_bom_lines: list[list[BomLine]] = []

        # --- Phase 1: collect cabinets from every source ---

        if metadata.get("sheets"):
            excel_result = ExcelCabinetAndBomExtractor().extract(document)
            all_cabinets.append(list(excel_result.cabinets))
            all_bom_lines.append(list(excel_result.bom_lines))

        vl_cabs: list[CabinetRecord] = []
        vl_boms: list[BomLine] = []
        if metadata.get("vision_llm_cabinets") or metadata.get("vision_llm_materials"):
            vl_cabs, vl_boms = self._extract_vision_llm(metadata)
            if vl_cabs:
                all_cabinets.append(vl_cabs)

        dwg_cabs = self._extract_dwg_cabinets(metadata)
        if dwg_cabs:
            all_cabinets.append(dwg_cabs)

        # --- Phase 2: remap Vision LLM BOM cabinet_refs using the
        #             full merged cabinet list ---
        merged_cabinets = self._merge_cabinets(all_cabinets)
        all_known_nos: set[str] = {c.cabinet_no for c in merged_cabinets if c.cabinet_no}

        if vl_boms and all_known_nos:
            vl_boms = self._remap_bom_cabinet_refs(vl_boms, all_known_nos)
        if vl_boms:
            all_bom_lines.append(vl_boms)

        # Merge and deduplicate
        result = ProjectResult(project=document)
        result.cabinets = merged_cabinets
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
        known_cabinet_nos: set[str] = set()
        for c in cabinets_data:
            if not isinstance(c, dict):
                continue
            cabinet_no = (c.get("cabinet_no") or "").strip()
            if not cabinet_no:
                continue
            known_cabinet_nos.add(cabinet_no)
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
            cabinet_ref = (m.get("cabinet_ref") or "").strip()
            if not cabinet_ref:
                cabinet_ref = "UNKNOWN"

            # Map cabinet_ref → best matching cabinet_no
            matched_cabinet = self._match_cabinet_ref(
                cabinet_ref, known_cabinet_nos
            )

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
                cabinet_no=matched_cabinet,
                material=material,
                derived_from=f"pdf:vision_llm"
                + (f":map({cabinet_ref}→{matched_cabinet})"
                   if matched_cabinet != cabinet_ref else ""),
            ))

        return cabinets, bom_lines

    def _match_cabinet_ref(
        self, cabinet_ref: str, known_nos: set[str]
    ) -> str:
        """Match a Vision LLM cabinet_ref to a known cabinet_no.

        Strategy (ordered by priority):
        1. Exact match — ``cabinet_ref`` is identical to a known cabinet_no.
        2. Substring match — ``cabinet_ref`` appears inside a known cabinet_no
           or vice versa (e.g. "空调配电屏" ⊆ "空调配电屏-1").
        3. Normalised fuzzy match — strip parentheses, whitespace, and common
           suffixes, then compare.
        4. Fallback — return ``cabinet_ref`` as-is (may be "UNKNOWN").
        """
        if not cabinet_ref or cabinet_ref == "UNKNOWN" or not known_nos:
            return cabinet_ref

        # 1. Exact match
        if cabinet_ref in known_nos:
            return cabinet_ref

        # 2. Substring / superstring match
        for cn in known_nos:
            if cabinet_ref in cn or cn in cabinet_ref:
                return cn

        # 3. Normalised match: strip （）, -, whitespace
        import re as _re
        norm_ref = _re.sub(r"[（()）\-\s]+", "", cabinet_ref)
        best: tuple[str, int] | None = None  # (cabinet_no, common_prefix_len)
        for cn in known_nos:
            norm_cn = _re.sub(r"[（()）\-\s]+", "", cn)
            if norm_ref == norm_cn:
                return cn
            # Longest common prefix as tie-breaker
            prefix_len = 0
            for a, b in zip(norm_ref, norm_cn):
                if a == b:
                    prefix_len += 1
                else:
                    break
            if prefix_len >= 2 and (best is None or prefix_len > best[1]):
                best = (cn, prefix_len)

        if best is not None:
            return best[0]

        # 4. Fallback — keep original (let downstream validation flag it)
        return cabinet_ref

    def _remap_bom_cabinet_refs(
        self, bom_lines: list[BomLine], known_nos: set[str]
    ) -> list[BomLine]:
        """Re-map Vision LLM BOM cabinet_no fields using the full cabinet list.

        Called in Phase 2 after all cabinets from all sources have been
        collected, so Vision LLM materials can match against Excel/DWG
        cabinet numbers in addition to Vision LLM's own cabinets.
        """
        remapped: list[BomLine] = []
        for bl in bom_lines:
            old_no = bl.cabinet_no
            new_no = self._match_cabinet_ref(old_no, known_nos)
            if new_no != old_no:
                bl.derived_from = (
                    bl.derived_from + f":map({old_no}→{new_no})"
                )
                bl.cabinet_no = new_no
            remapped.append(bl)
        return remapped

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

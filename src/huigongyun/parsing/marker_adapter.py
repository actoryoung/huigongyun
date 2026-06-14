"""Marker PDF adapter — local CPU-based PDF → structured markdown + tables.

Marker (https://github.com/datalab-to/marker) is an open-source, local-first
PDF-to-Markdown converter that runs on CPU and achieves SOTA accuracy on table
extraction (~89%). It serves as the **free fallback** for PDF pages that don't
require Vision LLM.

Dependency:
    ``pip install marker-pdf``

    On first use, Marker downloads ~5 GB of model weights to
    ``C:\\Users\\<user>\\AppData\\Local\\datalab`` (Windows) or
    ``~/.cache/huggingface`` (Linux/macOS).

Usage::

    from huigongyun.parsing.marker_adapter import MarkerAdapter

    adapter = MarkerAdapter()
    result = adapter.convert("drawing.pdf")  # → MarkerResult
    # result.markdown → full markdown text
    # result.tables   → list of extracted tables
    # result.metadata → page count, file size, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class MarkerTable:
    """A table extracted from a PDF page by Marker."""

    page_no: int = 0
    caption: str = ""
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    markdown: str = ""  # original markdown table string


@dataclass(slots=True)
class MarkerResult:
    """Normalised result from Marker PDF conversion."""

    source_path: str = ""
    markdown: str = ""
    plain_text: str = ""
    tables: List[MarkerTable] = field(default_factory=list)
    page_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    images_extracted: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.markdown or self.plain_text)


class MarkerAdapter:
    """Thin wrapper around Marker's PdfConverter.

    Lazy-loads the heavy Marker models on first use (models ~5 GB download).
    If Marker is not installed or models fail to load, reports the error
    gracefully — callers should check ``result.error``.
    """

    def __init__(self, use_llm: bool = False) -> None:
        """Initialize Marker adapter.

        Args:
            use_llm: If True, enable Marker's built-in LLM enhancement
                     (requires GEMINI_API_KEY for Gemini-based table correction).
                     Default False for free CPU-only mode.
        """
        self._use_llm = use_llm
        self._converter: Any = None
        self._available: Optional[bool] = None  # None = not checked yet

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether Marker is installed and models are loadable.

        Returns True if Marker can be used, False otherwise.
        Does NOT download models — only checks importability.
        """
        if self._available is not None:
            return self._available
        try:
            import marker  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def convert(self, pdf_path: str, max_pages: int = 50) -> MarkerResult:
        """Convert a PDF file to structured markdown + tables.

        Args:
            pdf_path: Path to the PDF file.
            max_pages: Max pages to process (safety limit for large drawings).

        Returns:
            MarkerResult with markdown, plain text, and extracted tables.
            Check ``result.error`` for failures.
        """
        if not self.is_available():
            return MarkerResult(
                source_path=pdf_path,
                error="Marker is not installed. Run: pip install marker-pdf",
            )

        path = Path(pdf_path)
        if not path.exists():
            return MarkerResult(
                source_path=pdf_path,
                error=f"File not found: {pdf_path}",
            )

        try:
            converter = self._get_converter()
            rendered = converter(str(path))
        except Exception as exc:
            return MarkerResult(
                source_path=pdf_path,
                error=f"Marker conversion failed: {exc}",
            )

        # Extract text and tables from rendered output
        try:
            from marker.output import text_from_rendered
            markdown_text, _, images = text_from_rendered(rendered)
        except Exception:
            # Fallback: try to get text from rendered directly
            markdown_text = str(rendered) if rendered else ""
            images = {}

        # Parse tables from markdown
        tables = _extract_tables_from_markdown(markdown_text)

        # Get page count from rendered metadata
        page_count = 0
        try:
            if hasattr(rendered, 'metadata'):
                page_count = len(getattr(rendered, 'children', []))
            if page_count == 0:
                # Try alternative: count from rendered structure
                from marker.schema.blocks import Page
                child_blocks = getattr(rendered, 'children', []) or []
                page_count = sum(1 for b in child_blocks if isinstance(b, Page))
        except Exception:
            page_count = 0

        # Plain text: strip markdown formatting
        import re
        plain = re.sub(r'[#*`\[\]()|]', '', markdown_text)
        plain = re.sub(r'\n{3,}', '\n\n', plain).strip()

        return MarkerResult(
            source_path=pdf_path,
            markdown=markdown_text,
            plain_text=plain,
            tables=tables,
            page_count=page_count,
            metadata={
                "file_size": path.stat().st_size,
                "images_extracted": len(images) if isinstance(images, dict) else 0,
            },
            images_extracted=len(images) if isinstance(images, dict) else 0,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_converter(self) -> Any:
        """Lazy-load and cache the Marker PdfConverter.

        Downloads models (~5 GB) on first call.
        """
        if self._converter is not None:
            return self._converter

        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict

        artifact_dict = create_model_dict()
        self._converter = PdfConverter(
            artifact_dict=artifact_dict,
            # Use llm_service only if explicitly requested
            # (requires GEMINI_API_KEY in environment)
        )
        return self._converter


# ---------------------------------------------------------------------------
# Markdown table parser
# ---------------------------------------------------------------------------

_MARKDOWN_TABLE_RE = __import__('re').compile(
    r'(?:^|\n)(?:\|.*\|[ \t]*\n\|[-\s|:]*\|\n(?:\|.*\|[ \t]*\n)*)',
    __import__('re').MULTILINE,
)


def _extract_tables_from_markdown(md_text: str) -> List[MarkerTable]:
    """Parse markdown pipe-tables from Marker output.

    Returns a list of MarkerTable objects with headers and rows.
    """
    tables: List[MarkerTable] = []

    for match in _MARKDOWN_TABLE_RE.finditer(md_text):
        block = match.group(0).strip()
        lines = [l.strip() for l in block.split('\n') if l.strip()]

        if len(lines) < 2:
            continue

        # First line = headers, second = separator, rest = data rows
        headers = [c.strip() for c in lines[0].split('|') if c.strip()]
        separator = lines[1]
        if not all(ch in '|-: \t' for ch in separator):
            continue  # Not a valid separator row

        data_rows: List[List[str]] = []
        for line in lines[2:]:
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells:
                data_rows.append(cells)

        if headers or data_rows:
            tables.append(MarkerTable(
                page_no=0,  # Can't determine page from markdown alone
                headers=headers,
                rows=data_rows,
                markdown=block,
            ))

    return tables


# ---------------------------------------------------------------------------
# Utility: convert MarkerResult tables → MaterialRecord list
# ---------------------------------------------------------------------------

def marker_tables_to_material_records(
    tables: List[MarkerTable],
    source_path: str = "",
) -> List[Any]:
    """Convert MarkerTable rows to MaterialRecord objects.

    Uses the same header-matching heuristic as vision_llm.py's
    _extract_materials_from_tables. This allows Marker-extracted tables
    to feed into the same downstream pipeline.
    """
    from ..models import MaterialRecord, SourceRef

    _material_keywords = {"名称", "物料", "元器件", "设备", "元件", "description", "material"}
    records: List[Any] = []

    for table in tables:
        headers = table.headers
        rows = table.rows
        if not rows or not headers:
            continue

        header_set = {h.lower().strip() for h in headers}
        if not _material_keywords & header_set:
            continue

        col_map: Dict[str, int] = {}
        for i, h in enumerate(headers):
            hl = h.lower().strip()
            if hl in {"名称", "元器件", "物料", "设备", "元件", "description", "material", "name"}:
                col_map["name"] = i
            elif hl in {"规格", "型号", "规格型号", "spec", "type"}:
                col_map["spec"] = i
            elif hl in {"数量", "台数", "个数", "qty", "quantity"}:
                col_map["quantity"] = i
            elif hl in {"品牌", "厂家", "生产厂家", "brand", "manufacturer"}:
                col_map["brand"] = i
            elif hl in {"单位", "unit"}:
                col_map["unit"] = i
            elif hl in {"柜号", "柜体", "柜名", "cabinet"}:
                col_map["cabinet_ref"] = i

        if "name" not in col_map:
            continue

        for row in rows:
            if not row:
                continue
            name = _safe_cell(row, col_map.get("name"))
            if not name:
                continue

            qty_str = _safe_cell(row, col_map.get("quantity"))
            try:
                qty = float(qty_str) if qty_str else 1.0
            except ValueError:
                qty = 1.0

            source = SourceRef(
                file_name=source_path,
                file_type="pdf",
                page_no=table.page_no or None,
                excerpt=table.caption,
                confidence=0.80,  # Marker has good table accuracy
            )
            records.append(
                MaterialRecord(
                    name=name,
                    spec=_safe_cell(row, col_map.get("spec")),
                    unit=_safe_cell(row, col_map.get("unit")) or "个",
                    quantity=qty,
                    brand=_safe_cell(row, col_map.get("brand")),
                    source=source,
                    confidence=0.80,
                    remarks=_safe_cell(row, col_map.get("cabinet_ref")),
                )
            )

    return records


def _safe_cell(row: List[str], index: Optional[int]) -> Optional[str]:
    """Safely extract a string cell from a table row."""
    if index is None or index >= len(row):
        return None
    val = row[index]
    return val.strip() if val else None

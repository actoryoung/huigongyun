from __future__ import annotations

from .base import ScaffoldFormatParser


class DwgSourceParser(ScaffoldFormatParser):
    """DWG/DXF source adapter skeleton.

    Input boundary: .dwg and .dxf files only.
    Future implementation: conversion or rendering to images/PDF, drawing-region
    detection, and geometry-to-text extraction.
    """

    input_kind = "dwg"
    source_format = "dwg"
    message = "DWG parsing is reserved for later conversion, rendering, and graphic extraction."

    def supported_suffixes(self) -> set[str]:
        return {".dwg", ".dxf"}
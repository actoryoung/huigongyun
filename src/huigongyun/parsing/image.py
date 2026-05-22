from __future__ import annotations

from .base import ScaffoldFormatParser


class ImageSourceParser(ScaffoldFormatParser):
    """Image source adapter skeleton.

    Input boundary: common raster image formats only.
    Future implementation: OCR, de-skew, region detection, caption parsing, and
    image-to-text provenance mapping.
    """

    input_kind = "image"
    source_format = "image"
    message = "Image parsing is reserved for later OCR and layout analysis."

    def supported_suffixes(self) -> set[str]:
        return {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
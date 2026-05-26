"""Tesseract OCR adapter PoC.

This module provides a small adapter around pytesseract/pdf2image to produce a
standard intermediate representation: pages -> blocks (bbox,text,confidence),
and a concatenated plain_text field.
"""
from typing import Any, Dict, List


class TesseractAdapter:
    @staticmethod
    def _parse_tesseract_dict(tdict: Dict[str, List[Any]]) -> (List[Dict[str, Any]], str):
        texts = tdict.get('text', []) or []
        lefts = tdict.get('left', []) or []
        tops = tdict.get('top', []) or []
        widths = tdict.get('width', []) or []
        heights = tdict.get('height', []) or []
        confs = tdict.get('conf', []) or []

        blocks = []
        plain_parts = []
        for i, raw in enumerate(texts):
            text = (raw or '').strip()
            if not text:
                continue
            try:
                left = int(lefts[i])
                top = int(tops[i])
                width = int(widths[i])
                height = int(heights[i])
            except Exception:
                left = top = width = height = None
            try:
                conf_raw = confs[i]
                conf = None if conf_raw in (None, '', '-1') else float(conf_raw)
            except Exception:
                conf = None
            blocks.append({'bbox': [left, top, width, height], 'text': text, 'confidence': conf})
            plain_parts.append(text)
        return blocks, ' '.join(plain_parts)

    @staticmethod
    def image_to_dict(image_path: str) -> Dict[str, Any]:
        try:
            from PIL import Image
        except Exception as e:
            raise RuntimeError('Pillow is required to open images. Install with: pip install Pillow') from e

        try:
            img = Image.open(image_path)
        except Exception as e:
            raise RuntimeError(f'Failed to open image {image_path}: {e}') from e

        size = getattr(img, 'size', (None, None))
        width, height = (size[0], size[1]) if size else (None, None)

        try:
            import pytesseract
        except Exception as e:
            raise RuntimeError('pytesseract python package is required. Install with: pip install pytesseract') from e

        try:
            out_type = getattr(pytesseract, 'Output', None)
            if out_type is not None:
                out = pytesseract.image_to_data(img, output_type=out_type.DICT)
            else:
                out = pytesseract.image_to_data(img)
        except Exception as e:
            # Attempt to detect tesseract missing
            try:
                from pytesseract import TesseractNotFoundError
                if isinstance(e, TesseractNotFoundError):
                    raise RuntimeError('Tesseract binary not found. Install system package, e.g. `sudo apt install tesseract-ocr`') from e
            except Exception:
                pass
            raise RuntimeError(f'pytesseract failed while processing image: {e}') from e

        blocks, plain = TesseractAdapter._parse_tesseract_dict(out)
        return {'pages': [{'page': 1, 'width': width, 'height': height, 'blocks': blocks}], 'plain_text': plain}

    @staticmethod
    def pdf_to_dict(pdf_path: str, dpi: int = 300) -> Dict[str, Any]:
        try:
            import pdf2image
        except Exception as e:
            raise RuntimeError('pdf2image is required to render PDF pages. Install with: pip install pdf2image') from e

        try:
            images = pdf2image.convert_from_path(pdf_path, dpi=dpi)
        except Exception as e:
            raise RuntimeError(f'pdf2image failed converting PDF: {e}\nEnsure poppler is installed (e.g. sudo apt install poppler-utils)') from e

        pages = []
        plain_parts = []
        try:
            import pytesseract
        except Exception as e:
            raise RuntimeError('pytesseract python package is required. Install with: pip install pytesseract') from e

        out_type = getattr(pytesseract, 'Output', None)
        for idx, img in enumerate(images, start=1):
            size = getattr(img, 'size', (None, None))
            width, height = (size[0], size[1]) if size else (None, None)
            try:
                if out_type is not None:
                    out = pytesseract.image_to_data(img, output_type=out_type.DICT)
                else:
                    out = pytesseract.image_to_data(img)
            except Exception as e:
                try:
                    from pytesseract import TesseractNotFoundError
                    if isinstance(e, TesseractNotFoundError):
                        raise RuntimeError('Tesseract binary not found. Install system package, e.g. `sudo apt install tesseract-ocr`') from e
                except Exception:
                    pass
                raise RuntimeError(f'pytesseract failed while processing PDF page: {e}') from e

            blocks, plain = TesseractAdapter._parse_tesseract_dict(out)
            pages.append({'page': idx, 'width': width, 'height': height, 'blocks': blocks})
            if plain:
                plain_parts.append(plain)

        return {'pages': pages, 'plain_text': '\n'.join(plain_parts)}

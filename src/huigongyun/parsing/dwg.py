"""DWG/DXF 格式解析占位实现。

当前为占位解析器，声明对 .dwg/.dxf 文件的支持。未来可扩展为将图纸
转换或渲染为图像/PDF、绘图区域检测以及几何到文本的抽取。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import subprocess
import shlex
import os

import re as _re

from .base import ScaffoldFormatParser
from ..models import ProjectDocument


def _decode_mtext(text: str) -> str:
    """Decode \\U+XXXX Unicode escapes in AutoCAD MTEXT."""
    return _re.sub(
        r'\\U\+([0-9A-Fa-f]{4})',
        lambda m: chr(int(m.group(1), 16)),
        str(text)
    )


def _extract_texts_from_dxf(msp) -> tuple[list[str], list[dict]]:
    """从 DXF 模型空间提取 TEXT/MTEXT 实体。

    Returns:
        (all_texts, records): 文本列表和结构化记录列表。
        记录格式: {"text": str, "type": "TEXT"|"MTEXT", "layer": str}
    """
    texts: list[str] = []
    records: list[dict] = []

    for entity_type, attr_extractor in [
        ("TEXT", lambda e: e.dxf.text if hasattr(e.dxf, 'text') else None),
        ("MTEXT", lambda e: (
            _decode_mtext(e.plain_text()) if hasattr(e, 'plain_text')
            else _decode_mtext(e.text) if hasattr(e, 'text')
            else _decode_mtext(e.dxf.text) if hasattr(e.dxf, 'text')
            else None
        )),
    ]:
        try:
            for e in msp.query(entity_type):
                txt = attr_extractor(e)
                if txt and str(txt).strip():
                    clean = str(txt).strip()
                    texts.append(clean)
                    records.append({
                        "text": clean,
                        "type": entity_type,
                        "layer": e.dxf.layer if hasattr(e.dxf, 'layer') else "0",
                    })
        except Exception:
            pass

    return texts, records


class DwgConverter:
    """DWG 转换包装器：DWG → DXF 转换。

    优先级：
      1. 系统 `dwg2dxf` 命令（LibreDWG）
      2. 环境变量 `DWG2DXF_CMD`（模板命令，需包含 `{input}` 和 `{output}` 占位符）
      3. Docker ODA converter 镜像（需 docker 环境）

    支持通过 `DWG2DXF_CMD` 或预装的 LibreDWG 二进制进行本地转换。
    """

    # Known binary names in priority order
    _BINARY_NAMES = ["dwg2dxf", "dwg2dxf.exe"]

    @staticmethod
    def _find_binary() -> Optional[str]:
        """查找可用的 dwg2dxf 二进制。"""
        import shutil
        for name in DwgConverter._BINARY_NAMES:
            path = shutil.which(name)
            if path:
                return path
        # Check common install locations
        for loc in ["/usr/local/bin/dwg2dxf", "/usr/bin/dwg2dxf"]:
            if os.path.isfile(loc) and os.access(loc, os.X_OK):
                return loc
        return None

    def convert_dwg_to_dxf(self, dwg_path: str, out_dir: Optional[str] = None) -> Optional[str]:
        src = Path(dwg_path)
        if out_dir is None:
            out_dir = str(src.parent)
        out_path = Path(out_dir) / (src.stem + ".dxf")

        # Try system dwg2dxf binary first (LibreDWG)
        binary = self._find_binary()
        if binary:
            try:
                result = subprocess.run(
                    [binary, str(src), "-o", str(out_path)],
                    capture_output=True, text=True, timeout=120,
                )
                if out_path.exists() and out_path.stat().st_size > 0:
                    # Note: LibreDWG may emit errors on newer DWG but still produce DXF
                    return str(out_path)
            except (subprocess.TimeoutExpired, Exception):
                pass

        # Try env-configured command
        cmd_template = os.environ.get("DWG2DXF_CMD")
        if cmd_template:
            cmd = cmd_template.format(input=str(src), output=str(out_path))
            try:
                subprocess.run(shlex.split(cmd), check=True, timeout=120)
                if out_path.exists():
                    return str(out_path)
            except Exception:
                pass

        return None


class DwgSourceParser(ScaffoldFormatParser):
    """DWG/DXF 源解析器。

    行为：当输入为 DXF 并且环境中安装了 `ezdxf` 时，会尝试解析模型空间中的
    文本实体（TEXT/MTEXT）并返回简要的文本提取结果。对于原生 DWG 文件，
    尝试调用 `DwgConverter` 进行转换，转换成功后继续解析转换产物，否则返回
    `requires_conversion` 的标记。
    """

    input_kind = "dwg"
    source_format = "dwg"
    message = "DWG 解析：DXF 可用时会尝试提取文本；DWG 通常需要外部转换。"

    def supported_suffixes(self) -> set[str]:
        return {".dwg", ".dxf"}

    def parse(self, input_path: str) -> ProjectDocument:
        path = Path(input_path)
        suffix = path.suffix.lower()

        # ── Try DXF direct parsing (ezdxf) ──
        dxf_path = str(path)
        needs_conversion = False

        if suffix in {".dwg"}:
            converter = DwgConverter()
            try:
                converted = converter.convert_dwg_to_dxf(str(path))
            except Exception:
                converted = None
            if converted:
                dxf_path = converted
            else:
                needs_conversion = True

        if needs_conversion:
            return ProjectDocument(
                project_name=path.stem or "project",
                files=[str(path)],
                metadata={
                    "input_kind": "dwg",
                    "parse_status": "requires_conversion",
                    "source_format": suffix.lstrip("."),
                    "message": "DWG files require external conversion to DXF. Install LibreDWG (dwg2dxf) or ODA Converter.",
                },
            )

        # ── Parse DXF with ezdxf ──
        try:
            import ezdxf  # type: ignore
        except Exception:
            return super().parse(input_path)

        try:
            dxf_doc = ezdxf.readfile(dxf_path)
        except Exception:
            return ProjectDocument(
                project_name=path.stem or "project",
                files=[str(path)],
                metadata={
                    "input_kind": "dwg",
                    "parse_status": "error",
                    "source_format": suffix.lstrip("."),
                    "message": f"Failed to read DXF with ezdxf: {dxf_path}",
                },
            )

        try:
            msp = dxf_doc.modelspace()
            texts, records = _extract_texts_from_dxf(msp)
        except Exception:
            texts, records = [], []

        # ── Extract cabinet/electrical keywords ──
        el_keywords = [
            "柜", "箱", "断路器", "开关", "电流", "电压", "母排", "铜排",
            "进线", "出线", "母联", "补偿", "馈线", "配电", "UPS",
            "Blok", "施耐德", "ABB", "NSX", "MT", "ATS", "SPD",
            "变压器", "发电", "IDC", "机房", "系统", "电源", "旁路", "主路",
            "PE", "N排", "PEN", "负荷", "容量", "kW", "kVA", "kA",
        ]
        electrical_texts = sorted(set(
            t for t in texts if any(kw in t for kw in el_keywords)
        ))

        return ProjectDocument(
            project_name=path.stem or "project",
            files=[str(path)],
            metadata={
                "input_kind": "dwg",
                "parse_status": "ok",
                "source_format": suffix.lstrip("."),
                "conversion_used": suffix in {".dwg"},
                "text_count": len(texts),
                "electrical_text_count": len(electrical_texts),
                "texts": texts[:200],
                "electrical_texts": electrical_texts[:100],
                "text_records": records[:200],
            },
        )
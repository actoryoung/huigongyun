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

from .base import ScaffoldFormatParser
from ..models import ProjectDocument


class DwgConverter:
    """DWG 转换包装器示例。

    实现尝试使用环境中配置的转换命令将 DWG 转换为 DXF。默认行为是检查
    环境变量 `DWG2DXF_CMD`（模板命令，需包含 `{input}` 和 `{output}` 占位符）
    或尝试 docker 命令（需宿主机支持），以便在 CI 中通过容器化方式运行。

    本示例目标是提供可被测试/替换的转换接口；生产部署应使用稳定的
    ODA converter 镜像或预装的 libredwg 二进制。
    """

    def convert_dwg_to_dxf(self, dwg_path: str, out_dir: Optional[str] = None) -> Optional[str]:
        src = Path(dwg_path)
        if out_dir is None:
            out_dir = str(src.parent)
        out_path = Path(out_dir) / (src.stem + ".dxf")

        cmd_template = os.environ.get("DWG2DXF_CMD")
        if cmd_template:
            cmd = cmd_template.format(input=str(src), output=str(out_path))
            try:
                subprocess.run(shlex.split(cmd), check=True)
                if out_path.exists():
                    return str(out_path)
            except Exception:
                return None

        # Try dockerized converter as a last resort (non-blocking example)
        docker_img = os.environ.get("DWG_CONVERTER_DOCKER_IMAGE")
        if docker_img:
            # mount input dir and run conversion inside docker
            try:
                mount_dir = str(src.parent)
                docker_cmd = (
                    f"docker run --rm -v {mount_dir}:/data {docker_img} /data/{src.name} /data/{out_path.name}"
                )
                subprocess.run(shlex.split(docker_cmd), check=True)
                if out_path.exists():
                    return str(out_path)
            except Exception:
                return None

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

        if suffix == ".dxf":
            try:
                import ezdxf  # type: ignore
            except Exception:
                return super().parse(input_path)

            try:
                doc = ezdxf.readfile(str(path))
            except Exception:
                return ProjectDocument(
                    project_name=path.stem or "project",
                    files=[str(path)],
                    metadata={
                        "input_kind": "dwg",
                        "parse_status": "error",
                        "source_format": "dxf",
                        "message": "Failed to read DXF with ezdxf.",
                    },
                )

            texts: list[str] = []
            try:
                msp = doc.modelspace()
                for e in msp.query('TEXT MTEXT'):
                    txt = getattr(e, 'text', None) or getattr(e, 'plain_text', None)
                    if callable(txt):
                        try:
                            txt = txt()
                        except Exception:
                            txt = None
                    if txt:
                        texts.append(str(txt))
            except Exception:
                texts = []

            return ProjectDocument(
                project_name=path.stem or "project",
                files=[str(path)],
                metadata={
                    "input_kind": "dwg",
                    "parse_status": "ok",
                    "source_format": "dxf",
                    "text_count": len(texts),
                    "texts": texts[:50],
                },
            )

        # For native .dwg files, attempt conversion
        if suffix == ".dwg":
            converter = DwgConverter()
            try:
                converted = converter.convert_dwg_to_dxf(str(path))
            except Exception:
                converted = None

            if converted:
                # delegate to parser for the converted DXF
                return self.parse(str(converted))

            return ProjectDocument(
                project_name=path.stem or "project",
                files=[str(path)],
                metadata={
                    "input_kind": "dwg",
                    "parse_status": "requires_conversion",
                    "source_format": "dwg",
                    "message": "DWG files require external conversion to DXF/PDF (ODA/libredwg).",
                },
            )

        return super().parse(input_path)
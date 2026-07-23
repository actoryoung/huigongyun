"""Vision LLM adapter for CAD vector PDF / image-based electrical drawing recognition.

This module provides a unified interface for calling Vision-capable Large Language
Models (GPT-4o, Claude Vision, Gemini Vision) to extract structured information
from rendered electrical drawing pages — cabinets, materials, tables, and
annotations — that traditional OCR cannot reliably handle.

Provider selection:
    Set the environment variable ``VISION_LLM_PROVIDER`` to one of:
    ``openai`` (default), ``anthropic``, or ``google``.

    API keys are read from:
    - ``OPENAI_API_KEY`` for OpenAI (GPT-4o)
    - ``ANTHROPIC_API_KEY`` for Anthropic (Claude Sonnet/Opus)
    - ``GOOGLE_API_KEY`` for Google (Gemini Vision)

    Optional config via env:
    - ``VISION_LLM_MODEL`` — override the default model name per provider
    - ``VISION_LLM_MAX_TOKENS`` — max output tokens (default 4096)
    - ``VISION_LLM_TEMPERATURE`` — sampling temperature (default 0.0 for deterministic)

Architecture:
    VisionLLMBackend (Protocol)
        ├── OpenAIBackend   (GPT-4o / GPT-4o-mini)
        ├── AnthropicBackend (Claude Sonnet / Opus)
        └── GoogleBackend    (Gemini 2.5 Flash / Pro)

    VisionLLMExtractor
        Uses a backend to call the API, parses structured JSON from the response,
        and maps it to domain models (CabinetRecord, MaterialRecord, SourceRef).
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from ..models import CabinetRecord, MaterialRecord, SourceRef


# ---------------------------------------------------------------------------
# JSON Schema for structured electrical-drawing extraction
# ---------------------------------------------------------------------------

EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "page_summary": {
            "type": "string",
            "description": "One-sentence summary of what this page shows (e.g. '一次系统图 — 进线柜AA1至母联柜AA5')",
        },
        "cabinets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cabinet_no": {"type": "string", "description": "柜号, e.g. AA1, K1-01, 1AA01"},
                    "cabinet_type": {
                        "type": "string",
                        "description": "柜型分类: 进线柜/出线柜/母联柜/MCC柜/变频柜/补偿柜/ATS柜/配电箱/其他",
                    },
                    "rated_current": {"type": "string", "description": "额定电流, e.g. 2000A, 630A. 留空如未标注."},
                    "dimensions": {"type": "string", "description": "外形尺寸 W×D×H (mm), 留空如未标注."},
                    "circuit_count": {"type": "integer", "description": "回路数, 留空如未标注."},
                    "grounding_mode": {"type": "string", "description": "接地方式 TN-S/TN-C/TT/IT, 留空如未标注."},
                    "page_region": {"type": "string", "description": "柜体在页面中的大致位置, 如 '左上角' / '中间偏右'"},
                },
                "required": ["cabinet_no"],
            },
        },
        "materials": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cabinet_ref": {"type": "string", "description": "所属柜号, 必须与上方 cabinets 中的 cabinet_no 一致; 如无法确定柜号填 '未知'"},
                    "name": {"type": "string", "description": "元器件名称, 如 '框架断路器' / '塑壳断路器' / '电流互感器'"},
                    "spec": {"type": "string", "description": "规格型号, 如 '3P 250A 36kA' / '2000/5A 15VA'"},
                    "brand": {"type": "string", "description": "品牌或厂家, 如 '施耐德' / 'ABB' / '正泰'; 留空如未标注"},
                    "quantity": {"type": "number", "description": "数量, 默认 1"},
                    "unit": {"type": "string", "description": "单位: 台/个/套/米/只; 默认 '个'"},
                },
                "required": ["name"],
            },
        },
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "caption": {"type": "string", "description": "表格标题或上下文描述"},
                    "headers": {"type": "array", "items": {"type": "string"}},
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "description": "页面中发现的表格数据; 如无表格则为空数组",
        },
        "annotations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "页面中值得注意的技术说明文字、注释、品牌约束、接地说明等",
        },
    },
    "required": ["cabinets", "materials"],
}

# ---------------------------------------------------------------------------
# System prompt for electrical drawings
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
你是一位电气成套设备图纸审阅专家。你将看到一页低压电气成套项目的图纸（以图片形式提供），
可能是系统图、布置图、二次图或配置说明。

请仔细观察图纸内容，提取以下信息并以严格的JSON格式返回：

1. **柜体 (cabinets)**：找到图纸中出现的所有电气柜。
   - 柜号通常标注在柜体符号旁边，如 "AA1"、"K1-01"、"1AA01"
   - 柜型判断：进线处为进线柜，馈出回路的为出线柜，母联开关处为母联柜，
     标注 MCC / 变频器 / 电容器 / ATS 的按标注分类
   - 额定电流如果在图纸上有标注（如 "2000A"、"630A"）请提取

2. **元器件/物料 (materials)**：列出能识别的元器件。
   - 包括但不限于：断路器（框架/塑壳/微型）、接触器、互感器、继电器、
     隔离开关、避雷器、铜排、母排、绝缘子、线缆等
   - 如果能识别型号规格（如 "NSX250F 3P"、"BH-0.66 2000/5A"），填入spec字段
   - 品牌/厂家标注在元器件旁边或图框标题栏中
   - 确保 cabinet_ref 与 cabinets 中的 cabinet_no 对应

3. **表格 (tables)**：如果页面中有材料表、设备表、图例表等表格，提取其内容。

4. **技术说明 (annotations)**：提取页面中的注释文字，包括品牌要求、
   防护等级(IPxx)、接地方式、安装说明等。

要点：
- 不要编造信息；无法确定的字段留空（null或空字符串）
- 柜号是核心关联字段，务必准确提取
- 中文内容用中文输出，型号规格保留原始写法
"""

# ---------------------------------------------------------------------------
# Backend protocol & implementations
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class VisionLLMResponse:
    """Normalised response from any Vision LLM backend."""

    raw_text: str
    parsed_json: Optional[Dict[str, Any]] = None
    model_used: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


class VisionLLMBackend(Protocol):
    """Protocol for Vision LLM provider backends."""

    def analyze_image(
        self,
        image_base64: str,
        media_type: str,
        system_prompt: str,
        json_schema: Optional[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> VisionLLMResponse:
        """Send an image + prompt to the LLM and return a normalised response."""
        ...


# ---------------------------------------------------------------------------
# OpenAI (GPT-4o / GPT-4o-mini)
# ---------------------------------------------------------------------------

_OPENAI_MODEL = os.environ.get("VISION_LLM_MODEL") or "gpt-4o"


class OpenAIBackend:
    """GPT-4o / GPT-4o-mini Vision backend.

    Requires ``OPENAI_API_KEY`` environment variable and the ``openai`` package.

    Compat mode (for third-party OpenAI-compatible APIs):
        Set ``VISION_LLM_OPENAI_COMPAT=1`` to skip native ``response_format``
        (which many third-party proxies don't support) and instead inject the
        JSON Schema into the system prompt.  Also set ``OPENAI_BASE_URL`` to
        point to the third-party endpoint.
    """

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get("OPENAI_API_KEY")
        self._model: str = _OPENAI_MODEL
        self._client: Any = None
        self._compat_mode: bool = os.environ.get("VISION_LLM_OPENAI_COMPAT", "").strip() in (
            "1", "true", "yes", "on"
        )
        # Timeout for third-party APIs (default 120s; override with VISION_LLM_TIMEOUT)
        self._timeout: float = float(os.environ.get("VISION_LLM_TIMEOUT", "120"))
        # Retry on connection errors (third-party APIs can be flaky)
        self._max_retries: int = int(os.environ.get("VISION_LLM_RETRIES", "2"))

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise RuntimeError(
                "openai package is required for OpenAI Vision backend. "
                "Install with: pip install openai"
            )
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is required for OpenAI Vision backend."
            )
        # OPENAI_BASE_URL is read automatically by the OpenAI SDK from the
        # environment — no explicit base_url parameter needed here.
        self._client = OpenAI(api_key=self._api_key, timeout=self._timeout, max_retries=0)
        return self._client

    def analyze_image(
        self,
        image_base64: str,
        media_type: str,
        system_prompt: str,
        json_schema: Optional[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> VisionLLMResponse:
        client = self._ensure_client()

        # Compat mode: inject JSON Schema into the system prompt (like the
        # Anthropic backend does) because many third-party proxies don't
        # support native ``response_format``.
        effective_system = system_prompt
        if self._compat_mode and json_schema is not None:
            effective_system += (
                "\n\n**你必须严格按以下 JSON Schema 输出，只输出 JSON，不要包含任何解释文字：**\n"
                + json.dumps(json_schema, ensure_ascii=False, indent=2)
            )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": effective_system},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
                    },
                    {"type": "text", "text": "请按照系统提示提取图纸中的结构化信息，以 JSON 格式返回。"},
                ],
            },
        ]

        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if not self._compat_mode and json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "electrical_drawing_extraction",
                    "schema": json_schema,
                    "strict": True,
                },
            }

        resp = None
        last_error: Optional[str] = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self._max_retries:
                    import time as _time
                    wait = (attempt + 1) * 5  # 5, 10, 15, … seconds back-off
                    _time.sleep(wait)
                    continue
                # Last attempt failed — propagate to outer handler
                raise

        if resp is None:
            # Shouldn't happen, but guard against missing retry coverage
            return VisionLLMResponse(
                raw_text="",
                error=last_error or "No response from Vision LLM",
            )

        content: str = resp.choices[0].message.content or ""
        parsed = _parse_json_from_text(content)

        return VisionLLMResponse(
            raw_text=content,
            parsed_json=parsed,
            model_used=self._model,
            usage={
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(resp.usage, "completion_tokens", 0),
            },
            error=None if parsed is not None else "Failed to parse JSON from response",
        )


# ---------------------------------------------------------------------------
# Anthropic (Claude Sonnet / Opus)
# ---------------------------------------------------------------------------

_ANTHROPIC_MODEL = os.environ.get("VISION_LLM_MODEL") or "claude-sonnet-4-6"


class AnthropicBackend:
    """Claude Vision backend.

    Requires ``ANTHROPIC_API_KEY`` environment variable and the ``anthropic`` package.
    """

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")
        self._model: str = _ANTHROPIC_MODEL
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError:
            raise RuntimeError(
                "anthropic package is required for Anthropic Vision backend. "
                "Install with: pip install anthropic"
            )
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable is required for Anthropic Vision backend."
            )
        self._client = Anthropic(api_key=self._api_key)
        return self._client

    def analyze_image(
        self,
        image_base64: str,
        media_type: str,
        system_prompt: str,
        json_schema: Optional[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> VisionLLMResponse:
        client = self._ensure_client()

        # Build enhanced prompt: append schema instruction to system prompt
        # (Anthropic doesn't have native JSON Schema enforcement like OpenAI,
        #  so we inject the schema into the system prompt)
        enhanced_system = system_prompt
        if json_schema is not None:
            enhanced_system += (
                "\n\n**你必须严格按以下 JSON Schema 输出，不要输出任何非 JSON 内容：**\n"
                + json.dumps(json_schema, ensure_ascii=False, indent=2)
            )

        resp = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=enhanced_system,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "请按照系统提示提取图纸中的结构化信息，以 JSON 格式返回，不要包含任何解释文字。",
                        },
                    ],
                },
            ],
        )

        content: str = ""
        for block in resp.content:
            if getattr(block, "type", "") == "text":
                content += block.text

        parsed = _parse_json_from_text(content)

        return VisionLLMResponse(
            raw_text=content,
            parsed_json=parsed,
            model_used=self._model,
            usage={
                "input_tokens": getattr(resp.usage, "input_tokens", 0),
                "output_tokens": getattr(resp.usage, "output_tokens", 0),
            },
            error=None if parsed is not None else "Failed to parse JSON from response",
        )


# ---------------------------------------------------------------------------
# Google (Gemini Vision)
# ---------------------------------------------------------------------------

_GOOGLE_MODEL = os.environ.get("VISION_LLM_MODEL") or "gemini-2.5-flash"


class GoogleBackend:
    """Gemini Vision backend.

    Requires ``GOOGLE_API_KEY`` environment variable and the ``google-generativeai`` package.
    """

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get("GOOGLE_API_KEY")
        self._model: str = _GOOGLE_MODEL
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:
            raise RuntimeError(
                "google-generativeai package is required for Google Vision backend. "
                "Install with: pip install google-generativeai"
            )
        if not self._api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY environment variable is required for Google Vision backend."
            )
        genai.configure(api_key=self._api_key)
        self._client = genai
        return self._client

    def analyze_image(
        self,
        image_base64: str,
        media_type: str,
        system_prompt: str,
        json_schema: Optional[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> VisionLLMResponse:
        genai = self._ensure_client()

        # Build prompt with schema
        prompt_text = system_prompt
        if json_schema is not None:
            prompt_text += (
                "\n\n**你必须严格按以下 JSON Schema 输出，只输出 JSON，不要输出任何解释文字：**\n"
                + json.dumps(json_schema, ensure_ascii=False, indent=2)
            )

        image_bytes = base64.b64decode(image_base64)

        generation_config = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            "response_mime_type": "application/json" if json_schema else "text/plain",
        }

        model = genai.GenerativeModel(
            model_name=self._model,
            system_instruction=system_prompt,
        )

        resp = model.generate_content(
            contents=[prompt_text, {"mime_type": media_type, "data": image_bytes}],
            generation_config=generation_config,
        )

        content: str = resp.text or ""
        parsed = _parse_json_from_text(content)

        usage: Dict[str, int] = {}
        try:
            usage_meta = getattr(resp, "usage_metadata", None)
            if usage_meta:
                usage = {
                    "prompt_tokens": getattr(usage_meta, "prompt_token_count", 0),
                    "completion_tokens": getattr(usage_meta, "candidates_token_count", 0),
                }
        except Exception:
            pass

        return VisionLLMResponse(
            raw_text=content,
            parsed_json=parsed,
            model_used=self._model,
            usage=usage,
            error=None if parsed is not None else "Failed to parse JSON from response",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Attempt to extract a JSON object from LLM response text.

    Handles cases where the model wraps JSON in markdown fences or
    prepends explanatory text.
    """
    if not text:
        return None

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` fence
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _image_to_base64(image: Any, image_format: str = "JPEG") -> tuple[str, str]:
    """Convert a PIL Image or file path to base64-encoded string.

    Returns:
        (base64_string, media_type) — e.g. ("iVBOR...", "image/jpeg")
    """
    from PIL import Image

    if isinstance(image, (str, Path)):
        path = Path(image)
        with open(path, "rb") as fh:
            raw = fh.read()
        # Determine media type from suffix
        suffix_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        media_type = suffix_map.get(path.suffix.lower(), "image/png")
        return base64.b64encode(raw).decode("ascii"), media_type

    # PIL Image — use JPEG for smaller payload (third-party APIs often have
    # low body-size limits; PNG at 300-DPI CAD page can be >5 MB base64).
    buf = io.BytesIO()
    fmt = (image_format or "JPEG").upper()
    save_kwargs: dict[str, Any] = {"format": fmt}
    if fmt == "JPEG":
        save_kwargs["quality"] = 85
    image.save(buf, **save_kwargs)
    media_type = f"image/{fmt.lower()}"
    return base64.b64encode(buf.getvalue()).decode("ascii"), media_type


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

_BACKEND_REGISTRY: Dict[str, type] = {
    "openai": OpenAIBackend,
    "anthropic": AnthropicBackend,
    "google": GoogleBackend,
}


@dataclass
class VisionLLMExtractor:
    """High-level extractor: page image → structured domain records.

    Usage::

        extractor = VisionLLMExtractor()
        # Render a PDF page to PIL Image, then:
        result = extractor.extract_from_image(pil_image, page_no=1, source_path="drawing.pdf")
        # result.cabinets → list[CabinetRecord]
        # result.materials → list[MaterialRecord]
    """

    provider: str = field(default_factory=lambda: os.environ.get("VISION_LLM_PROVIDER", "openai"))
    max_tokens: int = field(
        default_factory=lambda: int(os.environ.get("VISION_LLM_MAX_TOKENS", "4096"))
    )
    temperature: float = field(
        default_factory=lambda: float(os.environ.get("VISION_LLM_TEMPERATURE", "0.0"))
    )
    json_schema: Optional[Dict[str, Any]] = field(default_factory=lambda: EXTRACTION_SCHEMA)
    system_prompt: str = SYSTEM_PROMPT

    _backend: Optional[Any] = field(default=None, repr=False, init=False)

    def _get_backend(self) -> VisionLLMBackend:
        if self._backend is not None:
            return self._backend
        backend_cls = _BACKEND_REGISTRY.get(self.provider.lower())
        if backend_cls is None:
            raise ValueError(
                f"Unknown Vision LLM provider: {self.provider!r}. "
                f"Choose one of: {list(_BACKEND_REGISTRY)}"
            )
        self._backend = backend_cls()
        return self._backend

    def extract_from_image(
        self,
        image: Any,
        page_no: int = 1,
        source_path: str = "",
    ) -> VisionLLMExtractionResult:
        """Analyze a single page image and return structured domain records.

        Args:
            image: A PIL Image, or a file path (str/Path) to a PNG/JPG.
            page_no: Page number (for source tracking).
            source_path: Original PDF/DWG file path (for source tracking).

        Returns:
            VisionLLMExtractionResult with cabinets, materials, and metadata.
        """
        b64, media_type = _image_to_base64(image)
        backend = self._get_backend()

        try:
            response = backend.analyze_image(
                image_base64=b64,
                media_type=media_type,
                system_prompt=self.system_prompt,
                json_schema=self.json_schema,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except Exception as exc:
            return VisionLLMExtractionResult(
                page_no=page_no,
                source_path=source_path,
                error=str(exc),
            )

        if response.error or response.parsed_json is None:
            return VisionLLMExtractionResult(
                page_no=page_no,
                source_path=source_path,
                raw_response=response.raw_text,
                error=response.error or "No structured data extracted",
                usage=response.usage,
                model_used=response.model_used,
            )

        # Map parsed JSON → domain models
        data = response.parsed_json
        cabinets = _build_cabinet_records(
            data.get("cabinets", []), source_path, page_no
        )
        materials = _build_material_records(
            data.get("materials", []), source_path, page_no
        )
        # Also extract materials from tables if present
        table_materials = _extract_materials_from_tables(
            data.get("tables", []), source_path, page_no
        )
        materials.extend(table_materials)

        return VisionLLMExtractionResult(
            page_no=page_no,
            source_path=source_path,
            cabinets=cabinets,
            materials=materials,
            tables=data.get("tables", []),
            annotations=data.get("annotations", []),
            page_summary=data.get("page_summary", ""),
            raw_response=response.raw_text,
            usage=response.usage,
            model_used=response.model_used,
        )


# ---------------------------------------------------------------------------
# Extraction result
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class VisionLLMExtractionResult:
    """Structured result from a single page Vision LLM call."""

    page_no: int = 1
    source_path: str = ""
    cabinets: List[CabinetRecord] = field(default_factory=list)
    materials: List[MaterialRecord] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)
    page_summary: str = ""
    raw_response: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    model_used: str = ""
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def total_items(self) -> int:
        return len(self.cabinets) + len(self.materials)


# ---------------------------------------------------------------------------
# JSON → domain model builders
# ---------------------------------------------------------------------------


def _build_cabinet_records(
    raw_cabinets: List[Dict[str, Any]],
    source_path: str,
    page_no: int,
) -> List[CabinetRecord]:
    """Map parsed cabinet dicts to CabinetRecord domain objects."""
    records: List[CabinetRecord] = []
    for item in raw_cabinets:
        if not isinstance(item, dict):
            continue
        cabinet_no = (item.get("cabinet_no") or "").strip()
        if not cabinet_no:
            continue
        source = SourceRef(
            file_name=source_path,
            file_type="pdf",
            page_no=page_no,
            excerpt=item.get("page_region", ""),
            confidence=0.75,  # Vision LLM base confidence
        )
        records.append(
            CabinetRecord(
                cabinet_no=cabinet_no,
                cabinet_type=item.get("cabinet_type"),
                rated_current=item.get("rated_current"),
                dimensions=item.get("dimensions"),
                circuit_count=item.get("circuit_count"),
                grounding_mode=item.get("grounding_mode"),
                sources=[source] if source.excerpt else [],
                confidence=0.75,
                remarks=f"Vision LLM ({item.get('page_region', '')})" if item.get("page_region") else None,
            )
        )
    return records


def _build_material_records(
    raw_materials: List[Dict[str, Any]],
    source_path: str,
    page_no: int,
) -> List[MaterialRecord]:
    """Map parsed material dicts to MaterialRecord domain objects."""
    records: List[MaterialRecord] = []
    for item in raw_materials:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        source = SourceRef(
            file_name=source_path,
            file_type="pdf",
            page_no=page_no,
            excerpt=item.get("cabinet_ref", ""),
            confidence=0.70,  # Vision LLM medium confidence for materials
        )
        records.append(
            MaterialRecord(
                name=name,
                spec=item.get("spec"),
                unit=item.get("unit") or "个",
                quantity=float(item.get("quantity", 1)),
                brand=item.get("brand"),
                source=source,
                confidence=0.70,
                remarks=f"cabinet_ref: {item.get('cabinet_ref', '未知')}",
            )
        )
    return records


def _extract_materials_from_tables(
    tables: List[Dict[str, Any]],
    source_path: str,
    page_no: int,
) -> List[MaterialRecord]:
    """Extract MaterialRecord rows from table data.

    Heuristic: if a table has headers like ['名称','规格','数量','品牌']
    or similar, treat rows as material entries.
    """
    records: List[MaterialRecord] = []
    # Keywords that suggest a row is a material row
    _material_header_keywords = {"名称", "物料", "元器件", "设备", "元件", "description", "material"}

    for table in tables:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        if not rows or not headers:
            continue

        # Check if this table looks like a material list
        header_set = {h.lower().strip() for h in headers}
        if not _material_header_keywords & header_set:
            continue

        # Map header indices to fields
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
            continue  # Can't determine which column is the material name

        for row in rows:
            if not row or not any(cell.strip() for cell in row if cell):
                continue
            name = _safe_get(row, col_map.get("name"))
            if not name:
                continue
            source = SourceRef(
                file_name=source_path,
                file_type="pdf",
                page_no=page_no,
                excerpt=table.get("caption", ""),
                confidence=0.65,
            )
            qty_str = _safe_get(row, col_map.get("quantity"))
            try:
                qty = float(qty_str) if qty_str else 1.0
            except ValueError:
                qty = 1.0

            records.append(
                MaterialRecord(
                    name=name,
                    spec=_safe_get(row, col_map.get("spec")),
                    unit=_safe_get(row, col_map.get("unit")) or "个",
                    quantity=qty,
                    brand=_safe_get(row, col_map.get("brand")),
                    source=source,
                    confidence=0.65,
                    remarks=_safe_get(row, col_map.get("cabinet_ref")),
                )
            )

    return records


def _safe_get(row: List[str], index: Optional[int]) -> Optional[str]:
    """Safely get a string value from a table row by column index."""
    if index is None or index >= len(row):
        return None
    val = row[index]
    return val.strip() if val else None

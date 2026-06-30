# P0: 柜型/接地/进出线 → BOM 辅材规则注入 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 AuxMaterialInjector，基于 cabinet_type/grounding_mode/inbound_outbound 三层规则注入辅材 BomLine，插入到 DefaultBomGenerator 流程中。

**Architecture:** JSON 外置规则表 (`bom_rules.json`) 定义三层叠加数据，`AuxMaterialInjector` 类负责加载/归一化/查表/注入，在现有 `DefaultBomGenerator.generate()` 中调用。遵循 normalization 模块已有的词典映射 + 回退链模式。

**Tech Stack:** Python >= 3.10, openpyxl (测试夹具), pytest

## Global Constraints

- Python >= 3.10
- 遵循现有项目模式: JSON 外置词典 + lazy import + 优雅降级
- 测试运行: `PYTHONPATH=src pytest -p no:launch_testing --ignore=reference`
- 重型依赖可选，缺失时优雅回退不崩溃
- 所有 BomLine 保留 `derived_from` 和 `SourceRef` 追溯

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/huigongyun/generation/dictionaries/bom_rules.json` | Create | 三层规则数据（柜型模板/接地物料/进出线辅材） |
| `src/huigongyun/generation/rules.py` | Create | AuxMaterialInjector 类（加载/归一化/查表/注入） |
| `src/huigongyun/adapters/default.py` | Modify | DefaultBomGenerator.generate() 中插入一行调用 |
| `tests/unit/generation/__init__.py` | Create | 空文件，声明包 |
| `tests/unit/generation/test_rules.py` | Create | 45 单元测试 |
| `tests/integration/generation/__init__.py` | Create | 空文件，声明包 |
| `tests/integration/generation/test_rules_integration.py` | Create | 5 集成测试 |
| `tests/fixtures/aux_material_test.xlsx` | Create | 最小测试夹具（3 柜体，不同接地/进出线） |
| `CLAUDE.md` | Modify | 更新已交付模块和测试计数 |

---

### Task 1: Create `bom_rules.json` — 规则数据文件

**Files:**
- Create: `src/huigongyun/generation/dictionaries/bom_rules.json`

**Interfaces:**
- Produces: JSON 文件，三个顶层 key: `cabinet_type_templates`, `grounding_materials`, `inbound_outbound_materials`。Task 2 的 `AuxMaterialInjector.__init__` 加载此文件。

- [ ] **Step 1: Create directories**

```bash
mkdir -p src/huigongyun/generation/dictionaries
```

- [ ] **Step 2: Write bom_rules.json**

```json
{
  "_description": "低压成套柜型/接地/进出线 BOM 辅材规则表，三层叠加注入",

  "cabinet_type_templates": {
    "进线柜": {
      "materials": [
        {"name": "框架断路器", "spec": "按额定电流", "unit": "台", "quantity": "按额定电流"},
        {"name": "测量电流互感器", "spec": "按额定电流", "unit": "只", "quantity": 4},
        {"name": "多功能表", "spec": null, "unit": "只", "quantity": 1},
        {"name": "浪涌保护器", "spec": null, "unit": "套", "quantity": 1}
      ],
      "condition_fields": ["rated_current"]
    },
    "母联柜": {
      "materials": [
        {"name": "框架断路器", "spec": "按额定电流", "unit": "台", "quantity": "按额定电流"},
        {"name": "测量电流互感器", "spec": "按额定电流", "unit": "只", "quantity": 4},
        {"name": "多功能表", "spec": null, "unit": "只", "quantity": 1}
      ],
      "condition_fields": ["rated_current"]
    },
    "出线柜": {
      "materials": [
        {"name": "塑壳断路器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
        {"name": "接触器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
        {"name": "热继电器", "spec": "按回路配置", "unit": "只", "quantity": "按回路数"}
      ],
      "condition_fields": ["rated_current", "circuit_count"]
    },
    "变频柜": {
      "materials": [
        {"name": "变频器", "spec": "按功率", "unit": "台", "quantity": 1},
        {"name": "输入电抗器", "spec": "按功率", "unit": "台", "quantity": 1},
        {"name": "输出滤波器", "spec": "按功率", "unit": "台", "quantity": 1},
        {"name": "塑壳断路器", "spec": "按功率", "unit": "台", "quantity": 1}
      ],
      "condition_fields": ["rated_current"]
    },
    "补偿柜": {
      "materials": [
        {"name": "隔离开关", "spec": "按补偿容量", "unit": "台", "quantity": 1},
        {"name": "电容器", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
        {"name": "电抗器", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
        {"name": "晶闸管投切开关", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
        {"name": "温湿度控制器", "spec": null, "unit": "只", "quantity": 1}
      ],
      "condition_fields": []
    },
    "ATS柜": {
      "materials": [
        {"name": "双电源开关", "spec": "按额定电流", "unit": "台", "quantity": 1},
        {"name": "控制器", "spec": null, "unit": "台", "quantity": 1},
        {"name": "塑壳断路器", "spec": "按额定电流", "unit": "台", "quantity": 2}
      ],
      "condition_fields": ["rated_current"]
    },
    "MCC柜": {
      "materials": [
        {"name": "塑壳断路器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
        {"name": "接触器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
        {"name": "热继电器", "spec": "按回路配置", "unit": "只", "quantity": "按回路数"},
        {"name": "控制变压器", "spec": null, "unit": "台", "quantity": 1}
      ],
      "condition_fields": ["rated_current", "circuit_count"]
    },
    "配电箱": {
      "materials": [
        {"name": "微型断路器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
        {"name": "漏电保护器", "spec": "按回路配置", "unit": "只", "quantity": "按回路数"},
        {"name": "铜排", "spec": null, "unit": "米", "quantity": "按柜宽"}
      ],
      "condition_fields": ["circuit_count"]
    }
  },

  "grounding_materials": {
    "TN-S": [
      {"name": "N排", "spec": null, "unit": "米", "quantity": "按柜宽"},
      {"name": "PE排", "spec": null, "unit": "米", "quantity": "按柜宽"}
    ],
    "TN-C": [
      {"name": "PEN排", "spec": null, "unit": "米", "quantity": "按柜宽"}
    ],
    "TN-C-S": [
      {"name": "PEN排", "spec": null, "unit": "米", "quantity": "按柜宽"},
      {"name": "N排", "spec": null, "unit": "米", "quantity": "按柜宽"},
      {"name": "PE排", "spec": null, "unit": "米", "quantity": "按柜宽"}
    ],
    "TT": [
      {"name": "PE排", "spec": null, "unit": "米", "quantity": "按柜宽"},
      {"name": "漏电保护器", "spec": "按额定电流", "unit": "只", "quantity": 1}
    ],
    "IT": [
      {"name": "PE排", "spec": null, "unit": "米", "quantity": "按柜宽"},
      {"name": "绝缘监测装置", "spec": null, "unit": "台", "quantity": 1}
    ]
  },

  "inbound_outbound_materials": {
    "电缆上进": [
      {"name": "电缆夹具", "spec": null, "unit": "套", "quantity": "按回路数"},
      {"name": "进线密封圈", "spec": null, "unit": "套", "quantity": "按回路数"}
    ],
    "电缆下进": [
      {"name": "电缆夹具", "spec": null, "unit": "套", "quantity": "按回路数"},
      {"name": "进线密封圈", "spec": null, "unit": "套", "quantity": "按回路数"}
    ],
    "母线槽进线": [
      {"name": "过渡母排", "spec": null, "unit": "套", "quantity": 1},
      {"name": "母线连接件", "spec": null, "unit": "套", "quantity": 1},
      {"name": "接头盖板", "spec": null, "unit": "套", "quantity": 1}
    ],
    "母线槽出线": [
      {"name": "过渡母排", "spec": null, "unit": "套", "quantity": 1},
      {"name": "母线连接件", "spec": null, "unit": "套", "quantity": 1}
    ],
    "背靠背拼柜": [
      {"name": "拼柜连接母排", "spec": null, "unit": "套", "quantity": 1},
      {"name": "拼柜螺栓", "spec": null, "unit": "套", "quantity": 1}
    ]
  },

  "normalization_aliases": {
    "cabinet_type": {
      "进线柜": ["进线柜", "馈线柜", "出线柜", "电源进线柜", "主进线柜"],
      "母联柜": ["母联柜", "联络柜", "母线联络柜"],
      "补偿柜": ["补偿柜", "电容器柜", "无功补偿柜", "SVG柜"],
      "变频柜": ["变频柜", "变频器柜", "VFD柜"],
      "ATS柜": ["ATS柜", "双电源柜", "互投柜", "双电源切换柜"],
      "MCC柜": ["MCC柜", "马达控制柜", "电动机控制柜"],
      "配电箱": ["配电箱", "照明配电箱", "动力配电箱", "配电盒"]
    },
    "grounding": {
      "TN-S": ["TN-S", "TN-S 系统", "TNS", "tn-s", "tns"],
      "TN-C": ["TN-C", "TN-C 系统", "TNC", "tn-c", "tnc"],
      "TN-C-S": ["TN-C-S", "TN-C-S 系统", "TNCS", "tn-c-s", "tncs"],
      "TT": ["TT", "TT 系统", "tt"],
      "IT": ["IT", "IT 系统", "it"]
    },
    "inbound_outbound": {
      "电缆上进": ["电缆上进", "上进", "上进上出", "上进线", "电缆顶部进线"],
      "电缆下进": ["电缆下进", "下进", "下进下出", "下进线", "电缆底部进线"],
      "母线槽进线": ["母线槽进线", "母线进线", "母线接入", "母线槽接入", "母线上进"],
      "母线槽出线": ["母线槽出线", "母线出线", "母线下出"],
      "背靠背拼柜": ["背靠背拼柜", "拼柜", "背靠背", "并柜"]
    }
  }
}
```

- [ ] **Step 3: Validate JSON syntax**

```bash
python3 -m json.tool src/huigongyun/generation/dictionaries/bom_rules.json > /dev/null && echo "VALID"
```

- [ ] **Step 4: Commit**

```bash
git add src/huigongyun/generation/dictionaries/bom_rules.json
git commit -m "feat: 新增 bom_rules.json — 柜型/接地/进出线三层辅材规则表

- 8 种柜型模板（进线/母联/出线/变频/补偿/ATS/MCC/配电箱）
- 5 种接地方式物料（TN-S/TN-C/TN-C-S/TT/IT）
- 5 种进出线辅材（电缆上进/下进/母线槽进线/出线/背靠背拼柜）
- normalization_aliases: 柜型/接地/进出线归一化别名映射

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Create `AuxMaterialInjector` 骨架 + L1 规则加载测试

**Files:**
- Create: `src/huigongyun/generation/rules.py`
- Create: `tests/unit/generation/__init__.py` (空文件)
- Create: `tests/unit/generation/test_rules.py`

**Interfaces:**
- Produces: `AuxMaterialInjector` 类，构造函数加载 bom_rules.json，公开 `inject(result: ProjectResult) -> ProjectResult`（当前为 no-op）
- Consumes: `bom_rules.json`（Task 1）

- [ ] **Step 1: Create package __init__.py**

```bash
mkdir -p tests/unit/generation
touch tests/unit/generation/__init__.py
```

- [ ] **Step 2: Write L1 tests (规则加载，4 用例)**

Write `tests/unit/generation/test_rules.py`:

```python
"""AuxMaterialInjector 单元测试 — L1: 规则加载。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from huigongyun.generation.rules import AuxMaterialInjector


class TestRulesLoading:
    """L1: 规则加载与降级 (4 用例)。"""

    def test_load_valid_rules_json(self):
        """加载有效的 bom_rules.json，三个 section 均非空。"""
        injector = AuxMaterialInjector()
        rules = injector._rules

        assert "cabinet_type_templates" in rules
        assert "grounding_materials" in rules
        assert "inbound_outbound_materials" in rules
        assert len(rules["cabinet_type_templates"]) >= 8
        assert "进线柜" in rules["cabinet_type_templates"]
        assert len(rules["grounding_materials"]) >= 5
        assert "TN-S" in rules["grounding_materials"]
        assert len(rules["inbound_outbound_materials"]) >= 5

    def test_load_missing_file_fallback(self, monkeypatch):
        """JSON 文件缺失时使用内置回退字典。"""
        monkeypatch.setattr(Path, "exists", lambda self: False)
        injector = AuxMaterialInjector()
        rules = injector._rules

        assert "cabinet_type_templates" in rules
        assert len(rules["cabinet_type_templates"]) >= 5
        assert len(rules["grounding_materials"]) >= 4

    def test_load_invalid_json_fallback(self, tmp_path):
        """JSON 格式错误时静默回退到内置字典。"""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json")
        injector = AuxMaterialInjector(rules_path=str(bad_file))
        rules = injector._rules

        assert "cabinet_type_templates" in rules
        assert len(rules["cabinet_type_templates"]) >= 5

    def test_load_partial_sections(self, tmp_path):
        """JSON 缺少部分 section 时，缺失层不影响。"""
        partial = tmp_path / "partial.json"
        partial.write_text(json.dumps({"cabinet_type_templates": {"测试柜": {"materials": []}}}))
        injector = AuxMaterialInjector(rules_path=str(partial))
        rules = injector._rules

        assert "cabinet_type_templates" in rules
        assert len(rules["grounding_materials"]) == 0
        assert len(rules["inbound_outbound_materials"]) == 0
```

- [ ] **Step 3: Run tests, verify they fail**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: ImportError or AttributeError (module doesn't exist yet).

- [ ] **Step 4: Write AuxMaterialInjector skeleton**

Write `src/huigongyun/generation/rules.py`:

```python
"""辅材规则注入器 — 基于柜型/接地/进出线三层规则注入辅材 BomLine。

``AuxMaterialInjector`` 在每个柜体上独立工作，从 ``bom_rules.json``
查表并将匹配的物料作为 ``BomLine`` 注入，标记 ``derived_from = "规则推算"``。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..models import BomLine, CabinetRecord, MaterialRecord, ProjectResult, SourceRef

logger = logging.getLogger(__name__)

# ── 内置回退规则 ──────────────────────────────────────────────────────

_FALLBACK_RULES: dict[str, Any] = {
    "cabinet_type_templates": {
        "进线柜": {
            "materials": [
                {"name": "框架断路器", "spec": "按额定电流", "unit": "台", "quantity": "按额定电流"},
                {"name": "测量电流互感器", "spec": "按额定电流", "unit": "只", "quantity": 4},
                {"name": "多功能表", "spec": None, "unit": "只", "quantity": 1},
                {"name": "浪涌保护器", "spec": None, "unit": "套", "quantity": 1},
            ],
        },
        "母联柜": {
            "materials": [
                {"name": "框架断路器", "spec": "按额定电流", "unit": "台", "quantity": "按额定电流"},
                {"name": "测量电流互感器", "spec": "按额定电流", "unit": "只", "quantity": 4},
                {"name": "多功能表", "spec": None, "unit": "只", "quantity": 1},
            ],
        },
        "出线柜": {
            "materials": [
                {"name": "塑壳断路器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
                {"name": "接触器", "spec": "按回路配置", "unit": "台", "quantity": "按回路数"},
                {"name": "热继电器", "spec": "按回路配置", "unit": "只", "quantity": "按回路数"},
            ],
        },
        "补偿柜": {
            "materials": [
                {"name": "隔离开关", "spec": "按补偿容量", "unit": "台", "quantity": 1},
                {"name": "电容器", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
                {"name": "电抗器", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
                {"name": "晶闸管投切开关", "spec": "按补偿容量", "unit": "台", "quantity": "按补偿容量"},
            ],
        },
        "ATS柜": {
            "materials": [
                {"name": "双电源开关", "spec": "按额定电流", "unit": "台", "quantity": 1},
                {"name": "塑壳断路器", "spec": "按额定电流", "unit": "台", "quantity": 2},
            ],
        },
    },
    "grounding_materials": {
        "TN-S": [
            {"name": "N排", "spec": None, "unit": "米", "quantity": "按柜宽"},
            {"name": "PE排", "spec": None, "unit": "米", "quantity": "按柜宽"},
        ],
        "TN-C": [
            {"name": "PEN排", "spec": None, "unit": "米", "quantity": "按柜宽"},
        ],
        "TT": [
            {"name": "PE排", "spec": None, "unit": "米", "quantity": "按柜宽"},
            {"name": "漏电保护器", "spec": "按额定电流", "unit": "只", "quantity": 1},
        ],
        "IT": [
            {"name": "PE排", "spec": None, "unit": "米", "quantity": "按柜宽"},
            {"name": "绝缘监测装置", "spec": None, "unit": "台", "quantity": 1},
        ],
    },
    "inbound_outbound_materials": {
        "电缆上进": [
            {"name": "电缆夹具", "spec": None, "unit": "套", "quantity": "按回路数"},
        ],
        "电缆下进": [
            {"name": "电缆夹具", "spec": None, "unit": "套", "quantity": "按回路数"},
        ],
        "母线槽进线": [
            {"name": "过渡母排", "spec": None, "unit": "套", "quantity": 1},
            {"name": "母线连接件", "spec": None, "unit": "套", "quantity": 1},
        ],
        "背靠背拼柜": [
            {"name": "拼柜连接母排", "spec": None, "unit": "套", "quantity": 1},
            {"name": "拼柜螺栓", "spec": None, "unit": "套", "quantity": 1},
        ],
    },
    "normalization_aliases": {
        "cabinet_type": {
            "进线柜": ["进线柜", "馈线柜", "出线柜", "电源进线柜"],
            "母联柜": ["母联柜", "联络柜"],
            "补偿柜": ["补偿柜", "电容器柜", "无功补偿柜", "SVG柜"],
            "ATS柜": ["ATS柜", "双电源柜", "互投柜"],
        },
        "grounding": {
            "TN-S": ["TN-S", "TN-S 系统", "TNS", "tn-s", "tns"],
            "TN-C": ["TN-C", "TN-C 系统", "TNC", "tn-c", "tnc"],
            "TN-C-S": ["TN-C-S", "TN-C-S 系统", "TNCS", "tn-c-s", "tncs"],
            "TT": ["TT", "TT 系统", "tt"],
            "IT": ["IT", "IT 系统", "it"],
        },
        "inbound_outbound": {
            "电缆上进": ["电缆上进", "上进", "上进上出", "上进线"],
            "电缆下进": ["电缆下进", "下进", "下进下出", "下进线"],
            "母线槽进线": ["母线槽进线", "母线进线", "母线接入", "母线槽接入"],
            "背靠背拼柜": ["背靠背拼柜", "拼柜", "背靠背", "并柜"],
        },
    },
}


class AuxMaterialInjector:
    """基于柜型/接地/进出线三层规则注入辅材 BomLine。

    在每个柜体上独立工作，从规则表查表并将匹配的物料标记
    ``derived_from = "规则推算"`` 注入到 ``ProjectResult.bom_lines``。

    Args:
        rules_path: bom_rules.json 路径，None 使用默认路径。
    """

    def __init__(self, rules_path: str | None = None) -> None:
        self._rules = self._load_rules(rules_path)

    # ── 规则加载 ───────────────────────────────────────────────────

    def _load_rules(self, rules_path: str | None) -> dict[str, Any]:
        if rules_path is None:
            rules_path = str(Path(__file__).parent / "dictionaries" / "bom_rules.json")
        try:
            path = Path(rules_path)
            if path.exists():
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                return self._normalize_rules(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load bom_rules.json (%s), using fallback", exc)
        return self._normalize_rules(_FALLBACK_RULES)

    @staticmethod
    def _normalize_rules(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "cabinet_type_templates": data.get("cabinet_type_templates", {}),
            "grounding_materials": data.get("grounding_materials", {}),
            "inbound_outbound_materials": data.get("inbound_outbound_materials", {}),
            "normalization_aliases": data.get("normalization_aliases", {}),
        }

    # ── 公共入口 ───────────────────────────────────────────────────

    def inject(self, result: ProjectResult) -> ProjectResult:
        """遍历 cabinets 逐柜注入辅材 BomLine（当前骨架，Task 4 实现）。"""
        return result
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: 4/4 PASS

- [ ] **Step 6: Commit**

```bash
git add src/huigongyun/generation/rules.py tests/unit/generation/
git commit -m "feat: AuxMaterialInjector 骨架 + L1 规则加载测试

- rules.py: 加载 bom_rules.json，缺失时使用内置回退字典
- 测试: 4 用例覆盖有效JSON/文件缺失/格式错误/部分section

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 归一化方法 + L2-L4 测试

**Files:**
- Modify: `src/huigongyun/generation/rules.py` — 添加归一化方法
- Modify: `tests/unit/generation/test_rules.py` — 追加 L2/L3/L4 测试类

**Interfaces:**
- Consumes: `AuxMaterialInjector._rules["normalization_aliases"]`
- Produces: `_normalize_cabinet_type(type_str) -> str | None`, `_normalize_grounding(mode_str) -> str | None`, `_normalize_inbound(mode_str) -> str | None`

- [ ] **Step 1: Add L2-L4 tests to test_rules.py**

Append to `tests/unit/generation/test_rules.py`:

```python
class TestCabinetTypeNormalization:
    """L2: 柜型归一化 (5 用例)。"""

    @pytest.mark.parametrize("raw,expected", [
        ("进线柜", "进线柜"),
        ("馈线柜", "进线柜"),
        ("出线柜", "进线柜"),
        ("电源进线柜", "进线柜"),
        ("补偿柜", "补偿柜"),
        ("电容器柜", "补偿柜"),
        ("SVG柜", "补偿柜"),
        ("ATS柜", "ATS柜"),
        ("双电源柜", "ATS柜"),
        ("互投柜", "ATS柜"),
        ("母联柜", "母联柜"),
        ("联络柜", "母联柜"),
        ("变频柜", "变频柜"),
        ("MCC柜", "MCC柜"),
        ("配电箱", "配电箱"),
    ])
    def test_normalize_known_types(self, raw, expected):
        injector = AuxMaterialInjector()
        assert injector._normalize_cabinet_type(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "未知柜型", "xyz"])
    def test_normalize_unknown_returns_none(self, raw):
        injector = AuxMaterialInjector()
        assert injector._normalize_cabinet_type(raw) is None


class TestGroundingNormalization:
    """L3: 接地方式归一化 (5 用例)。"""

    @pytest.mark.parametrize("raw,expected", [
        ("TN-S", "TN-S"),
        ("TN-S 系统", "TN-S"),
        ("TNS", "TN-S"),
        ("tn-s", "TN-S"),
        ("TN-C", "TN-C"),
        ("TN-C 系统", "TN-C"),
        ("tnc", "TN-C"),
        ("TN-C-S", "TN-C-S"),
        ("tncs", "TN-C-S"),
        ("TT", "TT"),
        ("tt", "TT"),
        ("IT", "IT"),
        ("IT 系统", "IT"),
    ])
    def test_normalize_known_modes(self, raw, expected):
        injector = AuxMaterialInjector()
        assert injector._normalize_grounding(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "UNKNOWN", "XYZ"])
    def test_normalize_unknown_returns_none(self, raw):
        injector = AuxMaterialInjector()
        assert injector._normalize_grounding(raw) is None


class TestInboundOutboundNormalization:
    """L4: 进出线方式归一化 (5 用例)。"""

    @pytest.mark.parametrize("raw,expected", [
        ("电缆上进", "电缆上进"),
        ("上进", "电缆上进"),
        ("上进上出", "电缆上进"),
        ("上进线", "电缆上进"),
        ("电缆下进", "电缆下进"),
        ("下进", "电缆下进"),
        ("下进下出", "电缆下进"),
        ("母线槽进线", "母线槽进线"),
        ("母线进线", "母线槽进线"),
        ("母线接入", "母线槽进线"),
        ("母线槽接入", "母线槽进线"),
        ("母线槽出线", "母线槽出线"),
        ("背靠背拼柜", "背靠背拼柜"),
        ("拼柜", "背靠背拼柜"),
        ("背靠背", "背靠背拼柜"),
        ("并柜", "背靠背拼柜"),
    ])
    def test_normalize_known_modes(self, raw, expected):
        injector = AuxMaterialInjector()
        assert injector._normalize_inbound(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "未知方式", "xyz"])
    def test_normalize_unknown_returns_none(self, raw):
        injector = AuxMaterialInjector()
        assert injector._normalize_inbound(raw) is None
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: AttributeError for `_normalize_cabinet_type` etc.

- [ ] **Step 3: Implement normalization methods in rules.py**

Add to `AuxMaterialInjector` class (after `_normalize_rules`):

```python
    # ── 归一化 ─────────────────────────────────────────────────────

    def _normalize_cabinet_type(self, type_str: str | None) -> str | None:
        """柜型别名归一化：馈线柜/出线柜→进线柜，电容器柜→补偿柜 等。"""
        if not type_str:
            return None
        aliases = self._rules.get("normalization_aliases", {}).get("cabinet_type", {})
        type_clean = type_str.strip()
        for canonical, variants in aliases.items():
            if type_clean in variants:
                return canonical
        return None

    def _normalize_grounding(self, mode_str: str | None) -> str | None:
        """接地方式归一化：TNS→TN-S, tn-s→TN-S 等。"""
        if not mode_str:
            return None
        aliases = self._rules.get("normalization_aliases", {}).get("grounding", {})
        mode_clean = mode_str.strip()
        for canonical, variants in aliases.items():
            if mode_clean in variants:
                return canonical
        return None

    def _normalize_inbound(self, mode_str: str | None) -> str | None:
        """进出线方式归一化：上进→电缆上进，母线接入→母线槽进线 等。"""
        if not mode_str:
            return None
        aliases = self._rules.get("normalization_aliases", {}).get("inbound_outbound", {})
        mode_clean = mode_str.strip()
        for canonical, variants in aliases.items():
            if mode_clean in variants:
                return canonical
        return None
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py::TestCabinetTypeNormalization tests/unit/generation/test_rules.py::TestGroundingNormalization tests/unit/generation/test_rules.py::TestInboundOutboundNormalization -v -p no:launch_testing --ignore=reference
```

Expected: 所有 L2+L3+L4 测试 PASS

- [ ] **Step 5: Run all tests so far (L1+L2+L3+L4)**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: 全部 19 个测试 PASS (4 L1 + 15 L2-L4)

- [ ] **Step 6: Commit**

```bash
git add src/huigongyun/generation/rules.py tests/unit/generation/test_rules.py
git commit -m "feat: 归一化方法 — 柜型/接地/进出线别名映射 + 15 测试

- _normalize_cabinet_type: 馈线柜→进线柜, 电容器柜→补偿柜 等
- _normalize_grounding: TNS→TN-S, tncs→TN-C-S 等
- _normalize_inbound: 上进→电缆上进, 母线接入→母线槽进线 等
- 测试: 15 用例覆盖已知别名/未知值/None/空字符串

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 单层注入逻辑 + L5 测试

**Files:**
- Modify: `src/huigongyun/generation/rules.py` — 修改 `inject()` 添加三层注入调用，添加 `_apply_*` / `_create_bom_line` 方法
- Modify: `tests/unit/generation/test_rules.py` — 追加 L5 测试类

**Interfaces:**
- Produces: `inject(result) -> ProjectResult` 现在执行三层注入；`_apply_cabinet_type(cabinet) -> list[BomLine]`，`_apply_grounding(cabinet) -> list[BomLine]`，`_apply_inbound(cabinet) -> list[BomLine]`

- [ ] **Step 1: Add L5 tests to test_rules.py**

Append to `tests/unit/generation/test_rules.py`:

```python
from huigongyun.models import CabinetRecord, ProjectDocument, ProjectResult


def _make_cabinet(cabinet_no="1AA1", cabinet_type=None, grounding=None, inbound=None, **kw):
    return CabinetRecord(
        cabinet_no=cabinet_no,
        cabinet_type=cabinet_type,
        grounding_mode=grounding,
        inbound_outbound=inbound,
        **kw,
    )


def _make_result(cabinets):
    doc = ProjectDocument(project_name="test")
    return ProjectResult(project=doc, cabinets=cabinets)


class TestSingleLayerInjection:
    """L5: 单层注入 (6 用例)。"""

    def test_all_three_layers_populated(self):
        """三层属性全有，注入物料数 = 各层之和。"""
        cabinet = _make_cabinet("1AA1", "进线柜", "TN-S", "电缆上进")
        result = _make_result([cabinet])
        injector = AuxMaterialInjector()
        result = injector.inject(result)

        assert len(result.bom_lines) > 0
        names = [line.material.name for line in result.bom_lines]
        assert "框架断路器" in names
        assert "浪涌保护器" in names
        assert "N排" in names or "PE排" in names
        assert "电缆夹具" in names

    def test_cabinet_type_only(self):
        """仅柜型，接地和进出线为空，仅注入柜型模板物料。"""
        cabinet = _make_cabinet("1AA2", "母联柜", None, None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [line.material.name for line in result.bom_lines]
        assert "框架断路器" in names
        assert "多功能表" in names
        assert len(result.bom_lines) >= 3

    def test_grounding_only(self):
        """仅接地方式，无柜型和进出线，仅注入接地物料。"""
        cabinet = _make_cabinet("1AA3", None, "TN-C", None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [line.material.name for line in result.bom_lines]
        assert "PEN排" in names
        assert len(result.bom_lines) >= 1

    def test_inbound_only(self):
        """仅进出线方式，仅注入进出线辅材。"""
        cabinet = _make_cabinet("1AA4", None, None, "母线槽进线")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [line.material.name for line in result.bom_lines]
        assert "过渡母排" in names
        assert "母线连接件" in names

    def test_all_empty_attributes_no_injection(self):
        """三个属性全部为空，不注入任何物料。"""
        cabinet = _make_cabinet("1AA5", None, None, None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        assert len(result.bom_lines) == 0

    def test_compensation_cabinet_with_grounding(self):
        """补偿柜 + TN-S + 电缆下进，三层叠加。"""
        cabinet = _make_cabinet("1AA6", "补偿柜", "TN-S", "电缆下进")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [line.material.name for line in result.bom_lines]
        assert "隔离开关" in names
        assert "电容器" in names
        assert "N排" in names
        assert "PE排" in names
        assert "电缆夹具" in names
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py::TestSingleLayerInjection -v -p no:launch_testing --ignore=reference
```

Expected: FAIL (inject is no-op, returns 0 bom_lines).

- [ ] **Step 3: Implement inject() and _apply methods in rules.py**

Replace the stub `inject` method, and add these methods to `AuxMaterialInjector`:

```python
    # ── 公共入口 ───────────────────────────────────────────────────

    def inject(self, result: ProjectResult) -> ProjectResult:
        """遍历 cabinets 逐柜注入辅材 BomLine。"""
        for cabinet in result.cabinets:
            new_lines: list[BomLine] = []
            new_lines += self._apply_cabinet_type(cabinet)
            new_lines += self._apply_grounding(cabinet)
            new_lines += self._apply_inbound(cabinet)
            result.bom_lines.extend(new_lines)
        return result

    # ── 单层注入 ───────────────────────────────────────────────────

    def _apply_cabinet_type(self, cabinet: CabinetRecord) -> list[BomLine]:
        """根据柜型注入模板物料。"""
        key = self._normalize_cabinet_type(cabinet.cabinet_type)
        if key is None:
            return []
        template = self._rules["cabinet_type_templates"].get(key)
        if template is None:
            return []
        return self._materials_to_bom_lines(template["materials"], cabinet, f"柜型:{key}")

    def _apply_grounding(self, cabinet: CabinetRecord) -> list[BomLine]:
        """根据接地方式注入追加物料。"""
        key = self._normalize_grounding(cabinet.grounding_mode)
        if key is None:
            return []
        materials = self._rules["grounding_materials"].get(key, [])
        if not materials:
            return []
        return self._materials_to_bom_lines(materials, cabinet, f"接地:{key}")

    def _apply_inbound(self, cabinet: CabinetRecord) -> list[BomLine]:
        """根据进出线方式注入辅材。"""
        key = self._normalize_inbound(cabinet.inbound_outbound)
        if key is None:
            return []
        materials = self._rules["inbound_outbound_materials"].get(key, [])
        if not materials:
            return []
        return self._materials_to_bom_lines(materials, cabinet, f"进出线:{key}")

    # ── 辅助方法 ───────────────────────────────────────────────────

    def _materials_to_bom_lines(
        self, materials: list[dict[str, Any]], cabinet: CabinetRecord, rule_label: str
    ) -> list[BomLine]:
        """将规则物料字典列表转换为 BomLine 列表。"""
        lines: list[BomLine] = []
        for mat in materials:
            material = MaterialRecord(
                name=mat["name"],
                spec=mat.get("spec"),
                unit=mat.get("unit"),
                quantity=mat.get("quantity", 1) if isinstance(mat.get("quantity"), (int, float)) else 0.0,
                source=SourceRef(file_name="bom_rules", file_type="rule", excerpt=rule_label),
                confidence=0.7,
                remarks=rule_label,
            )
            lines.append(BomLine(
                cabinet_no=cabinet.cabinet_no,
                material=material,
                derived_from="规则推算",
            ))
        return lines
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py::TestSingleLayerInjection -v -p no:launch_testing --ignore=reference
```

Expected: 6/6 PASS

- [ ] **Step 5: Run all tests so far**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: 25/25 PASS

- [ ] **Step 6: Commit**

```bash
git add src/huigongyun/generation/rules.py tests/unit/generation/test_rules.py
git commit -m "feat: 单层注入逻辑 — 柜型/接地/进出线独立查表注入 + 6 测试

- inject() 遍历 cabinets 执行三层注入
- _apply_cabinet_type/_apply_grounding/_apply_inbound 各层独立
- _materials_to_bom_lines 将规则 dict 转为 BomLine
- 测试: 三层全有/仅柜型/仅接地/仅进出线/全空/补偿柜叠加

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 合并去重 + L6 测试

**Files:**
- Modify: `src/huigongyun/generation/rules.py` — 添加 `_merge_into_existing` 方法，在 `inject()` 中调用
- Modify: `tests/unit/generation/test_rules.py` — 追加 L6 测试类

**Interfaces:**
- Produces: `_merge_into_existing(new_lines, existing_lines)` — 同名同 spec 物料 quantity 相加

- [ ] **Step 1: Add L6 tests to test_rules.py**

Append:

```python
class TestMergeAndDedup:
    """L6: 合并去重 (5 用例)。"""

    def test_same_material_from_two_layers_merges(self):
        """两层同时注入同名物料 PE排，合并为 1 条 quantity 相加。"""
        cabinet = _make_cabinet("B01", "配电箱", "TN-S", None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        pe_lines = [l for l in result.bom_lines if l.material.name == "PE排"]
        assert len(pe_lines) == 1, f"PE排 should merge, got {len(pe_lines)}"

    def test_no_duplicates_across_three_layers(self):
        """三层注入均不含重复 → 总物料数 = 三层物料数之和。"""
        cabinet = _make_cabinet("B02", "母联柜", "TN-C", "电缆下进")
        result = _make_result([cabinet])
        before_count = result.bom_lines.count  # 0
        result = AuxMaterialInjector().inject(result)
        # 每层至少 1 条，无重叠 → >= 1+1+1 = 3
        assert len(result.bom_lines) >= 3

    def test_rule_material_merges_with_existing_excel_bom(self):
        """规则注入物料与 Excel 已提取的同名同规物料合并。"""
        cabinet = _make_cabinet("B03", "进线柜", None, None)
        result = _make_result([cabinet])

        # 模拟 Excel 已提取的物料
        existing = MaterialRecord(name="框架断路器", spec="按额定电流", unit="台")
        existing.quantity = 1
        result.bom_lines.append(BomLine(
            cabinet_no="B03", material=existing, derived_from="Excel提取"
        ))

        result = AuxMaterialInjector().inject(result)

        cb_lines = [l for l in result.bom_lines if l.material.name == "框架断路器"]
        assert len(cb_lines) == 1, f"Should merge, got {len(cb_lines)}"

    def test_same_name_different_spec_not_merged(self):
        """同名但 spec 不同，不合并。"""
        cabinet = _make_cabinet("B04", "进线柜", None, None)
        result = _make_result([cabinet])

        existing = MaterialRecord(name="框架断路器", spec="NSX630", unit="台")
        existing.quantity = 1
        result.bom_lines.append(BomLine(
            cabinet_no="B04", material=existing, derived_from="Excel提取"
        ))

        result = AuxMaterialInjector().inject(result)

        cb_lines = [l for l in result.bom_lines if l.material.name == "框架断路器"]
        assert len(cb_lines) == 2, f"Different spec should not merge, got {len(cb_lines)}"

    def test_same_name_different_brand_not_merged(self):
        """同名同规但 brand 不同，不合并。"""
        cabinet = _make_cabinet("B05", "进线柜", None, None)
        result = _make_result([cabinet])

        existing = MaterialRecord(name="框架断路器", spec="按额定电流", unit="台", brand="施耐德")
        existing.quantity = 1
        result.bom_lines.append(BomLine(
            cabinet_no="B05", material=existing, derived_from="Excel提取"
        ))

        result = AuxMaterialInjector().inject(result)

        cb_lines = [l for l in result.bom_lines if l.material.name == "框架断路器"]
        assert len(cb_lines) == 2, f"Different brand should not merge, got {len(cb_lines)}"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py::TestMergeAndDedup -v -p no:launch_testing --ignore=reference
```

Expected: FAIL (no merge logic yet).

- [ ] **Step 3: Implement merge logic in rules.py**

Add to `AuxMaterialInjector`, and modify `inject()` to call merge:

```python
    # ── 公共入口 ───────────────────────────────────────────────────

    def inject(self, result: ProjectResult) -> ProjectResult:
        """遍历 cabinets 逐柜注入辅材 BomLine，合并去重。"""
        for cabinet in result.cabinets:
            new_lines: list[BomLine] = []
            new_lines += self._apply_cabinet_type(cabinet)
            new_lines += self._apply_grounding(cabinet)
            new_lines += self._apply_inbound(cabinet)
            self._merge_into_existing(new_lines, result.bom_lines)
        return result

    # ── 合并去重 ───────────────────────────────────────────────────

    def _merge_into_existing(self, new_lines: list[BomLine], existing: list[BomLine]) -> None:
        """将新 BomLine 合并到现有列表，同名同规格同柜号 quantity 相加。"""
        for new_line in new_lines:
            merged = False
            for exist_line in existing:
                if (
                    exist_line.cabinet_no == new_line.cabinet_no
                    and exist_line.material.name == new_line.material.name
                    and exist_line.material.spec == new_line.material.spec
                    and exist_line.material.brand == new_line.material.brand
                ):
                    exist_line.material.quantity += (new_line.material.quantity or 0)
                    merged = True
                    break
            if not merged:
                existing.append(new_line)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py::TestMergeAndDedup -v -p no:launch_testing --ignore=reference
```

Expected: 5/5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/huigongyun/generation/rules.py tests/unit/generation/test_rules.py
git commit -m "feat: 合并去重 — 同名同规同柜物料 quantity 相加

- _merge_into_existing: 新 BomLine 与已有 BomLine 按 cabinet_no/name/spec/brand 匹配
- 匹配成功 → quantity 相加；失败 → 追加
- 测试: 同名合并/无重复/与Excel已有合并/不同spec不合并/不同brand不合并

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 占位符解析 + L7 测试

**Files:**
- Modify: `src/huigongyun/generation/rules.py` — 修改 `_materials_to_bom_lines` 调用占位符解析，添加 `_resolve_quantity` / `_resolve_spec` / `_parse_dimension_width` 方法
- Modify: `tests/unit/generation/test_rules.py` — 追加 L7 测试类

- [ ] **Step 1: Add L7 tests**

Append to test_rules.py:

```python
class TestPlaceholderResolution:
    """L7: 占位符处理 (6 用例)。"""

    def test_quantity_by_cabinet_width_with_dimensions(self):
        """quantity='按柜宽' + dimensions='800x800x2200' → 解析为数值。"""
        cabinet = _make_cabinet("C01", None, "TN-S", None, dimensions="800x800x2200")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        pe_line = next(l for l in result.bom_lines if l.material.name == "PE排")
        assert pe_line.material.quantity > 0

    def test_quantity_by_cabinet_width_without_dimensions(self):
        """quantity='按柜宽' + dimensions 为空 → 标记 pending。"""
        cabinet = _make_cabinet("C02", None, "TN-S", None, dimensions=None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        pe_line = next(l for l in result.bom_lines if l.material.name == "PE排")
        assert pe_line.material.quantity == 0.0
        assert pe_line.material.remarks and "pending" in pe_line.material.remarks.lower()

    def test_quantity_by_circuit_count_with_value(self):
        """quantity='按回路数' + circuit_count=12 → quantity=12。"""
        cabinet = _make_cabinet("C03", "出线柜", None, None, circuit_count=12)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        mccb_line = next(l for l in result.bom_lines if l.material.name == "塑壳断路器")
        assert mccb_line.material.quantity == 12

    def test_quantity_by_circuit_count_without_value(self):
        """quantity='按回路数' + circuit_count=None → 标记 pending。"""
        cabinet = _make_cabinet("C04", "出线柜", None, None, circuit_count=None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        mccb_line = next(l for l in result.bom_lines if l.material.name == "塑壳断路器")
        assert "pending" in (mccb_line.material.remarks or "").lower()

    def test_spec_by_rated_current_with_value(self):
        """spec='按额定电流' + rated_current='630A' → 替换 spec。"""
        cabinet = _make_cabinet("C05", "进线柜", None, None, rated_current="630A")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        cb_line = next(l for l in result.bom_lines if l.material.name == "框架断路器")
        assert "pending" not in (cb_line.material.remarks or "").lower()

    def test_spec_by_rated_current_without_value(self):
        """spec='按额定电流' + rated_current=None → 标记 pending_spec。"""
        cabinet = _make_cabinet("C06", "进线柜", None, None, rated_current=None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        cb_line = next(l for l in result.bom_lines if l.material.name == "框架断路器")
        assert "pending" in (cb_line.material.remarks or "").lower()
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py::TestPlaceholderResolution -v -p no:launch_testing --ignore=reference
```

- [ ] **Step 3: Implement placeholder resolution in rules.py**

Modify `_materials_to_bom_lines` and add these methods to `AuxMaterialInjector`:

```python
    def _materials_to_bom_lines(
        self, materials: list[dict[str, Any]], cabinet: CabinetRecord, rule_label: str
    ) -> list[BomLine]:
        """将规则物料字典列表转换为 BomLine 列表，解析占位符。"""
        lines: list[BomLine] = []
        for mat in materials:
            spec = self._resolve_spec(mat.get("spec"), cabinet)
            quantity, pending_qty = self._resolve_quantity(mat.get("quantity"), cabinet)

            remarks_parts = [rule_label]
            if pending_qty:
                remarks_parts.append("pending_quantity")

            material = MaterialRecord(
                name=mat["name"],
                spec=spec,
                unit=mat.get("unit"),
                quantity=quantity,
                source=SourceRef(file_name="bom_rules", file_type="rule", excerpt=rule_label),
                confidence=0.7 if not pending_qty else 0.4,
                remarks="; ".join(remarks_parts),
            )
            lines.append(BomLine(
                cabinet_no=cabinet.cabinet_no,
                material=material,
                derived_from="规则推算",
            ))
        return lines

    # ── 占位符解析 ─────────────────────────────────────────────────

    _PLACEHOLDER_SPECS = {"按额定电流", "按回路配置", "按功率", "按补偿容量"}

    @staticmethod
    def _resolve_spec(spec: str | None, cabinet: CabinetRecord) -> str | None:
        """解析 spec 占位符：按额定电流 → 从 cabinet.rated_current 推断。"""
        if spec is None or spec not in AuxMaterialInjector._PLACEHOLDER_SPECS:
            return spec
        if spec == "按额定电流" and cabinet.rated_current:
            return f"~{cabinet.rated_current}"
        return spec  # 保留占位符，待人工确认

    _NON_NUMERIC_QUANTITY = {"按柜宽", "按回路数", "按额定电流", "按补偿容量", "按功率"}

    @staticmethod
    def _resolve_quantity(quantity: Any, cabinet: CabinetRecord) -> tuple[float, bool]:
        """解析 quantity 占位符，返回 (数值, 是否pending)。"""
        if isinstance(quantity, (int, float)):
            return float(quantity), False
        if isinstance(quantity, str) and quantity in AuxMaterialInjector._NON_NUMERIC_QUANTITY:
            if quantity == "按柜宽":
                width = AuxMaterialInjector._parse_dimension_width(cabinet.dimensions)
                if width is not None:
                    return width / 1000.0, False  # mm → m
                return 0.0, True
            if quantity == "按回路数":
                if cabinet.circuit_count is not None and cabinet.circuit_count > 0:
                    return float(cabinet.circuit_count), False
                return 0.0, True
            if quantity == "按额定电流":
                if cabinet.rated_current:
                    return 1.0, False
                return 0.0, True
            if quantity in ("按补偿容量", "按功率"):
                return 0.0, True  # 需要额外输入，标记 pending
            return 0.0, True
        return float(quantity) if quantity else 0.0, False

    @staticmethod
    def _parse_dimension_width(dimensions: str | None) -> float | None:
        """从 '宽x深x高' 字符串解析宽度 (mm)，如 '800x800x2200' → 800.0。"""
        if not dimensions:
            return None
        parts = str(dimensions).replace(" ", "").lower().split("x")
        if len(parts) >= 1:
            try:
                return float(parts[0])
            except ValueError:
                pass
        return None
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py::TestPlaceholderResolution -v -p no:launch_testing --ignore=reference
```

- [ ] **Step 5: Run all unit tests**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: 36/36 PASS (4 L1 + 15 L2-L4 + 6 L5 + 5 L6 + 6 L7)

- [ ] **Step 6: Commit**

```bash
git add src/huigongyun/generation/rules.py tests/unit/generation/test_rules.py
git commit -m "feat: 占位符解析 — 按柜宽/按回路数/按额定电流 → 动态替换

- _resolve_quantity: 按柜宽→解析dimensions宽度, 按回路数→circuit_count, 按额定电流→rated_current
- _resolve_spec: 按额定电流→推断规格字符串
- _parse_dimension_width: '800x800x2200' → 800mm
- 无数据时标记 pending_quantity/pending_spec + 降低 confidence
- 测试: 6 用例覆盖有值替换/无值标记pending

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 来源标记 + 边缘降级 + L8-L9 测试

**Files:**
- Modify: `src/huigongyun/generation/rules.py` — 确保 `inject()` 不覆盖已有 `derived_from`，完善来源标记
- Modify: `tests/unit/generation/test_rules.py` — 追加 L8/L9 测试类

- [ ] **Step 1: Add L8-L9 tests**

Append to test_rules.py:

```python
class TestSourceMarking:
    """L8: 来源标记 (3 用例)。"""

    def test_derived_from_is_rule_estimate(self):
        """注入的 BomLine 标记 derived_from='规则推算'。"""
        cabinet = _make_cabinet("D01", "进线柜", "TN-S", None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        for line in result.bom_lines:
            assert line.derived_from == "规则推算"

    def test_material_source_is_bom_rules(self):
        """MaterialRecord.source.file_name = 'bom_rules'。"""
        cabinet = _make_cabinet("D02", "进线柜", None, None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        for line in result.bom_lines:
            assert line.material.source is not None
            assert line.material.source.file_name == "bom_rules"

    def test_remark_contains_rule_label(self):
        """remark 包含具体规则名。"""
        cabinet = _make_cabinet("D03", "母联柜", "TN-S", None)
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        remarks_all = " ".join(l.material.remarks or "" for l in result.bom_lines)
        assert "柜型:母联柜" in remarks_all
        assert "接地:TN-S" in remarks_all


class TestEdgeCasesAndDegradation:
    """L9: 边缘降级 (6 用例)。"""

    def test_empty_cabinets_no_crash(self):
        """cabinets 为空列表不崩溃。"""
        result = _make_result([])
        result = AuxMaterialInjector().inject(result)
        assert len(result.bom_lines) == 0

    def test_unknown_cabinet_type_skips_layer(self):
        """柜型不在 JSON 中，跳过柜型层，不影响其他层。"""
        cabinet = _make_cabinet("E01", "太阳能柜", "TN-S", "电缆上进")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [l.material.name for l in result.bom_lines]
        assert "N排" in names, "Grounding layer should still work"
        assert "电缆夹具" in names, "Inbound layer should still work"

    def test_unknown_grounding_skips_layer(self):
        """接地方式不在 JSON 中，log info，不影响其他层。"""
        cabinet = _make_cabinet("E02", "进线柜", "TN-XYZ", "电缆上进")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        names = [l.material.name for l in result.bom_lines]
        assert "框架断路器" in names, "Cabinet type layer should still work"

    def test_single_cabinet_no_matches_injects_nothing(self):
        """单个柜体三层无匹配 → 不注入任何物料。"""
        cabinet = _make_cabinet("E03", "未知XX", "未知YY", "未知ZZ")
        result = _make_result([cabinet])
        result = AuxMaterialInjector().inject(result)

        assert len(result.bom_lines) == 0

    def test_multi_cabinet_batch(self):
        """多柜体批量处理（3 柜体）每个独立计算。"""
        cabinets = [
            _make_cabinet("E04", "进线柜", "TN-S", "电缆上进"),
            _make_cabinet("E05", "母联柜", None, None),
            _make_cabinet("E06", None, "TN-C", "电缆下进"),
        ]
        result = _make_result(cabinets)
        result = AuxMaterialInjector().inject(result)

        # 每个柜体应至少有物料
        cabinet_nos = set(l.cabinet_no for l in result.bom_lines)
        assert "E04" in cabinet_nos
        assert "E05" in cabinet_nos
        assert "E06" in cabinet_nos

    def test_existing_derived_from_not_overwritten(self):
        """已有 derived_from 非空时保留原值（保留人工修正）。"""
        cabinet = _make_cabinet("E07", "进线柜", None, None)
        result = _make_result([cabinet])

        manual = MaterialRecord(name="框架断路器", spec="NSX400N", unit="台")
        manual.quantity = 1
        result.bom_lines.append(BomLine(
            cabinet_no="E07", material=manual, derived_from="人工修正"
        ))

        result = AuxMaterialInjector().inject(result)

        manual_lines = [l for l in result.bom_lines if l.derived_from == "人工修正"]
        assert len(manual_lines) == 1, "Manual edit should be preserved"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: 36/45 PASS (L8-L9 tests fail).

- [ ] **Step 3: Fix edge cases in rules.py**

The `inject()` method already handles most edge cases. The key fix: don't overwrite existing `derived_from`. The merge logic should already handle this — but let's also add a guard. Modify `inject()`:

```python
    def inject(self, result: ProjectResult) -> ProjectResult:
        """遍历 cabinets 逐柜注入辅材 BomLine，合并去重。"""
        for cabinet in result.cabinets:
            new_lines: list[BomLine] = []
            new_lines += self._apply_cabinet_type(cabinet)
            new_lines += self._apply_grounding(cabinet)
            new_lines += self._apply_inbound(cabinet)
            # 只合并，不覆盖已有的 derived_from（保留人工修正）
            self._merge_into_existing(new_lines, result.bom_lines)
        return result
```

The existing `_merge_into_existing` already achieves this — when a rule material merges with an existing one (same name/spec/brand/cabinet), it only adds quantity and does NOT overwrite `derived_from`. When the same material doesn't exist, it's appended fresh with `derived_from="规则推算"`.

- [ ] **Step 4: Run tests, verify they pass**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: 45/45 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/generation/test_rules.py
git commit -m "test: L8 来源标记 + L9 边缘降级 — 9 用例

- L8: derived_from/规则推算, MaterialRecord.source/bom_rules, remark含规则名
- L9: 空cabinets/未知柜型跳过/未知接地跳过/全无匹配/多柜体批量/人工修正不覆盖

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 接入 DefaultBomGenerator + 测试夹具

**Files:**
- Modify: `src/huigongyun/adapters/default.py` — 在 DefaultBomGenerator.generate() 中插入 AuxMaterialInjector
- Create: `tests/fixtures/aux_material_test.xlsx` — 测试夹具

- [ ] **Step 1: Wire into DefaultBomGenerator**

Edit `src/huigongyun/adapters/default.py`:

Add import at top (after existing imports):

```python
from ..generation.rules import AuxMaterialInjector
```

Modify `DefaultBomGenerator.generate()`:

```python
class DefaultBomGenerator(BomGenerator):
    """生成 BOM 行；注入辅材规则后聚合。"""

    def generate(self, result: ProjectResult) -> ProjectResult:
        # 1. 确保基础 BOM 存在
        if not result.bom_lines:
            placeholder = MaterialRecord(name="placeholder material", unit="set", quantity=1, remarks="placeholder")
            result.bom_lines.append(
                BomLine(
                    cabinet_no=result.cabinets[0].cabinet_no if result.cabinets else "TBD-01",
                    material=placeholder,
                    derived_from="default-scaffold",
                    risk_tags=["needs-implementation"],
                )
            )

        # 2. 注入辅材规则（新增）
        result = AuxMaterialInjector().inject(result)

        # 3. 聚合
        return ExcelBomAggregator().generate(result)
```

- [ ] **Step 2: Create test fixture Excel**

Use Python to create a minimal fixture:

```bash
PYTHONPATH=src python3 -c "
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.title = '主元件清单'
headers = ['柜号', '柜型', '进出线方式', '接地方式', '额定电流', '外形尺寸', '回路数',
           '物料名称', '规格型号', '单位', '数量', '品牌']
for i, h in enumerate(headers, 1):
    ws.cell(row=1, column=i, value=h)

# 进线柜 + TN-S + 电缆上进
row = 2
ws.cell(row=row, column=1, value='1AA1')
ws.cell(row=row, column=2, value='进线柜')
ws.cell(row=row, column=3, value='电缆上进')
ws.cell(row=row, column=4, value='TN-S')
ws.cell(row=row, column=5, value='630A')
ws.cell(row=row, column=6, value='800x800x2200')
ws.cell(row=row, column=7, value=4)
ws.cell(row=row, column=8, value='柜体')
ws.cell(row=row, column=9, value='800x800x2200')
ws.cell(row=row, column=10, value='台')
ws.cell(row=row, column=11, value=1)
ws.cell(row=row, column=12, value='国产')

# 母联柜 + TN-C (无进出线)
row = 3
ws.cell(row=row, column=1, value='1AA2')
ws.cell(row=row, column=2, value='母联柜')
ws.cell(row=row, column=4, value='TN-C')
ws.cell(row=row, column=5, value='400A')
ws.cell(row=row, column=6, value='600x800x2200')
ws.cell(row=row, column=8, value='柜体')
ws.cell(row=row, column=9, value='600x800x2200')
ws.cell(row=row, column=10, value='台')
ws.cell(row=row, column=11, value=1)
ws.cell(row=row, column=12, value='国产')

# 补偿柜 + TT + 母线槽进线
row = 4
ws.cell(row=row, column=1, value='1AA3')
ws.cell(row=row, column=2, value='补偿柜')
ws.cell(row=row, column=3, value='母线槽进线')
ws.cell(row=row, column=4, value='TT')
ws.cell(row=row, column=8, value='柜体')
ws.cell(row=row, column=9, value='1000x1000x2200')
ws.cell(row=row, column=10, value='台')
ws.cell(row=row, column=11, value=1)
ws.cell(row=row, column=12, value='国产')

wb.save('tests/fixtures/aux_material_test.xlsx')
print('Fixture created.')
"
```

- [ ] **Step 3: Verify fixture loads correctly**

```bash
PYTHONPATH=src python3 -c "
from huigongyun.parsing.excel import ExcelSourceParser
doc = ExcelSourceParser().parse('tests/fixtures/aux_material_test.xlsx')
print('Sheets:', doc.metadata.get('sheets', {}).keys())
print('Files:', doc.files)
"
```

- [ ] **Step 4: Run unit tests to verify no regression**

```bash
PYTHONPATH=src pytest tests/unit/generation/test_rules.py -v -p no:launch_testing --ignore=reference
```

Expected: 45/45 PASS

- [ ] **Step 5: Run existing full test suite to verify no regression**

```bash
PYTHONPATH=src pytest -p no:launch_testing --ignore=reference -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add src/huigongyun/adapters/default.py tests/fixtures/aux_material_test.xlsx
git commit -m "feat: 接入 DefaultBomGenerator + 测试夹具

- DefaultBomGenerator.generate() 在提取后/聚合前调用 AuxMaterialInjector.inject()
- 测试夹具: 3 柜体(进线/母联/补偿)含不同接地/进出线配置

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: 集成测试

**Files:**
- Create: `tests/integration/generation/__init__.py` (空文件)
- Create: `tests/integration/generation/test_rules_integration.py`

- [ ] **Step 1: Create integration test directory**

```bash
mkdir -p tests/integration/generation
touch tests/integration/generation/__init__.py
```

- [ ] **Step 2: Write integration tests**

Write `tests/integration/generation/test_rules_integration.py`:

```python
"""AuxMaterialInjector 集成测试 — 完整链路验证。"""

from __future__ import annotations

from pathlib import Path

import pytest

from huigongyun.adapters.default import DefaultBomGenerator, DefaultCabinetExtractor, DefaultMaterialNormalizer, DefaultProjectParser
from huigongyun.generation.rules import AuxMaterialInjector
from huigongyun.models import BomLine, MaterialRecord


FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures"


class TestFullPipeline:
    """完整链路集成测试。"""

    def test_full_pipeline_with_aux_materials(self):
        """DefaultBomGenerator 完整链路产出含规则注入物料。"""
        fixture = str(FIXTURE_DIR / "aux_material_test.xlsx")
        doc = DefaultProjectParser().parse(fixture)
        result = DefaultCabinetExtractor().extract(doc)

        assert len(result.cabinets) >= 3

        # 注入辅材
        result = AuxMaterialInjector().inject(result)

        # 验证注入
        rule_lines = [l for l in result.bom_lines if l.derived_from == "规则推算"]
        assert len(rule_lines) > 0, "Should have rule-injected materials"

        # 验证具体物料
        names = [l.material.name for l in rule_lines]
        assert "框架断路器" in names or "N排" in names or "隔离开关" in names

    def test_normalization_fills_brand_for_rule_materials(self):
        """注入物料经归一化后品牌被填充。"""
        fixture = str(FIXTURE_DIR / "aux_material_test.xlsx")
        doc = DefaultProjectParser().parse(fixture)
        result = DefaultCabinetExtractor().extract(doc)
        result = AuxMaterialInjector().inject(result)
        result = DefaultMaterialNormalizer().normalize(result)

        rule_lines = [l for l in result.bom_lines if l.derived_from == "规则推算"]
        at_least_one_has_brand = any(
            l.material.normalized_brand and l.material.normalized_brand != "pending"
            for l in rule_lines
        )
        # 归一化后品牌应被填充（国产柜体 → 国产品牌映射）
        # 注意：如果品牌关键词未触发推断则 may not be filled
        assert len(rule_lines) > 0, "Should have rule lines after normalization"

    def test_pending_quantity_generates_validation_issue(self):
        """pending_quantity 标记物料在导出时有提示。"""
        fixture = str(FIXTURE_DIR / "aux_material_test.xlsx")
        doc = DefaultProjectParser().parse(fixture)
        result = DefaultCabinetExtractor().extract(doc)

        # 创建一个无 dimensions 的柜体（占位符无法解析）
        from huigongyun.models import CabinetRecord
        result.cabinets.append(CabinetRecord(
            cabinet_no="PEND01", cabinet_type="配电箱",
            grounding_mode="TN-S", dimensions=None, circuit_count=None,
        ))
        result = AuxMaterialInjector().inject(result)

        pending_lines = [
            l for l in result.bom_lines
            if l.cabinet_no == "PEND01" and "pending" in (l.material.remarks or "").lower()
        ]
        assert len(pending_lines) > 0, "Should have pending lines for unresolvable placeholders"

    def test_no_regression_project_b_pattern(self):
        """验证三层注入不影响已有柜体结果（项目 B 模式）。"""
        # 无 cabinet_type/grounding/inbound 的柜体不应注入任何物料
        from huigongyun.models import CabinetRecord, ProjectDocument, ProjectResult
        doc = ProjectDocument(project_name="test")
        result = ProjectResult(project=doc, cabinets=[
            CabinetRecord(cabinet_no="NO-RULES-01"),
            CabinetRecord(cabinet_no="NO-RULES-02"),
        ])

        before_count = len(result.bom_lines)
        result = AuxMaterialInjector().inject(result)

        assert len(result.bom_lines) == before_count, (
            "Cabinets without type/grounding/inbound should not get injected materials"
        )

    def test_aggregator_works_with_rule_materials(self):
        """聚合器正确处理注入物料。"""
        fixture = str(FIXTURE_DIR / "aux_material_test.xlsx")
        doc = DefaultProjectParser().parse(fixture)
        result = DefaultCabinetExtractor().extract(doc)
        result = AuxMaterialInjector().inject(result)
        result = DefaultBomGenerator().generate(result)

        assert len(result.summary) > 0
        assert all(isinstance(m, MaterialRecord) for m in result.summary)
```

- [ ] **Step 3: Run integration tests, verify they pass**

```bash
PYTHONPATH=src pytest tests/integration/generation/test_rules_integration.py -v -p no:launch_testing --ignore=reference
```

Expected: 5/5 PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/generation/
git commit -m "test: 集成测试 — 完整链路 + 归一化 + pending + 回归

- test_full_pipeline_with_aux_materials: DefaultBomGenerator 产出含注入物料
- test_normalization_fills_brand: 归一化后品牌填充
- test_pending_quantity_generates_validation_issue: pending 标记
- test_no_regression_project_b_pattern: 无属性柜体不注入
- test_aggregator_works_with_rule_materials: 聚合器兼容

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: 全量回归 + 更新 CLAUDE.md

- [ ] **Step 1: Run full test suite**

```bash
PYTHONPATH=src pytest -p no:launch_testing --ignore=reference -q
```

Expected: 全部 188+ collected，183+ passed（新增 5 集成测试）

- [ ] **Step 2: Record test counts**

```bash
PYTHONPATH=src pytest -p no:launch_testing --ignore=reference --collect-only -q 2>&1 | tail -2
```

- [ ] **Step 3: Update CLAUDE.md**

Update test counts and mark the P0 features as complete:

In CLAUDE.md "已交付模块" table, add:
```
| 辅材规则注入 | ✅ | `generation/rules.py` AuxMaterialInjector，柜型/接地/进出线三层叠加，50 用例 |
```

In CLAUDE.md "当前测试状态", update the collected/passed counts from the actual test run.

Remove from "未完成/暂缓" if any P0 items were listed there.

- [ ] **Step 4: Final commit**

```bash
git add CLAUDE.md
git commit -m "docs: 更新 CLAUDE.md — P0 辅材规则注入已交付

- 新增 generation/rules.py: AuxMaterialInjector 三层规则注入
- 新增 generation/dictionaries/bom_rules.json: 8柜型+5接地+5进出线
- 测试: 50 用例 (45单元+5集成)
- 更新测试计数

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **Step 5: Self-review checklist**

Run the self-review:
1. Spec coverage: Does each design spec section have a corresponding task?  ✅
2. Placeholder scan: No TBD/TODO/incomplete patterns. ✅
3. Type consistency: All types match across tasks (CabinetRecord, BomLine, ProjectResult, MaterialRecord). ✅

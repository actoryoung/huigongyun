# P0: 柜型/接地/进出线 → BOM 辅材规则注入

**日期**: 2026-06-30
**状态**: 设计已确认，待实现

---

## 一、背景

赛题业务规则要求：
- 柜型影响 BOM（进线柜/母联柜/补偿柜等各有典型物料）
- 接地方式影响物料（TN-S/TN-C/TT/IT 影响 N排/PE排/RCD/绝缘监测）
- 进出线方式影响辅材（电缆上进/下进、母线槽接入、背靠背拼柜）

现有 `CabinetRecord` 已定义 `cabinet_type`、`grounding_mode`、`inbound_outbound` 字段，`CabinetIndexBuilder` 和 `TechnicalConstraintExtractor` 已填充它们，但**没有任何代码将这些字段用于 BOM 生成**。

---

## 二、数据流设计

```
现有流程:
  Excel/Word/DWG → CabinetIndexBuilder    → CabinetRecord (含 cabinet_type/
                 → ExcelCabinetBomExtractor → BomLine[]       grounding_mode/
                                                              inbound_outbound)
  ─────────────── 新增 ───────────────
                 → AuxMaterialInjector    → 注入辅材 BomLine[]
  ─────────────────────────────────────
                 → MaterialNormalizer     → 归一化
                 → ExcelBomAggregator     → 汇总
                 → QuoteGenerator         → 报价
```

**插入点**: `DefaultBomGenerator.generate()`（`adapters/default.py`），在现有提取器产出 BomLine[] 之后、归一化之前。

```python
result = AuxMaterialInjector().inject(result)  # 新增这一行
```

---

## 三、规则数据模型

### 文件: `src/huigongyun/generation/dictionaries/bom_rules.json`

**核心设计: 三层叠加**

每层独立匹配，互不干扰。三层结果取并集，同 (name, spec, unit) 物料合并 quantity。

### 第一层: 柜型模板 (`cabinet_type_templates`)

| 柜型 | 典型物料 |
|------|---------|
| 进线柜 | 框架断路器 + 测量CT(×4) + 多功能表 + 浪涌保护器 |
| 母联柜 | 框架断路器 + 测量CT(×4) + 多功能表 |
| 出线柜 | 塑壳断路器(×回路数) + 接触器 + 热继电器 |
| 变频柜 | 变频器 + 输入电抗器 + 输出滤波器 + 制动单元 |
| 补偿柜 | 隔离开关 + 电容器 + 电抗器 + 晶闸管投切开关 + 温湿度控制器 |
| ATS柜 | 双电源开关 + 控制器 + 互锁机构 |
| MCC柜 | 塑壳断路器 + 接触器 + 热继电器 + 控制变压器 |
| 配电箱 | 微型断路器 + 漏电保护器 + 铜排 |

`condition_fields`: 声明哪些物料需要从柜体属性动态计算（如 `rated_current` → 断路器规格）。

### 第二层: 接地物料 (`grounding_materials`)

| 接地方式 | 追加物料 |
|---------|---------|
| TN-S | N排 + PE排 (长度按柜宽) |
| TN-C | PEN排 (长度按柜宽) |
| TN-C-S | N排 + PE排 + PEN排 |
| TT | PE排 + 漏电保护器 |
| IT | PE排 + 绝缘监测装置 |

### 第三层: 进出线辅材 (`inbound_outbound_materials`)

| 进出线方式 | 追加辅材 |
|-----------|---------|
| 电缆上进 | 电缆夹具(×回路数) + 顶部进线密封圈 |
| 电缆下进 | 电缆夹具(×回路数) + 底部进线密封圈 |
| 母线槽进线 | 过渡母排 + 母线连接件 + 接头盖板 |
| 母线槽出线 | 过渡母排 + 母线连接件 |
| 背靠背拼柜 | 拼柜连接母排 + 拼柜螺栓 |

### 占位符机制

| 占位符值 | 含义 | 处理策略 |
|---------|------|---------|
| `"按额定电流"` (spec) | 从 `rated_current` 推断规格 | 有值时替换，无值时标记 `pending_spec` |
| `"按柜宽"` (quantity) | 从 `dimensions` 解析宽度 | 解析成功替换，失败标记 `pending_quantity` |
| `"按回路数"` (quantity) | 从 `circuit_count` 取值 | 有值时替换，无值时标记 `pending_quantity` |
| `"按补偿容量"` (quantity) | 需额外输入 | 标记 `pending_quantity` |

---

## 四、Python 实现

### 文件结构

```
src/huigongyun/generation/
  dictionaries/                    # 新增目录
    bom_rules.json                 # 三层规则表
  __init__.py                      # 不变
  excel_bom.py                     # 不变
  rules.py                         # 新增: AuxMaterialInjector
```

### 核心类: `AuxMaterialInjector`

```python
class AuxMaterialInjector:
    def __init__(self, rules_path: str | None = None): ...
    def inject(self, result: ProjectResult) -> ProjectResult: ...
    def _apply_cabinet_type(self, cabinet: CabinetRecord) -> list[BomLine]: ...
    def _apply_grounding(self, cabinet: CabinetRecord) -> list[BomLine]: ...
    def _apply_inbound(self, cabinet: CabinetRecord) -> list[BomLine]: ...
    def _normalize_cabinet_type(self, type_str: str | None) -> str | None: ...
    def _normalize_grounding(self, mode_str: str | None) -> str | None: ...
    def _normalize_inbound(self, mode_str: str | None) -> str | None: ...
    def _resolve_placeholder(self, value, cabinet): ...
    def _merge_lines(self, new: list, existing: list): ...
```

### 归一化别名映射

**柜型**: 馈线柜/出线柜→进线柜, 电容器柜/SVG柜→补偿柜, 双电源柜/互投柜→ATS柜...
**接地**: tn-s/TNS/TN-S 系统→TN-S, tns→TN-S, tncs→TN-C-S...
**进出线**: 上进上出/上进→电缆上进, 下进下出/下进→电缆下进, 母线进线/母线接入→母线槽进线...

### 降级策略

- `bom_rules.json` 缺失 → 使用内置 fallback 字典（含 8种柜型+4种接地+5种进出线）
- `cabinet_type` 为空 → 跳过柜型模板层
- `grounding_mode` 为空 → 跳过接地层
- `inbound_outbound` 为空 → 跳过进出线层
- 无法估算 quantity → 标记 `pending_quantity`
- `derived_from` 已有值（人工修正）→ 不覆盖

### 接线修改

```python
# adapters/default.py → DefaultBomGenerator.generate()
result = AuxMaterialInjector().inject(result)  # 新增一行
```

---

## 五、测试计划 (50 用例)

### 单元测试: 45 用例

| 组 | 用例数 | 覆盖 |
|---|--------|------|
| L1 规则加载 | 4 | 有效JSON、文件缺失、格式错误、section缺失 |
| L2 柜型归一化 | 5 | 进线柜/馈线/补偿/ATS/None |
| L3 接地归一化 | 5 | TN-S/tns/TN-C-S/TT/IT/None |
| L4 进出线归一化 | 5 | 电缆上进/上进/母线槽/拼柜/None |
| L5 单层注入 | 6 | 各层独立、三层全空、三层全有 |
| L6 合并去重 | 5 | 同名合并、同名不同spec不合并、与Excel已有合并 |
| L7 占位符处理 | 6 | 按柜宽(有值/无值)、按回路数(有值/无值)、按额定电流(有值/无值) |
| L8 来源标记 | 3 | derived_from/MaterialRecord.source/remark |
| L9 边缘降级 | 6 | 空cabinets、未知柜型、未知接地、多柜体批量、已有derived_from不覆盖 |

### 集成测试: 5 用例

| 用例 | 覆盖 |
|------|------|
| DefaultBomGenerator 完整链路 | 输出含注入物料 |
| 注入物料经归一化后品牌填充 | 国产品牌默认填入 |
| 注入物料报价阶段正确处理 | pending 物料有缺价提示 |
| 校验阶段识别 pending 标记 | 生成对应 ValidationIssue |
| 项目 B Excel 完整链路回归 | 原统计不变 ± 新增辅材 |

### 测试夹具

`tests/fixtures/aux_material_test.xlsx`: 1进线柜+2出线柜，含不同接地/进出线配置

---

## 六、验收标准

1. ✅ 项目 B (34 柜体) 跑完完整链路，原有 BOM 结果不受影响
2. ✅ 柜型明确时自动注入对应典型物料
3. ✅ 接地方式和进出线方式各层独立生效
4. ✅ 无法确定的值（quantity/spec）标记 `pending_*`，不伪造数据
5. ✅ JSON 缺失时内置回退可用，不崩溃
6. ✅ 50 个测试用例全部通过
7. ✅ 注入物料在导出 Excel 中可追溯至 `derived_from = "规则推算"`

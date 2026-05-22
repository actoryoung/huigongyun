# 低压电气成套智能报价清单生成系统

这是一个面向低压电气成套项目的 MVP 原型，当前已经具备从 Excel 主元器件清单生成逐柜 BOM、项目汇总、基础校验和 JSON / Excel 导出的最小闭环，后续继续补强规则与解析能力：

- 项目资料解析
- 柜体识别与逐柜 BOM 生成
- 物料归一与相似匹配
- 报价汇总与校验报告
- 人机协同修正与导出

## 当前能力

- 提供核心数据模型
- 提供解析、归一、生成、校验、导出的接口协议
- 提供默认空实现，方便后续逐步替换
- 提供 CLI 入口，可用于跑通最小流程
- 已完成 Excel 解析入口：可读取工作簿元数据、sheet 名称、表头、样例行和原始记录
- 已完成从 Excel 行中抽取柜体和 BOM 明细，并可生成项目汇总 BOM
- 已补基础校验与 JSON/Excel 导出
- 已有单元测试覆盖解析、生成、校验与导出

## 运行方式

```bash
python -m pip install -e .
huigongyun --help
```

## 目录说明

- `src/huigongyun/models.py`: 核心数据结构
- `src/huigongyun/interfaces.py`: MVP 阶段的能力接口
- `src/huigongyun/bootstrap.py`: 默认流水线组装
- `src/huigongyun/pipeline.py`: 端到端编排
- `src/huigongyun/adapters/`: 默认空实现与后续适配器入口
- `src/huigongyun/parsing/`: 解析层骨架
- `src/huigongyun/normalization/`: 归一层骨架
- `src/huigongyun/generation/`: 生成层骨架
- `src/huigongyun/validation/`: 校验层骨架
- `src/huigongyun/export/`: 导出层骨架
- `src/huigongyun/cli.py`: 命令行入口
- `tests/`: 最小烟测

## 下一步

1. 提升物料归一规则和品牌映射
2. 支持更复杂的多表格 Excel 模板
3. 引入更完整的长交期和品牌冲突校验
4. 扩展图纸 / PDF / 图片输入

## 运行验证

```bash
python -m pip install -e .[dev]
pytest
python -m huigongyun /path/to/input.xlsx --output-dir ./output
```

## 当前输出

- `*_result.json`: 项目结构化结果，包含柜体、BOM、汇总、校验和导出路径
- `*_result.xlsx`: 结构化 Excel 结果，包含 `Project`、`Cabinets`、`BOM`、`Summary`、`Issues` 工作表

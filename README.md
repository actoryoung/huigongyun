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
- 目录输入会返回歧义标记，不再静默选择第一份工作簿；原始 Excel 行号会被保留
- 已补轻量物料归一层：同义词、品牌别名和规格清洗
- 已补柜体清单生成接口：独立 builder 输出柜体列表与未解析记号
- 已补基础校验的“待确认记号”：未解析柜号、缺规格、缺品牌会进入 Issues
- 校验报告会保留 `pending_*` 记号，便于后续数据格式下发后回填
- 已补轻量 Web 演示壳：上传 Excel、运行、查看结果、下载 JSON / Excel

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

1. 支持更复杂的多表格 Excel 模板
2. 扩展图纸 / PDF / 图片输入
3. 补充人机协同回灌和演示脚本收尾

## 当前计划进程

- 已完成：Excel 解析、物料归一、柜体清单、逐柜 BOM、项目汇总、基础校验、JSON/Excel 导出。
- 未完成：复杂表格模板、图纸/PDF/图片输入、人机协同回灌、文档与演示脚本收尾。
- 暂缓：复杂支持和高级校验先不做，保留接口与 `pending_*` 记号，等待后续数据格式正式下发。

## 运行验证

```bash
python -m pip install -e .[dev]
pytest
python -m huigongyun /path/to/input.xlsx --output-dir ./output
huigongyun-web
```

Web 演示壳也可以用下面方式安装和启动：

```bash
python -m pip install -e .[web]
huigongyun-web
```

## 当前输出

- `*_result.json`: 项目结构化结果，包含柜体、BOM、汇总、校验和导出路径
- `*_result.xlsx`: 结构化 Excel 结果，包含 `Project`、`Cabinets`、`BOM`、`Summary`、`Issues` 工作表

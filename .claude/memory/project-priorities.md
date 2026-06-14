---
name: project-priorities
description: 当前项目优先级排序与暂缓事项
metadata:
  type: project
---

# 项目优先级 (2026-06-14)

## 当前推进（按顺序）
1. **PDF矢量图识别** — 商业大模型OCR + Marker本地兜底 → [[pdf-processing-strategy]]
2. **版本差异Demo** — 项目D双版本Excel，低投入高回报
3. **风险分级体系** — 在现有7类校验上叠加分级标签
4. **历史检索RAG** — 待技术选型（FAISS vs Chroma vs PGVector）

## 明确暂缓
- **多源融合校验** (Excel vs DWG vs Word 跨源一致性) — 优先级后推
- **CI/CD 自动测试** — 不使用，测试手动运行 `pytest`
- **复杂商务报价** (税率/折扣/运费/利润) — 不在当前scope

## 架构约束
- DWG AC1032 (2018+): 需ODA Converter商业许可，当前不可用
- CAD矢量PDF: 优先DWG→DXF方案，PDF做LLM OCR补充
- 大文件在 `examples/` 目录，Git不提交

**Why:** 比赛场景下PDF识别是最关键的差异化能力。融合校验依赖三个模块都稳定，应等PDF识别完成后统一做。

**How to apply:** 每次工作前检查此文件确认当前优先级。新增任务时对照此列表避免跑偏。

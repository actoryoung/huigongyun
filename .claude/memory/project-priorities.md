---
name: project-priorities
description: 当前项目优先级排序与暂缓事项
metadata:
  type: project
---

# 项目优先级 (2026-06-30)

## 已完成
1. ✅ PDF矢量图识别 — vision_llm.py + marker_adapter.py + pdf.py 五级回退链
2. ✅ 版本差异Demo — comparison/differ.py + scripts/demo_version_diff.py
3. ✅ 风险分级体系 — validation/risk.py RiskClassifier + ValidationIssue.risk_level
4. ✅ 历史检索RAG — retrieval/ FAISS + sentence-transformers
5. ✅ 品牌归一化回退链 — 精确→大小写不敏感→别名→默认品牌→RapidFuzz
6. ✅ SimilarMaterialMatcher — retrieval/matcher.py EmbeddingMaterialMatcher
7. ✅ 多源融合校验 — parsing/multi_source.py + validation/cross_source.py 5条跨源规则

## 当前待推进
1. **价格表数据接入** — 待用户提供价格表文件，填充 unit_price + price_source
2. **Vision LLM API Key 配置** — 激活 PDF CAD 图纸 Vision LLM 识别路径

## 明确暂缓
- **版本差异 Web UI** — diff 可视化待做
- **CI/CD 自动测试** — 暂不启用，测试手动运行 `pytest`
- **复杂商务报价** (税率/折扣/运费/利润) — 不在当前scope
- **DWG AC1032** (2018+) — 需ODA Converter商业许可，当前不可用

## 架构约束
- 大文件在 `examples/` 目录，Git不提交
- 重型依赖 (OCR/ML/Vision LLM) lazy import，缺失时优雅回退
- 测试运行: `PYTHONPATH=src pytest -p no:launch_testing --ignore=reference`

**Why:** Phase 3a/3b/3c/3d 已全部交付，当前阻塞项是外部依赖（价格表数据、API Key配置）。

**How to apply:** 每次工作前检查此文件确认当前优先级。新增任务时对照此列表避免跑偏。

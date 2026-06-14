---
name: pdf-processing-strategy
description: CAD矢量PDF处理方案选型决策与执行路线
metadata:
  type: project
---

# CAD 矢量 PDF 处理策略

**决策日期**: 2026-06-14

## 方案选择
**混合路线：商业大模型 API（主）+ Marker 本地（兜底）**

流程：PDF → pdf2image(300DPI) → 页面PNG
  → 优先: GPT-4o / Claude Vision API（结构化JSON Schema输出）
  → 兜底: Marker PDF→Markdown（CPU可跑，处理有文本层页面）

## 选型理由
- 比赛样例数据量小（4项目，每项目数十页），API成本可控
- GPT-4o/Claude对中文+表格+电气符号联合理解远超传统OCR
- 结构化输出可直接对接现有ProjectDocument/CabinetRecord模型
- 不需要GPU硬件
- Marker免费兜底降低API成本

## 开源参考
- Marker: https://github.com/datalab-to/marker (35k⭐, CPU可跑)
- olmOCR: https://github.com/allenai/olmOCR (需GPU)
- Vision Parse: https://github.com/iamarunbrahma/vision-parse (API封装)
- ParseMyPDF: https://github.com/genieincodebottle/parsemypdf (对比工具)

## 任务顺序
1. PDF→图片渲染管线 (pdf2image已有)
2. Vision LLM调用适配器
3. 电气图纸专用Prompt + 结构化Schema
4. Marker本地兜底集成
5. 混合路由逻辑
6. 对接现有pipeline.py
7. 样例验证 (项目A/D PDF)
8. 测试补齐

**Why:** CAD矢量PDF无文本层，传统OCR(Tesseract)误识率极高。需商业VLM的视觉理解能力处理图纸中的线条/文字混合、旋转标签、复杂表格。

**How to apply:** 实现parsing/pdf.py的VisionLLM分支，保持现有PdfSourceParser/PdfOcrParser作为兼容路径。新增LLM调用模块通过环境变量配置API Key。

# OCR PoC (Tesseract + pdf2image)

系统依赖（需通过系统包管理器安装）：

- tesseract OCR 引擎：

  sudo apt update && sudo apt install -y tesseract-ocr

- poppler（用于 PDF 渲染）：

  sudo apt install -y poppler-utils

Python 依赖（请参见 `requirements.txt`，也可在虚拟环境中安装）：

- pytesseract
- pdf2image
- pdfplumber (已有)
- Pillow

快速运行（在项目根目录，虚拟环境中）：

```bash
python scripts/ocr_poc.py tests/fixtures/ocr_sample.png
# 或对 PDF：
python scripts/ocr_poc.py sample.pdf
```

如果运行时报错提示找不到 tesseract，可通过以下命令测试：

```bash
tesseract --version
```

如果想运行集成测试（非默认），设置环境变量并运行 pytest：

```bash
export OCR_POC=1
pytest tests/integration/parsing/test_ocr_integration.py -q
```


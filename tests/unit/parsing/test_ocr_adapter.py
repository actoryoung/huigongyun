import types
import sys

class FakeImage:
    def __init__(self, w, h):
        self.size = (w, h)


def test_image_to_dict_monkeypatched(monkeypatch, tmp_path):
    sample = {
        "level": [1, 2],
        "page_num": [1, 1],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "word_num": [0, 1],
        "left": [0, 10],
        "top": [0, 5],
        "width": [100, 90],
        "height": [50, 40],
        "conf": ["-1", "95"],
        "text": ["", "Hello"],
    }

    # fake pytesseract module
    fake_pyt = types.ModuleType('pytesseract')
    def fake_image_to_data(image, output_type=None):
        return sample
    fake_pyt.image_to_data = fake_image_to_data
    fake_pyt.Output = types.SimpleNamespace(DICT='DICT')
    monkeypatch.setitem(sys.modules, 'pytesseract', fake_pyt)

    # fake PIL.Image.open
    fake_pil = types.ModuleType('PIL')
    image_mod = types.SimpleNamespace()
    def open_fn(path):
        return FakeImage(100, 50)
    image_mod.open = open_fn
    fake_pil.Image = image_mod
    monkeypatch.setitem(sys.modules, 'PIL', fake_pil)

    from huigongyun.parsing.ocr_adapter import TesseractAdapter

    img_path = tmp_path / 'sample.png'
    img_path.write_bytes(b'')

    res = TesseractAdapter.image_to_dict(str(img_path))
    assert 'pages' in res
    assert 'plain_text' in res
    assert isinstance(res['pages'], list)
    assert len(res['pages']) == 1
    page = res['pages'][0]
    assert 'blocks' in page
    assert isinstance(page['blocks'], list)
    block = page['blocks'][0]
    for k in ('bbox', 'text', 'confidence'):
        assert k in block


def test_pdf_to_dict_monkeypatched(monkeypatch):
    sample = {
        "level": [1],
        "page_num": [1],
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "word_num": [1],
        "left": [10],
        "top": [5],
        "width": [80],
        "height": [20],
        "conf": ["88"],
        "text": ["World"],
    }

    # fake pytesseract
    fake_pyt = types.ModuleType('pytesseract')
    def fake_image_to_data(image, output_type=None):
        return sample
    fake_pyt.image_to_data = fake_image_to_data
    fake_pyt.Output = types.SimpleNamespace(DICT='DICT')
    monkeypatch.setitem(sys.modules, 'pytesseract', fake_pyt)

    # fake pdf2image
    fake_pdf2 = types.ModuleType('pdf2image')
    img1 = FakeImage(100, 50)
    img2 = FakeImage(200, 150)
    def fake_convert_from_path(pdf_path, dpi=300):
        return [img1, img2]
    fake_pdf2.convert_from_path = fake_convert_from_path
    monkeypatch.setitem(sys.modules, 'pdf2image', fake_pdf2)

    # ensure PIL is present for adapter imports (we return FakeImage instances directly)
    monkeypatch.setitem(sys.modules, 'PIL', types.ModuleType('PIL'))

    from huigongyun.parsing.ocr_adapter import TesseractAdapter

    res = TesseractAdapter.pdf_to_dict('dummy.pdf', dpi=150)
    assert 'pages' in res
    assert len(res['pages']) == 2
    assert res['pages'][0]['width'] == 100
    assert res['pages'][1]['width'] == 200

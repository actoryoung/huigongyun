from pathlib import Path
import types
import sys

from huigongyun.parsing.registry import build_default_source_registry
import huigongyun.parsing.dwg as dwg_mod


def test_dwg_requires_conversion_when_converter_returns_none(monkeypatch, tmp_path):
    # create fake .dwg file
    p = Path(tmp_path) / "sample.dwg"
    p.write_bytes(b"DWG-DATA")

    # monkeypatch converter to return None
    monkeypatch.setattr(dwg_mod.DwgConverter, 'convert_dwg_to_dxf', lambda self, path, out_dir=None: None)

    doc = build_default_source_registry().parse(str(p))

    assert doc.metadata.get('parse_status') == 'requires_conversion'


def test_dwg_conversion_and_dxf_parsing(monkeypatch, tmp_path):
    # create fake .dwg file
    dwg = Path(tmp_path) / "drawing.dwg"
    dwg.write_bytes(b"DWG")

    # path for converted dxf
    converted = Path(tmp_path) / "drawing.dxf"
    converted.write_text("0\nSECTION\n")

    # monkeypatch converter to return the converted path
    monkeypatch.setattr(dwg_mod.DwgConverter, 'convert_dwg_to_dxf', lambda self, path, out_dir=None: str(converted))

    # create fake ezdxf module with readfile
    class FakeDoc:
        def modelspace(self):
            class Msp:
                def query(self, q):
                    return [types.SimpleNamespace(text='T1'), types.SimpleNamespace(text='T2')]
            return Msp()

    fake_ezdxf = types.ModuleType('ezdxf')
    fake_ezdxf.readfile = lambda p: FakeDoc()
    monkeypatch.setitem(sys.modules, 'ezdxf', fake_ezdxf)

    doc = build_default_source_registry().parse(str(dwg))

    assert doc.metadata.get('parse_status') == 'ok'
    assert doc.metadata.get('source_format') == 'dxf'
    assert doc.metadata.get('text_count', 0) >= 2

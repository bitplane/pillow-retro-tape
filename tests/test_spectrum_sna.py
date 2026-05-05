import pytest
from PIL import Image, UnidentifiedImageError

import pillow_zx_spectrum  # noqa: F401
from pillow_zx_spectrum.snapshot import MachineType
from pillow_zx_spectrum.spectrum_sna import parse_sna

from ._helpers import make_screen, make_sna_48k


def test_parse_48k_sna_screen():
    ram = bytearray(49152)
    s = make_screen(0xFF, 0x07)
    ram[:6912] = s
    snap = parse_sna(make_sna_48k(bytes(ram), border=4))
    assert snap.machine == MachineType.SPECTRUM_48K
    assert snap.border == 4
    assert snap.screen() == s


def test_parse_rejects_wrong_size():
    with pytest.raises(ValueError):
        parse_sna(b"\x00" * 100)


def test_pillow_open_sna(tmp_path):
    ram = bytearray(49152)
    ram[:6912] = make_screen(0xFF, 0x07)
    p = tmp_path / "synth.sna"
    p.write_bytes(make_sna_48k(bytes(ram)))
    img = Image.open(p)
    assert img.format == "ZXSNA"
    img.load()


def test_pillow_rejects_wrong_size(tmp_path):
    p = tmp_path / "junk.sna"
    p.write_bytes(b"\x00" * 1234)
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)

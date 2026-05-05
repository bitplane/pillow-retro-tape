from PIL import Image

import pillow_retro_tape  # noqa: F401
from pillow_retro_tape.spectrum_slt import (
    SLT_TYPE_SCREEN,
    extract_screens,
    iter_slt_entries,
)

from ._helpers import make_screen, make_slt, make_z80_v3


def _empty_v3_z80() -> bytes:
    """Minimal v3 Z80 with no RAMP data — irrelevant for this test."""
    return make_z80_v3({}, hardware_mode=0)


def test_iter_slt_entries_returns_screen_entries():
    snap = _empty_v3_z80()
    s1 = make_screen(0xFF, 0x07)
    s2 = make_screen(0xFF, 0x02)
    slt = make_slt(snap, [s1, s2])
    entries = list(iter_slt_entries(slt))
    assert len(entries) == 2
    assert all(t == SLT_TYPE_SCREEN for t, _, _ in entries)
    assert entries[0][2] == s1
    assert entries[1][2] == s2


def test_iter_slt_entries_empty_when_no_signature():
    """A z80 file without the SLT marker yields nothing."""
    snap = _empty_v3_z80()
    assert list(iter_slt_entries(snap)) == []


def test_extract_screens_returns_slt_screens_in_table_order():
    snap = _empty_v3_z80()
    s1 = make_screen(0xFF, 0x07)
    s2 = make_screen(0xFF, 0x02)
    screens = extract_screens(make_slt(snap, [s1, s2]))
    # Snapshot's $4000 is empty so frame 0 = s1, frame 1 = s2.
    assert screens == [s1, s2]


def test_pillow_open_slt(tmp_path):
    snap = _empty_v3_z80()
    s1 = make_screen(0xFF, 0x07)
    p = tmp_path / "synth.slt"
    p.write_bytes(make_slt(snap, [s1]))
    img = Image.open(p)
    assert img.format == "ZXSLT"
    img.load()


def test_pillow_rejects_z80_without_slt_marker(tmp_path):
    """A bare .z80 file with no SLT marker should fall through to ZXZ80."""
    p = tmp_path / "no-slt.slt"
    p.write_bytes(_empty_v3_z80())
    # The SLT plugin rejects (no marker), and Pillow falls through to ZXZ80
    # which accepts it (PC=0, extra_len=54 is valid).
    img = Image.open(p)
    assert img.format == "ZXZ80"

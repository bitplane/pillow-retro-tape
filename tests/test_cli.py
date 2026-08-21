"""Tests for the ``zx-screen`` command line tool."""

import importlib.metadata

import pytest
from PIL import Image

from pillow_zx_spectrum.blocks import TYPE_CODE
from pillow_zx_spectrum.cli import main

from ._helpers import make_data_block, make_header_block, make_screen, make_tap


def test_save_output_writes_png(data_dir, tmp_path):
    out = tmp_path / "out.png"
    rc = main([str(data_dir / "colorbars.scr"), "-o", str(out)])
    assert rc == 0
    saved = Image.open(out)
    assert saved.format == "PNG"
    assert saved.size == (256, 192)


def test_default_action_shows_image(data_dir, monkeypatch):
    shown = []
    monkeypatch.setattr(Image.Image, "show", lambda self, title=None: shown.append(self))
    rc = main([str(data_dir / "colorbars.scr")])
    assert rc == 0
    assert len(shown) == 1
    assert shown[0].size == (256, 192)


def test_frame_selects_other_screen(tmp_path):
    # Two-screen TAP: white-on-black then red-on-black.
    screens = [make_screen(0xFF, 0x07), make_screen(0xFF, 0x02)]
    blocks = []
    for i, screen in enumerate(screens):
        blocks.append(make_header_block(TYPE_CODE, f"scr{i}", 6912, 0x4000))
        blocks.append(make_data_block(screen))
    tap = tmp_path / "two.tap"
    tap.write_bytes(make_tap(*blocks))

    out = tmp_path / "frame1.png"
    rc = main([str(tap), "--frame", "1", "-o", str(out)])
    assert rc == 0

    expected = Image.open(tap)
    expected.seek(1)
    expected.load()
    assert Image.open(out).convert("RGB").tobytes() == expected.tobytes()


def test_frame_out_of_range_fails(data_dir, tmp_path, capsys):
    rc = main([str(data_dir / "colorbars.scr"), "--frame", "5", "-o", str(tmp_path / "x.png")])
    assert rc == 1
    assert "frame" in capsys.readouterr().err.lower()


def test_missing_file_fails(tmp_path, capsys):
    rc = main([str(tmp_path / "nope.tap")])
    assert rc == 1
    assert "nope.tap" in capsys.readouterr().err


def test_unrecognised_file_fails(tmp_path, capsys):
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"definitely not a spectrum file")
    rc = main([str(junk)])
    assert rc == 1
    assert "junk.bin" in capsys.readouterr().err


def test_console_scripts_registered():
    eps = importlib.metadata.entry_points(group="console_scripts")
    ours = {ep.name: ep.value for ep in eps if ep.value.startswith("pillow_zx_spectrum.")}
    assert ours == {"zx-screen": "pillow_zx_spectrum.cli:main"}


def test_help_uses_command_name(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "zx-screen" in capsys.readouterr().out

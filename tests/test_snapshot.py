from pillow_retro_tape.snapshot import MachineType, Snapshot

from ._helpers import make_screen


def test_default_snapshot_is_zero_ram():
    s = Snapshot()
    assert len(s.ram) == 0x10000
    assert all(b == 0 for b in s.ram)
    assert s.banks == {}
    assert s.machine == MachineType.UNKNOWN


def test_screen_returns_4000_slice():
    s = Snapshot()
    screen = make_screen(0xFF, 0x07)
    s.ram[0x4000 : 0x4000 + len(screen)] = screen
    assert s.screen() == screen
    assert len(s.screen()) == 6912


def test_shadow_screen_none_by_default():
    assert Snapshot().shadow_screen() is None


def test_shadow_screen_returns_first_6912_of_bank_7():
    s = Snapshot()
    s.banks[7] = bytes([0x42] * 16384)
    shadow = s.shadow_screen()
    assert shadow == bytes([0x42] * 6912)

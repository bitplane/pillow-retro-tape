import struct

import pytest
from PIL import Image, UnidentifiedImageError

import pillow_retro_tape  # noqa: F401
from pillow_retro_tape.microdrive import (
    DATA_BYTES,
    HEADER_LEN,
    MIN_SECTORS,
    SECTOR_BYTES,
    TYPE_BASIC,
    TYPE_CODE,
    parse_mdr_files,
)
from pillow_retro_tape.spectrum_mdr import extract_screens

from ._helpers import make_screen


def _checksum(data: bytes) -> int:
    return sum(data) % 255


def _make_sector(
    *,
    cartridge_name: str = "TEST      ",
    sector_index: int = 1,
    rec_flag: int = 0x06,  # SAVE* data record (bit 1 = preamble, bit 2 = SAVE*)
    rec_num: int = 0,
    rec_len: int | None = None,
    name: str = "file",
    data: bytes = b"",
) -> bytes:
    """Construct one valid 543-byte Microdrive sector."""
    if rec_len is None:
        rec_len = len(data)
    # Sector header: cartridge name (10) + sector index (1) + 3 unused
    sec_header = bytearray(HEADER_LEN)
    cart = cartridge_name.encode("ascii")[:10].ljust(10, b" ")
    sec_header[0] = sector_index & 0xFF
    sec_header[1:11] = cart
    # Bytes 11..13 — unused/zero per spec
    sec_header[14] = _checksum(sec_header[: HEADER_LEN - 1])

    # Record descriptor: flag(1) + num(1) + len(2) + name(10) + 0 + checksum(1)
    desc = bytearray(15)
    desc[0] = rec_flag
    desc[1] = rec_num & 0xFF
    desc[2] = rec_len & 0xFF
    desc[3] = (rec_len >> 8) & 0xFF
    desc[4:14] = name.encode("ascii")[:10].ljust(10, b" ")
    desc[14] = _checksum(desc[:14])

    # Data block: 512 bytes, only first rec_len bytes are meaningful
    block = bytearray(DATA_BYTES)
    block[: len(data)] = data
    data_cs = _checksum(block)

    sector = bytes(sec_header) + bytes(desc) + bytes(block) + bytes([data_cs])
    assert len(sector) == SECTOR_BYTES
    return sector


def _make_mdr(sectors: list[bytes], pad_total: int = MIN_SECTORS) -> bytes:
    """Pad with empty/blank sectors (rec_flag bit 0 set = "USED" -> skipped)
    so we hit the MIN_SECTORS threshold."""
    blank = _make_sector(rec_flag=0x01, name="empty", data=b"")
    while len(sectors) < pad_total:
        sectors.append(blank)
    return b"".join(sectors)


def _file_header(file_type: int, length: int, addr: int) -> bytes:
    return bytes([file_type]) + struct.pack("<HH", length, addr) + b"\x00\x00\x00\x00"


def test_parse_extracts_single_record_code_file():
    s = make_screen(0xFF, 0x07)
    body = _file_header(TYPE_CODE, 6912, 0x4000) + s
    # Need 6921 bytes split across records of <= 512 bytes each.
    chunks = [body[i : i + DATA_BYTES] for i in range(0, len(body), DATA_BYTES)]
    sectors = [_make_sector(rec_num=i, rec_len=len(chunk), name="screen", data=chunk) for i, chunk in enumerate(chunks)]
    mdr = _make_mdr(sectors)
    files = list(parse_mdr_files(mdr))
    assert len(files) == 1
    assert files[0].type == TYPE_CODE
    assert files[0].length == 6912
    assert files[0].start_addr == 0x4000
    assert files[0].body == s


def test_extract_screens_single_screen():
    s = make_screen(0xFF, 0x07)
    body = _file_header(TYPE_CODE, 6912, 0x4000) + s
    chunks = [body[i : i + DATA_BYTES] for i in range(0, len(body), DATA_BYTES)]
    sectors = [_make_sector(rec_num=i, rec_len=len(chunk), name="pic", data=chunk) for i, chunk in enumerate(chunks)]
    assert extract_screens(_make_mdr(sectors)) == [s]


def test_records_are_reordered_by_rec_num():
    s = make_screen(0xFF, 0x07)
    body = _file_header(TYPE_CODE, 6912, 0x4000) + s
    chunks = [body[i : i + DATA_BYTES] for i in range(0, len(body), DATA_BYTES)]
    # Build sectors in REVERSE order — parser must sort by rec_num.
    sectors = [_make_sector(rec_num=i, rec_len=len(chunk), name="pic", data=chunk) for i, chunk in enumerate(chunks)][
        ::-1
    ]
    assert extract_screens(_make_mdr(sectors)) == [s]


def test_skips_sectors_with_bad_data_checksum():
    s = make_screen(0xFF, 0x07)
    body = _file_header(TYPE_CODE, 6912, 0x4000) + s
    chunks = [body[i : i + DATA_BYTES] for i in range(0, len(body), DATA_BYTES)]
    sectors = [_make_sector(rec_num=i, rec_len=len(chunk), name="pic", data=chunk) for i, chunk in enumerate(chunks)]
    # Corrupt one record's data checksum -> that record drops out -> file
    # is incomplete and gets skipped.
    bad = bytearray(sectors[1])
    bad[-1] ^= 0xFF
    sectors[1] = bytes(bad)
    assert extract_screens(_make_mdr(sectors)) == []


def test_rejects_too_short_image():
    short = b"\x00" * (SECTOR_BYTES * (MIN_SECTORS - 1))
    assert list(parse_mdr_files(short)) == []


def test_classic_size_with_trailing_byte_is_accepted():
    s = make_screen(0xFF, 0x07)
    body = _file_header(TYPE_CODE, 6912, 0x4000) + s
    chunks = [body[i : i + DATA_BYTES] for i in range(0, len(body), DATA_BYTES)]
    sectors = [_make_sector(rec_num=i, rec_len=len(chunk), name="pic", data=chunk) for i, chunk in enumerate(chunks)]
    mdr = _make_mdr(sectors, pad_total=254) + b"\x00"  # write-protect byte
    assert len(mdr) == 254 * 543 + 1
    assert extract_screens(mdr) == [s]


def test_basic_only_cartridge_yields_no_screens():
    body = _file_header(TYPE_BASIC, 100, 10) + b"\x00" * 100
    chunks = [body[i : i + DATA_BYTES] for i in range(0, len(body), DATA_BYTES)]
    sectors = [_make_sector(rec_num=i, rec_len=len(chunk), name="loader", data=chunk) for i, chunk in enumerate(chunks)]
    assert extract_screens(_make_mdr(sectors)) == []


# --- Pillow integration ---------------------------------------------------


def test_pillow_open_mdr(tmp_path):
    s = make_screen(0xFF, 0x07)
    body = _file_header(TYPE_CODE, 6912, 0x4000) + s
    chunks = [body[i : i + DATA_BYTES] for i in range(0, len(body), DATA_BYTES)]
    sectors = [_make_sector(rec_num=i, rec_len=len(chunk), name="pic", data=chunk) for i, chunk in enumerate(chunks)]
    p = tmp_path / "synth.mdr"
    p.write_bytes(_make_mdr(sectors))
    img = Image.open(p)
    assert img.format == "ZXMDR"
    assert img.size == (256, 192)
    img.load()


def test_pillow_rejects_non_mdr(tmp_path):
    p = tmp_path / "junk.mdr"
    # Right kind of length, but no valid sectors (everything zero).
    p.write_bytes(b"\x00" * (SECTOR_BYTES * 50))
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)

from pillow_retro_tape.plus3dos import (
    HEADER_LEN,
    PLUS3DOS_MAGIC,
    TYPE_CODE,
    TYPE_PROGRAM,
    find_plus3_files,
    make_plus3_header,
    parse_at,
)


def test_make_header_round_trip():
    body = b"\xff" * 6912
    header = make_plus3_header(TYPE_CODE, len(body), 0x4000)
    assert header[:9] == PLUS3DOS_MAGIC
    assert len(header) == HEADER_LEN
    f = parse_at(header + body, 0)
    assert f is not None
    assert f.type == TYPE_CODE
    assert f.length == 6912
    assert f.param1 == 0x4000
    assert f.body == body


def test_parse_at_rejects_wrong_offset():
    body = b"\x00" * 100
    header = make_plus3_header(TYPE_PROGRAM, len(body), 5)
    data = b"junk_____" + header + body
    assert parse_at(data, 0) is None  # magic isn't at offset 0
    assert parse_at(data, 9) is not None


def test_parse_at_rejects_bad_checksum():
    body = b"\x42" * 32
    header = bytearray(make_plus3_header(TYPE_CODE, len(body), 0x6000))
    header[127] ^= 0xFF
    assert parse_at(bytes(header) + body, 0) is None


def test_parse_at_rejects_truncated_body():
    body = b"\x42" * 32
    header = make_plus3_header(TYPE_CODE, len(body), 0x6000)
    truncated = header + body[:-1]
    assert parse_at(truncated, 0) is None


def test_find_plus3_files_only_at_aligned_offsets():
    body = b"\x42" * 64
    header = make_plus3_header(TYPE_CODE, len(body), 0x4000)
    # Place a fake header on a non-512-aligned offset. find_plus3_files
    # with default align=512 should not see it.
    block = bytearray(2048)
    block[100 : 100 + HEADER_LEN] = header
    block[100 + HEADER_LEN : 100 + HEADER_LEN + len(body)] = body
    assert list(find_plus3_files(bytes(block))) == []

    # Same data at offset 512 -> found
    block2 = bytearray(2048)
    block2[512 : 512 + HEADER_LEN] = header
    block2[512 + HEADER_LEN : 512 + HEADER_LEN + len(body)] = body
    found = list(find_plus3_files(bytes(block2)))
    assert len(found) == 1
    assert found[0].offset == 512
    assert found[0].body == body


def test_find_plus3_files_finds_multiple():
    body_a = b"\x01" * 32
    body_b = b"\x02" * 64
    block = bytearray(2048)
    h_a = make_plus3_header(TYPE_CODE, len(body_a), 0x6000)
    h_b = make_plus3_header(TYPE_PROGRAM, len(body_b), 5)
    block[0:HEADER_LEN] = h_a
    block[HEADER_LEN : HEADER_LEN + len(body_a)] = body_a
    block[512 : 512 + HEADER_LEN] = h_b
    block[512 + HEADER_LEN : 512 + HEADER_LEN + len(body_b)] = body_b
    found = list(find_plus3_files(bytes(block)))
    assert [f.type for f in found] == [TYPE_CODE, TYPE_PROGRAM]
    assert found[0].body == body_a
    assert found[1].body == body_b

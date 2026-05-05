from pillow_retro_tape.disk import DiskImage, Sector


def test_logical_sectors_sorts_by_track_side_id():
    raw = [
        Sector(track=1, side=0, sector_id=2, data=b"a"),
        Sector(track=0, side=0, sector_id=9, data=b"b"),
        Sector(track=0, side=0, sector_id=1, data=b"c"),
        Sector(track=0, side=1, sector_id=1, data=b"d"),
    ]
    img = DiskImage(tracks=2, sides=2, sectors=raw)
    ordered = list(img.logical_sectors())
    assert [(s.track, s.side, s.sector_id) for s in ordered] == [
        (0, 0, 1),
        (0, 0, 9),
        (0, 1, 1),
        (1, 0, 2),
    ]


def test_flat_concatenates_in_logical_order():
    raw = [
        Sector(track=0, side=0, sector_id=2, data=b"BB"),
        Sector(track=0, side=0, sector_id=1, data=b"AA"),
        Sector(track=0, side=0, sector_id=3, data=b"CC"),
    ]
    img = DiskImage(tracks=1, sides=1, sectors=raw)
    assert img.flat() == b"AABBCC"

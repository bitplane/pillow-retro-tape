"""The ``zx-screen`` command line tool.

Loads a ZX Spectrum screen from a tape, disk or snapshot file and opens
it in the system image viewer (or saves it with ``--output``).
"""

import argparse
import sys

from PIL import Image, UnidentifiedImageError

PROG = "zx-screen"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Load a ZX Spectrum screen from a tape, disk or snapshot file and open it.",
    )
    parser.add_argument(
        "file",
        help="tape, disk or snapshot file (.tap, .tzx, .scr, .dsk, .trd, .sna, .z80, ...)",
    )
    parser.add_argument(
        "--frame",
        type=int,
        default=0,
        help="screen to pick from multi-screen containers (default: 0)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="save the screen to FILE (format from extension) instead of opening a viewer",
    )
    args = parser.parse_args(argv)

    try:
        img = Image.open(args.file)
    except FileNotFoundError:
        print(f"{PROG}: {args.file}: file not found", file=sys.stderr)
        return 1
    except UnidentifiedImageError:
        print(f"{PROG}: {args.file}: no ZX Spectrum screen found", file=sys.stderr)
        return 1

    try:
        img.seek(args.frame)
    except EOFError:
        n = getattr(img, "n_frames", 1)
        print(f"{PROG}: {args.file}: no frame {args.frame} (file has {n})", file=sys.stderr)
        return 1

    if args.output:
        img.save(args.output)
    else:
        img.show(title=args.file)
    return 0

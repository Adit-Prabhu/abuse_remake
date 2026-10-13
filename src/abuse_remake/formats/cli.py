"""``abuse-data``: verify and summarise the vendored original data."""

from __future__ import annotations

import argparse
import collections
import hashlib
import sys
from pathlib import Path

from ..paths import data_root, level_path
from .level_file import load_level
from .tiles import load_palette, load_tiles


def verify(root: Path) -> list[str]:
    """Return a list of problems; empty means every file matches SHA256SUMS."""
    sums = root / "SHA256SUMS"
    if not sums.exists():
        return [f"missing {sums}"]
    problems = []
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        path = root / rel.strip()
        if not path.exists():
            problems.append(f"missing {rel}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"checksum mismatch {rel}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="abuse-data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="check vendored data against SHA256SUMS")
    info = sub.add_parser("info", help="summarise a level file")
    info.add_argument("--level", default="level01")
    args = parser.parse_args(argv)

    root = data_root()
    if args.cmd == "verify":
        problems = verify(root)
        for p in problems:
            print("FAIL", p)
        if problems:
            return 1
        print(f"PASS all files under {root} match SHA256SUMS")
        return 0

    lv = load_level(level_path(args.level))
    tiles = load_tiles(root)
    pal = load_palette(root)
    counts = collections.Counter(o.type_name for o in lv.objects)
    print(f"{args.level}: {lv.fg_width}x{lv.fg_height} fg tiles, {lv.bg_width}x{lv.bg_height} bg tiles")
    print(f"{len(lv.objects)} objects, {sum(len(o.links) for o in lv.objects)} links, "
          f"{len(lv.lights)} lights, {len(lv.areas)} areas")
    print(f"{len(tiles.fore)} foreground and {len(tiles.back)} background tiles; {len(pal.colors)} colours")
    for name, n in counts.most_common():
        print(f"  {n:4d} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

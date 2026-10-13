"""Differential tests: the Python port against the original C, compiled from verbatim source.

tests/c_reference/*.c wrap functions copied unchanged from historicalsource/abuse@01cce80.
CI sets ABUSE_REQUIRE_C_REFERENCE=1, so a missing compiler fails instead of skipping.
"""

import random
import subprocess

from abuse_remake.formats.images import Boundary, Figure, PointList
from abuse_remake.formats.spec import SPEC_CHARACTER, SPEC_CHARACTER2, SpecError, SpecFile
from abuse_remake.formats.tiles import load_tiles
from abuse_remake.paths import data_root


def run_inside_reference(binary, polygons):
    lines = []
    for pts in polygons:
        flat = " ".join(f"{x} {y}" for x, y in pts)
        lines.append(f"{len(pts)} {flat}")
    out = subprocess.run([str(binary)], input="\n".join(lines) + "\n", capture_output=True,
                         text=True, check=True).stdout.splitlines()
    result = []
    for line in out:
        fwd, flp = line.split("|")
        result.append((tuple(int(v) for v in fwd.split()), tuple(int(v) for v in flp.split())))
    return result


def python_inside(pts):
    pl = PointList(tuple(pts))
    return (Boundary.from_points(pl).inside, Boundary.from_points(pl, flipped=True).inside)


def shipped_polygons():
    tiles = load_tiles(data_root())
    polygons = [t.boundary.points for t in tiles.fore.values() if t.boundary.tot >= 2]
    for path in sorted(data_root().joinpath("art").rglob("*.spe")):
        try:
            spec = SpecFile.open(path)
        except SpecError:
            continue  # art/tints/cop/gray.spe is a bare 4096-byte table, not a SPEC file
        for e in spec.entries:
            if e.type in (SPEC_CHARACTER, SPEC_CHARACTER2):
                fig = Figure.read(spec.reader(e), e.type)
                if fig.f_damage.tot >= 2:
                    polygons.append(fig.f_damage.points)
    return polygons


def test_inside_flags_match_original_on_every_shipped_outline(c_reference):
    binary = c_reference("boundary_inside")
    polygons = shipped_polygons()
    assert len(polygons) == 998  # 223 tile outlines + 775 sprite damage outlines in the pinned data
    expected = run_inside_reference(binary, polygons)
    for pts, exp in zip(polygons, expected, strict=True):
        assert python_inside(pts) == exp, pts


def test_inside_flags_match_original_on_random_polygons(c_reference):
    binary = c_reference("boundary_inside")
    rng = random.Random(1995)
    polygons = []
    for _ in range(400):
        n = rng.randint(3, 9)
        pts = [(rng.randint(0, 30), rng.randint(0, 20)) for _ in range(n)]
        pts.append(pts[0])  # closed, as the loader requires
        polygons.append(pts)
    expected = run_inside_reference(binary, polygons)
    for pts, exp in zip(polygons, expected, strict=True):
        assert python_inside(pts) == exp, pts

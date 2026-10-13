# Rule and source map

Every rule the reconstruction enforces, where our code implements it, and the evidence for it.

## Evidence labels

The labels follow the course convention:

| Label | Meaning |
|---|---|
| `code` | Read from the original C engine (`historicalsource/abuse@01cce80`, cited as `abuse/src/file.c:line`) or the original Lisp (`data/original/lisp/file.lsp:line`). |
| `manual` | Stated in the original manual or release notes. |
| `observed` | Seen by running something; the method is named. |
| `assumed` | Not yet backed by evidence. Each one is listed under "Open questions". |

For the Lisp's relation to the 1996 retail release, see `docs/data-lineage.md`.

This map grows with each milestone. Rows for the engine, objects and player interface are added
by the PRs that implement them.

## Timing and episode

| Rule | Our code | Evidence |
|---|---|---|
| Game logic runs at most 15 frames per second; faster frames are delayed | `scope.TICKS_PER_SECOND` | `code`: `abuse/src/game.c:1630-1633` (`calc_speed`). Corroborated by `manual`: the release note's "the 15 Hz (i believe) updates" (historicalsource `README`). |
| One engine tick per original frame, at a fixed 15 Hz, with rendering interpolated in between | `scope.TICKS_PER_SECOND` | `assumed`: the original slows down on hardware that cannot reach 15 fps; we model the full-speed case |
| Episode limits: 9000 ticks for the full level, 2700 for checkpoint segments | `scope.FULL_LEVEL_TICK_LIMIT`, `scope.SEGMENT_TICK_LIMIT` | course choice, not a rule of the game |
| Every object type in `level01.spe` is in scope | `scope.LEVEL01_TYPES` | `observed`: `tests/test_scope.py` reads the level file |

## Data formats

| Rule | Our code | Evidence |
|---|---|---|
| SPEC1.0 container: signature, u16 count, then per entry type, name, flags, size, offset | `formats/spec.py` `SpecFile` | `code`: `imlib/specs.c:739-789`, `imlib/include/specs.hpp` (layout comment) |
| `find` returns the first entry with a matching name | `SpecFile.find` | `code`: `imlib/specs.c:680-688` |
| Image: u16 width, u16 height, then palette indices; index 0 is transparent in sprites | `formats/images.py` `Image` | `code`: `imlib/image.c:132`; `trans_image` |
| Point list: u8 count, then (x, y) byte pairs | `PointList` | `code`: `abuse/src/points.c:17` |
| Boundary "inside" flags; the flipped copy checks vertical segments to the right | `images._inside_flags` | `code`: `abuse/src/items.c:8-98` and `:100-183`; the difference is at `items.c:42` versus `:125` |
| Character frame: image, hit damage, `xcfg`, signed advance, damage boundary, hit list | `Figure.read` | `code`: `abuse/src/items.c:270-292`, `abuse/inc/items.hpp:51-58` |
| Palette: u16 count, then RGB byte triples (8 bits per channel) | `tiles.Palette` | `code`: `imlib/palette.c:22-31`; `observed`: values above 63 in `backgrnd.spe` |
| A tile's number is its entry name; a later file redefines an earlier number | `tiles.load_tiles` | `code`: `abuse/src/loader2.c:157-264` |
| Tile file order | `tiles.TILE_FILES` | `code`: `data/original/lisp/startup.lsp:36-54` |
| Tile grid is the size of tile 0: foreground 30x15, background 60x30 | `TileSet.grid_sizes` | `code`: `abuse/src/loader2.c:439-442`; `observed`: `tests/test_formats.py` |
| Foretile: image, u16 next, u8 damage (unused), boundary | `tiles.load_tiles` | `code`: `abuse/src/items.c:197-257` |
| Level maps: u32 width, u32 height, u16 cells; the foreground value is `cell & 0x3FFF` | `level_file._read_map`, `fg_tile` | `code`: `abuse/src/level.c:1303-1335`, `abuse/inc/level.hpp:22-24` |
| With no `player_info`, the 0x8000 seen bit is cleared; cells naming missing tiles become 0 | `load_level` | `code`: `abuse/src/level.c:1357-1374` |
| Objects: per-type names, states and local variables; then one array per base variable | `level_file._load_objects` | `code`: `abuse/src/level.c:1005-1240`, `abuse/src/objects.c:47-82` |
| `direction`, `active`, `fade_dir` and `frame_dir` are signed chars; `cur_frame` is a short | `SIGNED_CHAR_VARS`, `SIGNED_SHORT_VARS` | `code`: `abuse/inc/extend.hpp` (`simple_object`) |
| An lvar whose type byte is not `RC_L` stops lvar loading | `_load_objects` | `code`: `abuse/src/level.c:1166-1190` |
| Objects with an unknown type or negative x or y are deleted after loading | `LevelObject.removed_on_load` | `code`: `abuse/src/level.c:1393-1399` |
| Links: 1-based object numbers. A target of 0 or less is a player; 0 resolves to NULL and is ignored | `level_file._load_links` | `code`: `abuse/src/level.c:2001-2050`, `abuse/src/objects.c:1503-1510`, `abuse/src/extend.c:49-57` |
| Areas: x, y, w, h, active, ambient, view offsets and speeds (signed) | `AreaController` | `code`: `abuse/src/level.c:2085-2144` |
| Lights: count, minimum light level, then x, y, shifts, radii and a type byte | `level_file.Light` | `code`: `abuse/src/light.c:1243-1272` |

## Open questions

- `assumed`: the fixed 15 Hz tick. See the timing table.

# Provenance of `data/original/`

All files here except this note and `SHA256SUMS` are copied unchanged from the upstreams listed
below. `SHA256SUMS` pins each one, and `uv run abuse-data verify` (also run in CI) checks them.

## Where it came from

| Path here | Upstream | Commit |
|---|---|---|
| `art/**`, `lisp/**`, `levels/level01.spe`, `abuse.lsp` | `https://github.com/Xenoveritas/abuse`, folder `data/` | `9d1f66f57377859bae10e28eabebea0b9c750490` (2022-10-27) |
| `COPYING.upstream` | the same repository's `COPYING` | same |
| `levels/level00.spe`, `levels/level02.spe` | `LEVELS/LEVEL00.SPE` and `LEVELS/LEVEL02.SPE` in the 1995 shareware v1.01 release, `https://archive.org/download/Abuse_454/ABUSE101.zip` | zip SHA-256 `4e3db6ca92e53d9cd5037127fb0d4d061f017ded8426fdb2a1e80f888ba5a4df` |

The two shareware levels were added on 2026-10-14 for Remastered mode's campaign (the training
level and Level 2; see `docs/remastered.md`). They are copied byte for byte from the release zip,
which `scripts/compare_original_data.py` already downloads and pins. The upstream repository also
has these levels, but its copies are the 2.00 versions, which match the `abuse-lib-2.00` data set
this repository treats as retail and never commits. So the shareware copies are used. They were
built against the 1995 shareware Lisp, while the rules we port are the 2.0-era Lisp (see
`docs/data-lineage.md`); Remastered labels any difference this causes.

The upstream copy descends from the abuse.zoy.org packaging. It is **not** a pristine 1996 copy:
the packaging adds community edits made between 1996 and 2008, and its `abuse.lsp` differs from
the one in the source release.

`docs/data-lineage.md` compares it with two original Crack dot Com releases:

- `levels/level01.spe` and the palette and tiles used by Level 1 are byte-identical to the 1995
  shareware v1.01 and the 1996 retail 2.00 releases.
- The Lisp matches retail 2.00 in 401 of 409 shared definitions. None of the 8 differences
  changes a Level 1 rule.

The C engine we port lives at `https://github.com/historicalsource/abuse`, commit
`01cce80eaf2ae82bafb9981162e205e42d0fae2f`. It is cited by file and line in
`docs/rule-source-map.md`; it is not copied here.

## Licence, as the sources state it

Crack dot Com's release note (`README` at the historicalsource commit above) says:

> Crack dot Com is hereby releasing the source code to Abuse to the public domain.

It keeps ownership of the "retail" and "registered" data sets, "the levels, sound effects,
music, artwork and other data which are NOT common to the 'shareware' release of the game". It
says Crack is "NOT releasing the full data set to the public domain". It also lists, among
things you can do:

> Use pieces of the source code or shareware data (excluding the WAV's-
> you must speak to Bobby Prince) however you see fit.

So the source code is public domain, and the shareware data comes with a use permission. The
upstream `COPYING.upstream` also lists `data/*` as "released in the public domain".

Level 1 is part of the shareware release, and the file is byte-identical to shareware v1.01. The
retail 2.00 data is used only for comparison and is never committed.

**Not included:**

- The sound effects and music (`sfx/`, `music/`): Bobby Prince's copyright. The game uses CC0
  replacement audio from `assets/`.
- The retail and registered data sets.

## What is used

- `levels/level01.spe`: the agreed scope (see `SCOPE.md`).
- `levels/level00.spe`, `levels/level02.spe`: Remastered mode only (the training level and
  Level 2). Classic mode and the agent evaluations never load them.
- `art/back/backgrnd.spe`: the palette and background tiles. The other tile sets come from the
  `startup.lsp` list.
- `art/*.spe`, `art/chars/*.spe`: sprites for the player, enemies, items and logic objects.
- `lisp/*.lsp`: kept as the rule source. The engine hand-ports these scripts and never runs them.

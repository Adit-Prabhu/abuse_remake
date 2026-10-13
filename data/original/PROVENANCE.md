# Provenance of `data/original/`

Every data file in this folder (everything except this note and `SHA256SUMS`) is unmodified
original Abuse data. `SHA256SUMS` pins each one, and
`uv run abuse-data verify` (also run in CI) checks them.

## Where it came from

| Path here | Upstream | Commit |
|---|---|---|
| `art/**`, `lisp/**`, `levels/level01.spe`, `abuse.lsp` | `https://github.com/Xenoveritas/abuse`, folder `data/` | `9d1f66f57377859bae10e28eabebea0b9c750490` (2022-10-27) |
| `COPYING.upstream` | the same repository's `COPYING` | same |

The C engine we port from lives in `https://github.com/historicalsource/abuse` at
`01cce80eaf2ae82bafb9981162e205e42d0fae2f`. It is cited by file and line in
`docs/rule-source-map.md`, but not copied here.

## Licence

Crack dot Com placed the Abuse source code and the shareware data in the public domain. Their
release note (the `README` at the historicalsource commit above) says:

> Use pieces of the source code or shareware data (excluding the WAV's — you must speak to
> Bobby Prince) however you see fit.

`COPYING.upstream` also lists `data/*` as "released in the public domain". The levels, art and
Lisp scripts here are public domain.

**Not included:** the sound effects and music (`sfx/`, `music/`), which are Bobby Prince's
copyright, and the retail or registered data sets, which Crack dot Com did not release. The game
uses CC0 replacement audio from `assets/`. `scripts/fetch_original_audio.py` can download the
original sounds into the git-ignored `local-audio/` folder for your own personal use.

## What is used

- `levels/level01.spe`: the agreed scope (see `SCOPE.md`).
- `art/back/backgrnd.spe`: the palette and background tiles. The other tile sets come from the
  `startup.lsp` list.
- `art/*.spe`, `art/chars/*.spe`: sprites for the player, enemies, items and logic objects.
- `lisp/*.lsp`: kept as the rule source. The engine hand-ports these scripts and never runs them.

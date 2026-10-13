# abuse_remake

A reconstruction of **Level 1 of Abuse** (Crack dot Com, 1996) in Python, with a model-driven
player and a scripted baseline. This is a COMS E6998 midterm project.

- The scope record is `SCOPE.md`. `data/original/PROVENANCE.md` gives the data's provenance
  and licence terms. `docs/data-lineage.md` shows that Level 1 is byte-identical to the 1995
  and 1996 releases, and that the rule scripts match the 1996 retail Lisp.
- The game logic is a deterministic port of the original C engine and Lisp rules, running at
  15 ticks per second. Every rule is cited in `docs/rule-source-map.md`.
- Classic mode is the faithful port. Remastered mode adds modern features on top.

## Quick start

```sh
uv sync --all-extras
uv run abuse-data verify        # check the original data files
uv run abuse-data info          # summarise Level 1
uv run pytest                   # deterministic tests
```

## Status

This repo is under construction. Work is split into milestone PRs:

1. **Data readers and scaffold** (this PR): the SPEC container, palette, tiles, sprites and
   level file, plus CI.
2. Engine core: physics, collision and the player.
3. Every Level 1 object.
4. The playable game.
5. The player interface.
6. Baselines and evaluation.
7. The model player.
8. Remastered mode.
9. Evidence and release.

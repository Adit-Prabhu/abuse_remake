# Instructions for development agents

This repo reconstructs Level 1 of Abuse (1996) and builds a model-driven player for it.
It is a COMS E6998 midterm. Read `SCOPE.md` first.

## Roles

- The student is Executive Producer and Creative Director. They own scope, priorities,
  acceptance, merges, tags and gate decisions.
- An agent never merges a PR, pushes a tag, approves its own work or changes deadlines.
- Never put secrets, API keys or personal playtester data in code, prompts, traces, reports or
  recordings. Model settings belong in `agent-config.json`; resolved model IDs belong in
  evaluation reports.

## Architecture rules

- `src/abuse_remake/engine/` is the authoritative game state. It is pure Python, deterministic
  (seeded RNG, fixed 15 Hz tick), and must not import pygame.
- `src/abuse_remake/game/` renders and reads input. It never changes rules.
- `src/abuse_remake/agent/` is the playing-agent interface. A player sees only what
  `observe()`, `legal_actions()` and `step()` return. It never sees the World object, level
  files, `docs/rule-source-map.md` or credentials.
- Development tools (tests, scripts, this file) are separate from the player's
  observation/action interface.
- Classic mode is the faithful port. Anything that changes a rule lives behind
  `--mode remastered`, and fidelity tests and evaluations run in Classic mode.

## Changing a rule

Follow `.claude/skills/port-classic-rule/SKILL.md`:

1. Cite the original source (`historicalsource/abuse@01cce80` for C, `data/original/lisp` for
   Lisp) and add or update a row in `docs/rule-source-map.md` with the strongest honest label:
   `code`, `manual`, `observed` or `assumed`.
2. Write the failing test first.
3. Port the rule.
4. Check the player boundary.
5. Hand the summary to the independent reviewer (`.claude/agents/rules-reviewer.md`). Never
   review your own change.

## Commands

```sh
uv sync --all-extras
uv run pytest                 # deterministic tests, no network
uv run abuse-data verify      # original data checksums
uv run ruff check src tests
uv run abuse-remake           # play
```

Live model calls need an explicit provider and credentials. Never spend credits during routine
review, and never silently substitute a fixture for a live evaluation.

## Git

- Work on feature branches only; never commit to `main`.
- No AI co-author trailers in commits and no "Generated with" footers in PRs. AI-use disclosure
  belongs in the course documents (`docs/agent-team-log.md`).

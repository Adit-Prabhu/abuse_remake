# Abuse, Level 1: a faithful reconstruction with a model-driven player

COMS E6998 midterm, by GitHub user `adit-prabhu`. The project rebuilds **Level 1 of Abuse**
(Crack dot Com, 1996) in Python from the public-domain C engine and the original Lisp rules, on
the original level file. A model-driven player plays it through a five-operation interface, and
is compared with a scripted search baseline on a suite declared before any tuning.

| | |
|---|---|
| Recording (3–5 min) | *link added when recorded* |
| Evaluation report | [`EVALUATION.md`](EVALUATION.md) |
| Agent-team log | `AGENT-TEAM.md`, written by the student (to come) |
| Peer playtest notes | [`docs/playtests/`](docs/playtests/) |
| Scope record | [`SCOPE.md`](SCOPE.md) |
| Declared suite | [`SUITE.md`](SUITE.md) |
| Rule/source map | [`docs/rule-source-map.md`](docs/rule-source-map.md) |

## Scope

**Graded: Classic mode, Level 1.** This is the whole first combat level:
- every object type in the original file (ants, turrets, boulders, switches, doors, force
  fields, hidden walls, teleporters, lifts, consoles, pickups, logic gates);
- the four weapons;
- the original 15 Hz physics.

You win by reaching the exit and pressing down. You lose by dying, and an episode can also end
at its tick limit. People play it with the original restart at the last console; agent
episodes end at death. Remastered mode (a campaign, Horde, a dash and more) is an optional layer
that is **not graded or evaluated**. Exclusions and dated scope changes are in
[`SCOPE.md`](SCOPE.md).

## Commands

Every command runs from the project folder: **`midterms/adit-prabhu/`** in the course
repository, or the root of the project repository. You need [uv](https://docs.astral.sh/uv/) and Python 3.11 or 3.12. A C
compiler is optional: without one, the differential tests against the original C are skipped
locally, and CI requires them. `ffmpeg` is needed only to write videos.

```sh
cd midterms/adit-prabhu                   # in the course repository
uv sync --all-extras                      # the game, the players and the model SDKs
```

**Play (the graded game):**

```sh
uv run abuse-remake --mode classic        # Classic Level 1: Enter on the title starts it
uv run abuse-remake                       # optional: Remastered (campaign, Horde, dash)
```

Controls:
- move: A/D or the arrows;
- jump: W, Up or Space;
- **action (switches, consoles, the exit): S or Down**;
- aim: the mouse; fire: the left button;
- weapons: 1–4, or Ctrl/Insert as in the original;
- pause: Esc; after a death, Space restarts at the last console;
- every control and HUD element: F1.

Gamepads work too.

**Test (deterministic, no network, no model calls):**

```sh
uv run pytest                             # rules, interface, limits, regressions, evidence replays
uv run abuse-data verify                  # the original data files match their checksums
uv run ruff check src tests scripts
```

**Watch and run the players:**

```sh
uv run abuse-replay --player scripted --scenario level01-cp3                      # spectate the baseline live
uv run abuse-replay --trace evidence/traces/offline-v5/scripted-level01-cp3-s0.jsonl  # replay a trace, checking every observation
uv run abuse-agent --player scripted --scenario level01-cp1 --seed 0 --trace runs/demo.jsonl
```

**Evaluate:**

```sh
uv run abuse-eval run --config eval/configs/offline.toml --jobs 6          # baselines only, no network
uv run abuse-eval estimate --config eval/configs/midterm.toml              # the declared suite: tokens and cost, no calls
# Live (Vertex AI, Gemini). Owner setup: gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=global COURSE_MODEL=<model id>
uv run abuse-eval run --config eval/configs/midterm.toml --live --jobs 6 --out runs/midterm
uv run abuse-eval report runs/midterm                                       # rebuild the report
```

Without `--live`, the model players are listed as "not run". No fixture ever stands in for
them. `docs/evaluation.md` has the full instructions, including the Anthropic and OpenAI
adapters.

## The player interface

`src/abuse_remake/agent/interface.py` implements the course's five operations:
- `reset(seed)`;
- `observe(player_id)`;
- `legal_actions(player_id)`;
- `step(player_id, action)`;
- `outcome()`.

Every player is a separate process speaking JSON lines (`agent/protocol.py`). It gets only the
observation and the legal actions, with no seed, no level file and no evaluator data. The
runner holds the authoritative game. Only the model player's process gets credentials, and only
the variables its provider's SDK reads. They never enter a prompt, an observation or a trace.

| What | Where |
|---|---|
| Observation and what is never shown (with the two judgement calls) | `docs/information-boundary.md` |
| Action vocabulary and invalid actions (refused, counted, fed back, never repaired) | `docs/action-interface.md` |
| Step, decision, tick, token, wall-clock and request limits, each with its own terminal reason | `docs/budgets.md` |
| The players | `agent/players/baselines.py` (random, scripted), `agent/players/model_player.py` with `agent/providers/` (Vertex, Anthropic, OpenAI) |

## Rules and sources

The rule/source map has **152 rows**, and each carries an evidence label with a locator:
- **122 `code`**: the C engine at `historicalsource/abuse@01cce80`, or the original Lisp,
  cited by file, almost always with lines;
- **1 `observed`**: the level file read directly, to list its object types;
- **2 `assumed`**: listed as open questions;
- **24 `design`**: our own choices, each with its kind (harness, course requirement,
  presentation, front end, port, Remastered) and its reason. They point to `SCOPE.md`,
  `SUITE.md`, `docs/action-interface.md`, `docs/budgets.md` and `docs/remastered.md`.

Some rows carry a second label. Three are `observed`: two values read from the original data
files, and the collision routine checked against the compiled original C (20,000 cases). One is
`manual`: the 15 Hz cap, which the release note mentions. Properties
of our own port that are not rules, such as the saved routes, are listed apart.

The game reads the original files directly:
- **The C engine** is public domain.
- **The levels, the palette and 64 art files** are byte-identical to the 1995 shareware
  release, whose note grants use "however you see fit".
- **The Lisp and the rest of the art** come from the abuse.zoy.org packaging, whose `COPYING`
  states they were released into the public domain. They include 2.0-era content, and the
  instructor is asked to confirm their publication.
- **The sounds and music** are not public domain and are not included: the game synthesises
  its own effects.

`data/original/PROVENANCE.md` quotes every term, pins every file's checksum, and sets out the
basis for publishing each part in this public repository. `docs/data-lineage.md` shows that the files match the
1995 and 1996 releases.

## Design choices and the alternatives they beat

| Choice | We chose | Instead of | Why |
|---|---|---|---|
| Game | Reconstruct one complete level of Abuse | An original game, or several levels | One level has a full loop, a real ending and checkable fidelity. Scope went into evidence, not size |
| Starting point | A clean Python port of the original C and Lisp | Adapting the C++/SDL port and its Lisp interpreter | A pure, deterministic, headless engine with the interface and tests built in. Every rule cites its source line, and two core routines (collision and boundary flags) are checked against the compiled original C |
| Timing | One logic tick per original frame, fixed at 15 Hz | A variable step, or a faster one | `game.c:1630-1633` caps the original at 15 Hz (`code`). That it ran at exactly the cap is `assumed`, an open question. A fixed step makes every episode reproducible |
| Actions | Macro actions (`wait`, `move`, `jump`, `explore`, `goto`, `use`, `attack`, `fire`, `weapon`), each 1–15 ticks, ending early when hurt or (except `attack` and `fire`) when a new threat appears | Raw inputs every tick (keys plus an aim angle) | Raw input means up to 9,000 calls per level and pixel-precise aim. Macros give one decision about every half second, and every player shares the same controllers, so the comparison is about decisions, not motor skill |
| Real time | The game pauses while a player decides | Running the clock during model latency | Slow players gain or lose no game time, so latency doesn't decide the result |
| Observation | What the 316x162 screen shows: visible objects, their visible state, tile classes, the HUD | The full map, or pixels | It is what the screen shows a player (`docs/information-boundary.md` lists the two judgement calls). The full map would leak the level; pixels would need a vision model at many times the cost |
| Navigation | `goto`/`explore` plan over tiles already seen (an automap) | A* over the whole map | Planning over unseen tiles would leak the layout |
| Secrets | An uncracked hidden wall shows as solid scenery; a cracked one can be named; `fire <direction>` shoots scenery | Naming every breakable wall | Six of the eight hidden-wall types look like ordinary scenery. Naming them leaked secrets, which a render of every type showed |
| Ending | Death ends an agent's episode | The original's respawn at the last console | A bounded episode with an explicit terminal reason. People keep the respawn |
| Situations | Three checkpoint segments plus the full level | The full level only | From the start, the scripted baseline stalls in the first section on every seed. Segments test the later parts and separate the players |
| Baseline | Scripted priority rules plus A* over the automap; random as a floor | Random only | Random is trivial. The scripted player is a real competitor with the same priors the model's prompt gets |
| Solver | A privileged engine search, reported as an upper reference | No solver | It shows which situations can be won, with a route CI replays, or reports that none was found. It reads engine state, so it never competes |
| History | `M1` (the last 8 turns) against `M0` (current screen only) | Persistent memory only, or none | The game is partly observed, so the question is whether bounded history helps. `M2` (notes and an automap summary) is implemented but cut from the suite to fit the budget |
| Metric | Wins, plus an evaluator-only progress measure | Wins only | Few wins are expected, and progress separates players that all lose. It is never shown to players |
| Invalid actions | Refused, counted, fed back; one decision spent | Repairing to the nearest legal action | Repairs would hide the model's errors and inflate its score |
| Model | Gemini flash-lite on Vertex AI | A larger model | The course credit covers it, and the brief names it as enough. The same adapter supports Anthropic and OpenAI. Latency and cost are measured in the run |

## Agent team

- **Implementation agent:** Claude Code, with `CLAUDE.md` and `AGENTS.md` as its instructions.
  It works on feature branches through stacked PRs and never merges.
- **Reusable skills:** `.claude/skills/port-classic-rule/` (cite, test first, port, check the
  boundary, hand to review) and `.claude/skills/agent-eval/`.
- **Independent reviewer:** `.claude/agents/rules-reviewer.md`, a read-only agent with a fresh
  context that never wrote the code. Its records are in `docs/reviews/`.
- **Playing agents:** the players above, with no repository tools.

The student's own log is `AGENT-TEAM.md`, written by the student (to come). The agents'
session-by-session record is `docs/agent-team-log.md`.

## Where this was built

The project was built in its own repository, [`Adit-Prabhu/abuse_remake`](https://github.com/Adit-Prabhu/abuse_remake),
through stacked, reviewed PRs (#1-#8, #15-#20, and the midterm fixes from #21). This folder is
an export of one commit of it, made by `scripts/export_submission.py`. `EVALUATION.md` gives
that commit and the git tree hash of `src/`, which every evaluation run records.

## Repository map

- `src/abuse_remake/formats/`: readers for the original SPEC files, tiles, sprites and levels.
- `src/abuse_remake/engine/`: the deterministic simulation. It is pure Python, with no pygame.
  `behaviors/` holds the hand-ported rules; `remastered.py`, `horde.py` and `campaign.py` are
  Remastered only.
- `src/abuse_remake/game/`: the pygame front end, which never changes rules, and `abuse-replay`.
- `src/abuse_remake/agent/`: the interface, players, providers, runner and `abuse-eval`.
- `data/original/`: the vendored original data, with checksums and provenance.
- `eval/configs/`, `evidence/`, `docs/`, `tests/`, `scripts/`, `.claude/`.

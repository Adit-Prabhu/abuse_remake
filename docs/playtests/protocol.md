# Peer playtest protocol

> Agents never write playtest notes. The student runs each session with real peers and writes
> the notes from `template.md`. Until then, this folder holds only the protocol and the template.

## Purpose

1. **Fidelity:** does Classic mode feel like the original Abuse Level 1 to someone who knows it,
   or who watches a recording of the original next to it?
2. **Human reference:** how far do human players get under the same scenarios and limits as the
   agents? Their traces give the evaluation a human baseline.
3. **Remastered:** are the new features (dash, quick restart, ghost race, Horde) fun, clear
   and fair?

## Before the session

- Get the player's consent to record inputs, and explain that only anonymous IDs (P1, P2, ...)
  are kept. Never record names, faces or voices in the repo.
- Build or install: `uv sync --all-extras`.
- Check the controls on the player's machine with `uv run abuse-remake --mode classic`.

## The session (about 25 minutes)

1. **Warm-up (3 min):** Remastered mode, any part of the level, to learn the controls.
2. **Classic run (10 min):** run `uv run abuse-remake --mode classic --playtest --seed 0`. Play
   from the start, aiming for the exit. The trace goes to `playtests/raw/`, which git ignores.
   Note deaths and where the player got stuck.
3. **Segment (5 min):** play from a checkpoint, if wanted. The agents' segment scenarios start at
   the three restart consoles.
4. **Remastered (5 min):** try the dash, quick restart and one Horde run (`--horde`).
5. **Questions (2 min):** the questions in `template.md`.

## Rules for the facilitator

- Do not coach during the timed runs. Answer control questions only.
- Write down what the player says while playing, word for word where you can.
- Count deaths, time to each console, and whether the player reached the exit.

## Afterwards

- Copy the notes into `docs/playtests/P<n>-<date>.md` from the template.
- Keep raw traces local. Commit a trace only with the player's consent, as
  `evidence/traces/human/P<n>-<scenario>.jsonl`, after removing anything personal. A trace holds
  only inputs and the seed.
- Turn findings into issues or PR tasks. Tag fidelity findings to a rule-map row where possible.

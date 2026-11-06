# Human playtest protocol (15 minutes)

> Agents never write playtest notes. The student runs the session and writes the notes. The
> course asks for at least one session in which someone else, anyone (a classmate, friend or
> family member), plays the build while the student watches without helping. This folder holds
> the protocol, the template and the notes (`received/`).

## Purpose

1. **Clarity and fun.** Can someone new finish or make progress in Classic Level 1 without
   help? What do they have to guess?
2. **The agent's view** (if time allows). Watching an agent's replay, can a person tell what it
   is trying to do, and is the display honest about it?
3. **A human reference.** How far does a person get under the same rules as the agents? (A
   person may restart at a console and an agent may not, so this is a reference, not a score.)

## Before the session

- Consent: say that only an anonymous ID (P1, P2, ...) is written down, with no names, faces
  or voices, and ask whether the input trace may be committed.
- Setup, from `midterms/adit-prabhu/` (or the project repository's root): `uv sync --all-extras`.
  Then check the controls once with `uv run abuse-remake --mode classic`.
- Optional: have a live model trace ready to replay, `evidence/traces/midterm/model-M1-level01-cp3-s2.jsonl`.

## The session

| Minutes | What | Command |
|---|---|---|
| 0–1 | Controls only: move, jump, aim and fire, **Down is the action key** | |
| 1–9 | **Classic Level 1 from the start**, thinking aloud. No coaching; answer control questions only | `uv run abuse-remake --mode classic --playtest --seed 0` |
| 9–12 | Optional: **watch the model player** play a recorded episode; ask "what is it trying to do?" | `uv run abuse-replay --trace <a live trace>` |
| 12–15 | The questions in `template.md` | |

Remastered (Horde, dash) is optional and only if time remains. It is not graded.

## While they play, write down

- what they did, and their words, verbatim where possible;
- each death, and where it happened;
- each place they hesitated, guessed or were stuck, and for how long;
- whether they found the consoles and the exit, and whether they knew Down was the action key.

## Afterwards

- Write the notes from `template.md` into `received/P<n>-<date>.md`.
- Score the trace with the agents' measure:
  `uv run abuse-replay --human-trace playtests/raw/session-<id>.jsonl`. It replays the session,
  checks every recorded state hash, and prints ticks, deaths, console saves, whether the exit
  was reached, and progress.
- Keep raw traces local (`playtests/raw/` is ignored by git). Commit one only with consent, as
  `evidence/traces/human/P<n>.jsonl`. A trace holds only inputs and the seed.
- Turn each finding into a change, or a line in the limitations of `EVALUATION.md`, and say
  which in the notes' follow-ups. Fidelity findings point to a rule-map row.
- If no session was possible, the limitations paragraph says so, gives the reason, and names
  what a playtest would have checked.

Notes on classmates' recordings (the silent-playtester peer review, due before class on
2026-11-16) are posted as Week 3 replies, not kept here.

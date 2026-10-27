# Peer playtest protocol (15 minutes)

> Agents never write playtest notes. The student runs the sessions and writes the notes; peers
> write theirs. This folder holds the protocol, the template and the notes:
> - `received/`: notes from peers who played this build;
> - `given/`: notes the student gave on a classmate's build.

## Purpose

1. **Clarity and fun.** Can someone new finish or make progress in Classic Level 1 without
   help? What do they have to guess?
2. **The agent's view.** Watching an agent's replay, can a person tell what it is trying to
   do, and is the display honest about it?
3. **A human reference.** How far does a person get under the same rules as the agents? (A
   person may restart at a console and an agent may not, so this is a reference, not a score.)

## Before the session

- Consent: say that only an anonymous ID (P1, P2, ...) is written down, with no names, faces
  or voices, and ask whether the input trace may be committed.
- Setup, from `midterms/adit-prabhu/`: `uv sync --all-extras`. Then check the controls once with
  `uv run abuse-remake --mode classic`.
- Have a live model trace ready to replay (`evidence/traces/`).

## The session

| Minutes | What | Command |
|---|---|---|
| 0–1 | Controls only: move, jump, aim and fire, **Down is the action key** | |
| 1–9 | **Classic Level 1 from the start**, thinking aloud. No coaching; answer control questions only | `uv run abuse-remake --mode classic --playtest --seed 0` |
| 9–12 | **Watch the model player** play a recorded episode; ask "what is it trying to do?" | `uv run abuse-replay --trace <a live trace>` |
| 12–15 | The questions in `template.md` | |

Remastered (Horde, dash) is optional and only if time remains. It is not graded.

## While they play, write down

- their words, verbatim where possible;
- each death, and where it happened;
- each place they were stuck, and for how long;
- whether they found the consoles and the exit, and whether they knew Down was the action key.

## Afterwards

- Write the notes from `template.md` into `received/P<n>-<date>.md`.
- Score the trace with the agents' measure:
  `uv run abuse-replay --human-trace playtests/raw/session-<id>.jsonl`. It replays the session,
  checks every recorded state hash, and prints ticks, deaths, console saves, whether the exit
  was reached, and progress.
- Keep raw traces local (`playtests/raw/` is ignored by git). Commit one only with consent, as
  `evidence/traces/human/P<n>.jsonl`. A trace holds only inputs and the seed.
- Turn each finding into a change, or a line in the limitations of `EVALUATION.md`. Fidelity
  findings point to a rule-map row.

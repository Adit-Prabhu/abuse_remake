# Human responsibility

> **Owner:** the student. **TODO (student):** read this, edit it to match how you worked, and
> sign it off before submission.

The student is the Executive Producer and Creative Director. Agents build and review; the
student decides and answers for the result.

## What the student owns

| Area | The student's responsibility | Where it shows |
|---|---|---|
| Scope | Agree the bounded classic (Level 1 of Abuse) in Session 2, and record any change with its date | `SCOPE.md` (TODO: confirm against the Session 2 agreement) |
| Direction | Choose the provider, the Classic/Remastered split and the repo hosting; approve the plan | `docs/agent-team-log.md` |
| Acceptance | Read each PR and its review record, decide every finding, and merge in order | PRs #1–#8, `docs/reviews/` |
| Fidelity claims | Accept or reject each `assumed` row and each open question in the rule map | `docs/rule-source-map.md` |
| Spending and credentials | Set up Vertex AI (ADC, project, region, `COURSE_MODEL`); fill in dated prices; approve each live run's estimate before it starts | `eval/configs/live.toml`, `abuse-eval estimate` |
| Evaluation conclusions | Decide what the live comparison shows and what it does not | `docs/evaluation-report.md` (after the live run) |
| Playtests | Recruit peers, run the protocol, get consent, write the notes. Agents never invent playtest notes | `docs/playtests/` |
| Demonstration | Record and narrate the demo | `docs/demo.md` |
| Release | Push the `v1.0.0` tag, which builds the release | `.github/workflows/release.yml` |
| Disclosure | State how AI was used | `docs/agent-team-log.md` |

## What agents may not do

- merge a PR, push a tag, approve their own work, or change deadlines;
- read, create or test credentials without asking, or put any secret in code, traces or reports;
- spend model credits without an approved estimate, retry failed paid requests, or substitute a
  fixture for a live player;
- invent playtest notes, prices, or results that were not run.

## Licences and data

- The engine is a clean Python port of the public-domain C code (`historicalsource/abuse`).
- The Level 1 data, art and Lisp come from the public-domain shareware release
  (`data/original/PROVENANCE.md`).
- The original sounds and music (Bobby Prince) are not public domain and are not in the repo;
  the game uses procedurally generated sound effects.
- The project is for personal and course use only, as the student stated.

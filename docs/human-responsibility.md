# Human responsibility

> **Owner:** the student. This page says who decides what. The student's own account of the work
> is `AGENT-TEAM.md`.

The student is the Executive Producer and Creative Director. Agents build and review; the
student decides and answers for the result.

## What the student owns

| Area | The student's responsibility | Where it shows |
|---|---|---|
| Scope | Choose the bounded classic (Level 1 of Abuse), record every change with its date, and post changes to the Week 3 thread | `SCOPE.md` (changes table) |
| Direction | Choose the provider, the Classic/Remastered split and the repo hosting; approve the plan | `docs/agent-team-log.md` |
| Acceptance | Read each PR and its review record, decide every finding, and merge in order | PRs #1–#8, #15–#20 and the midterm PRs from #21, `docs/reviews/` |
| Fidelity claims | Accept or reject each `assumed` row and each open question in the rule map | `docs/rule-source-map.md` |
| Spending and credentials | Set up Vertex AI (ADC, project, region, `COURSE_MODEL`); approve the spending cap (USD 10, 2026-10-26) and each run's estimate before it starts | `SUITE.md`, `eval/configs/midterm.toml`, `abuse-eval estimate` |
| Evaluation conclusions | Decide what the live comparison shows and what it does not, and write the limitations | `EVALUATION.md` |
| Playtests | Recruit peers, run the protocol, get consent, write the notes. Agents never invent playtest notes | `docs/playtests/` |
| Demonstration | Record and narrate the 3–5 minute recording | `docs/demo.md` |
| Submission | Open the course PR from `midterms/adit-prabhu/`, submit its URL on CourseWorks | the course repository |
| Disclosure | State how AI was used, in the student's own words | `AGENT-TEAM.md` |

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
- Publishing in the public course repository is covered by the release note's grant for the
  source code and shareware data (`data/original/PROVENANCE.md`, "Publishing in the public course
  repository").

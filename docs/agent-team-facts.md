# Agent-team facts (source material for `AGENT-TEAM.md`)

> **Written by the implementation agent, as source material.** The course asks for a one-page
> agent-team log in the student's own voice, and treats an agent-voiced log as missing. This
> page is not that log. It collects the checkable facts, with links, so the student can write
> `AGENT-TEAM.md` themselves: who did what, what each agent was allowed to see and do, what it
> recommended, what the student decided, and where the evidence is.

## The agents

| Agent | Allowed to see and do | Not allowed | Artifact |
|---|---|---|---|
| Implementation agent (Claude Code; Codex on 2026-10-15/16) | read and write the project repository, run tests, commit and push feature branches, open PRs; push a draft branch to the course repository (approved 2026-10-26) | merge, tag, approve its own work, spend model credits without an approved cap, read credentials without asking | `CLAUDE.md`, `AGENTS.md` |
| Skill: `port-classic-rule` | the agent's permissions; a fixed procedure (cite, map row, failing test first, port, boundary check, review) | | `.claude/skills/port-classic-rule/SKILL.md` |
| Skill: `agent-eval` | the agent's permissions; a fixed procedure for fair, estimated, approved live comparisons | live runs without approval | `.claude/skills/agent-eval/SKILL.md` |
| Independent reviewer (`rules-reviewer`) | read-only: Read, Grep, Glob, in a separate worktree, with a fresh context; it never wrote the code it reviews | edit, run, approve, merge | `.claude/agents/rules-reviewer.md`; records in `docs/reviews/` |
| Playing agents (random, scripted, the model) | only `observe`/`legal_actions`/`step` JSON, in a separate process | the repository, the World object, the seed, the evaluator's progress, credentials (except the model's own SDK variables) | `src/abuse_remake/agent/` |

## What the reviewers found (and what changed)

| PR | Reviewer's most important findings | Outcome | Record |
|---|---|---|---|
| #1 | provenance claims not backed by evidence | the data-lineage study | `docs/reviews/PR-1.md` |
| #4 | the second restart crashed the game | fixed, tested | `PR-4.md` |
| #6 | the Vertex SDK could send several billed requests per decision | one request per decision | `PR-6.md` |
| #18 | three dash cards made the player permanently invulnerable | a floor on the recharge | `PR-18.md` |
| #21 | the committed evidence went stale under the fix; two tests could not fail | evidence regenerated, every trace replayed in CI | `PR-21.md` |
| #23 | `SCOPE.md` claimed a Level 1 route that did not exist; the Lisp was called "shareware data" | honest scope and publication terms; it led to checking every hidden wall | `PR-23.md` |
| #24 | the export could delete uncommitted work; the eval smoke could not fail; solver results were claimed before they existed | a safe, tested export; a failing eval; honest claims | `PR-24.md` |
| #25 | **the observation leaked secrets** (camouflaged breakable walls were named); later, two walls misclassified, and players unable to return fire | each wall shown only as it looks; the aim fixed; three review rounds | `PR-25.md` |
| #27 | (in review) | | |

## Decisions the student made (dated)

| Date | Decision | Where it shows |
|---|---|---|
| 2026-10-13 | Abuse, Level 1 only; a Classic core plus a Remastered mode; Vertex/Gemini; a private repository; plan first | `SCOPE.md`, `docs/agent-team-log.md` |
| 2026-10-13 | stopped the agent's first attempt (credentials, wrong repository) | `docs/agent-team-log.md` |
| 2026-10-14 | grow Remastered before the required items, **against the agent's advice** | `SCOPE.md` changes table |
| 2026-10-26 | asked for an audit against the rubric ("be brutally honest") | `docs/reviews/midterm-audit-2026-10-26.md` |
| 2026-10-26 | build on the reviewed #15-#20 line; levels stay only if each is fully finishable; leave out the Codex polish and the bridge; drop Neon | the audit's header, `SCOPE.md` |
| 2026-10-26 | Vertex with a USD 10 cap; a draft course PR early; make the repository public after a secret scan | the audit's header, `SUITE.md` |
| 2026-10-26 | "fix it one by one", stacked PRs, aiming for 20/20; no AI co-author trailers | PRs #21-#27 |

## Things the student can say in their own words

These are prompts only, so the student can answer each in their own voice.

- Why Abuse, and why one level?
- Why grow Remastered first, and what did that cost? (The live comparison started two weeks
  before the deadline.)
- What did you learn from the reviews? For example, the hidden-wall leak was found only because
  a reviewer refused one screenshot as evidence for eight wall types.
- What would you do differently?
- How did you use the peer playtest notes?

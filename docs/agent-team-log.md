# Agent session record

> **Written by the implementation agents**, from the repository history and the working
> sessions. It is the detailed, agent-voiced record of who did what. **The student's own
> one-page log, in the student's voice, is [`AGENT-TEAM.md`](../AGENT-TEAM.md).** Where the two
> differ, the student's page is the account of record.

## Team

| Role | Who | Permissions | Artifact |
|---|---|---|---|
| Executive Producer, Creative Director | the student | owns scope, priorities, acceptance, every merge, the release tag, credentials and spending | `docs/human-responsibility.md` |
| Implementation agent | Claude Code (Claude Opus 5.5), in this repository | reads and writes the repo, runs tests, commits and pushes feature branches, opens PRs; never merges or tags; asks before touching credentials | `AGENTS.md`, `CLAUDE.md` |
| Independent reviewer | a fresh read-only Claude agent (`Explore` type) per milestone, briefed with `.claude/agents/rules-reviewer.md` | read-only: git objects, the vendored data, the installed SDKs; no edits, no network or model calls | `docs/reviews/PR-<n>.md` |
| Reusable skills | used by the implementation agent | its permissions | `.claude/skills/port-classic-rule/`, `.claude/skills/agent-eval/` |
| Playing agents | random, scripted (rules plus A* search), the model player (Gemini on Vertex by default) | the JSON-lines protocol only, in a separate process | `src/abuse_remake/agent/players/` |

## Human decisions (2026-10-13)

- Chose the classic: Abuse (`historicalsource/abuse`). Asked for a modern-feeling version with
  more features and the original gameplay pattern, using the freely available assets for
  personal use.
- Stopped the agent's first attempt, which started checking credentials and was working inside
  the course repo. The agent was told to plan first and to work in a separate repo. The agent
  now asks before touching credentials.
- Approved the plan, with four choices:
  - scope: **Level 1 only**;
  - live provider: **Vertex AI / Gemini**, with all three adapters built;
  - **a Classic core plus a Remastered mode**;
  - a **private GitHub repo**.
- Asked for frequent commits and pushes, in case of usage limits. The work went on across
  several usage-limit pauses.

## Handoffs

Each milestone is one stacked PR. The agent wrote the change, an independent reviewer read
it in a fresh context, and the agent fixed or recorded every finding. The student merges.

| PR | Milestone | Review |
|---|---|---|
| #1 | Scaffold, public-domain data, format readers | 1 blocking finding (provenance claims not backed by evidence). It led to the data-lineage study (`docs/data-lineage.md`) and the first differential test against compiled original C. `PR-1.md` |
| #2 | Engine core | No blocking findings. The fixes covered the view size (316x162), Lisp `*` semantics, test strength and citations. `PR-2.md` |
| #3 | Every Level 1 object | No fidelity bugs. 11 findings on tests, labels and citations, all fixed. `PR-3.md` |
| #4 | Playable game | Reviewed last, against the current code. 1 blocking finding: the second restart of a session crashed the game. 7 should-fix findings, including the camera not really interpolating and Classic lighting not following `light.c`. All fixed; human traces are now replayable. `PR-4.md` |
| #5 | Player interface, baselines, runner | Reviewed after #6 and #7, against the current code. No blocking findings; 4 should-fix findings. Among them: repeated events after a refusal, the seed reaching players, and `weapon laser` writing engine state. All fixed, with new controller tests. On the full level random and scripted are now level, which the evaluation reports. `PR-5.md` |
| #6 | Model player, providers, memory conditions, `abuse-eval` | 1 blocking finding (the Vertex SDK's automatic continuation could send several billed requests per decision) and 12 should-fix findings, all fixed. `PR-6.md` |
| #7 | Remastered mode | No blocking findings; 8 should-fix findings. Among them: spectating a model skipped the budgets, the replay check could pass a truncated trace, and playtests defaulted to Remastered rules. All fixed. The first review run was cut off by a usage limit and re-run. `PR-7.md` |
| #8 | Evidence, docs, release | This PR. Its own changes are docs, configuration and the release workflow |

## Remastered expansion (2026-10-14 and 15)

> Written by the implementation agent.

- **Human decisions.**
  - The agent advised finishing the required midterm items first. The student chose to extend
    Remastered first, and the midterm work after.
  - The student picked:
    - the shareware training level and Level 2;
    - the original four power-ups;
    - all four Horde upgrades.
  - The student approved the written plan (`~/.claude/plans/remastered-expansion.md`), and said
    "go ahead" and later "keep going".
- **Handoffs.** Five stacked PRs, #15-#19. A fresh read-only reviewer checked R1-R4, each in its
  own worktree; every review got a follow-up pass on the fixes.
  - R1: 1 blocking finding. Level 1 could not be finished while Level 2 was unported.
  - R2: no blocking findings. 1995-vs-2.0 differences were documented, and the weak tests made
    exact.
  - R3: no fidelity bugs; citations, wording and tests fixed.
  - R4: 1 blocking finding. Three dash cards made the player permanently invulnerable.
- **What went wrong.**
  - Unguided search could not finish Level 2. It is a long loop with switches, teleporters, a gate
    puzzle and enemies that must be fought. The route was built in segments, from scripted steps
    and short searches.
  - Several usage limits interrupted reviews, which were resumed.
  - A test that killed enemies outside a tick hid that Horde reads damage only from inside one.

## Remastered polish (2026-10-15)

> Written by the implementation agent.

- **Human decisions.** The student played the stack and listed what felt poorly made. They chose
  to seal the Horde arenas rather than open their lower floors, said the "white bars" were in the
  HUD and the black-backed ghost was the ghost race runner, and approved the written plan
  (`~/.claude/plans/remastered-polish.md`).
- **What went wrong.** Every screenshot and test ran on SDL's dummy driver, whose surfaces have
  no alpha channel. The macOS window has one, and on it the HUD's text and the ghost were drawn as
  solid boxes. The agent had reviewed only headless screenshots, so it never saw what the student
  saw. The fix was found by running the game on the real Cocoa driver. Display checks now include
  that, and `tests/test_display.py` stands in for the macOS format.
- **Handoffs.** One PR, #20, on #19. A fresh read-only reviewer checked the Horde engine change.

## What went wrong, and what changed

- **Provenance.** The agent first claimed a data lineage it had not verified. The PR #1
  reviewer flagged it, and the agent did the research and rewrote the provenance from evidence.
- **Port bugs that test thresholds hid.** Guessed thresholds hid real port bugs. The fix was to
  pin exact values taken from the original: background tile size, the atan table length, fall
  speed, `sin(270)`.
- **Agent-interface bugs found in testing:**
  - the last decision of every budget was refused;
  - actions could take zero ticks;
  - a bare non-JSON `wait` was accepted;
  - late replies were taken as answers to the next decision;
  - evaluator progress reached players in the end message;
  - player processes inherited credentials;
  - the baseline stopped fighting aliens after six shots.
  All are fixed and tested.

## AI use

The agent wrote the code, tests and docs. The agent also ran the reviews, as separate
read-only agents. The student directed the scope and the decisions. No model calls were made
for play or evaluation up to this point: every result in `evidence/` comes from the
deterministic baselines.

## Midterm fixes (2026-10-26)

> Written by the implementation agent.

- **Audit.** At the student's request, the agent audited the project against the course brief
  and rubric (`docs/reviews/midterm-audit-2026-10-26.md`). Its findings:
  - the model player had never made a live call;
  - nothing proved Level 1 could be finished;
  - there was no course folder, `EVALUATION.md`, recording or peer notes;
  - the agent-team log was agent-voiced;
  - the suite was oversized, with no held-out cases;
  - the decision-count bug was known but unfixed.
- **Student decisions.**
  - Build on the reviewed #15-#20 line. Leave out the Codex polish and the bridge, and drop Neon.
  - Vertex AI with a USD 10 cap.
  - Open a draft course PR early.
  - Make the repository public after a secret scan.
- **Handoffs.** Stacked PRs from #21. Each change to a rule or the interface gets a fresh
  read-only `rules-reviewer`, with a follow-up pass on the fixes.
  - #21: the decision that reaches the cap ran 0 ticks; fixed test-first. The review found
    stale evidence and tests that could not fail. The evidence was regenerated, and every
    committed trace now replays in CI.
  - #22: the suite was declared before any live call (`SUITE.md`).
  - #23: the rubric documents.

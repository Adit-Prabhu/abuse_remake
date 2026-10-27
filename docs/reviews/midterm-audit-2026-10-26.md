# Midterm audit and next steps

> **Record.** This is a production audit of the project against the course brief and rubric. The
> implementation agent (Claude Code) wrote it on 2026-10-26 at the student's request, reading
> `feat/codex-bridge` (`ee04947`), the open PRs and the course repository. It is kept as an
> inspectable recommendation.
>
> **The student's decisions on it, the same day:**
> - Build the submission on the reviewed #15-#20 line. Levels stay only if each is fully
>   finishable. The Codex polish and the bridge (`feat/codex-bridge`) are left out, and Neon is
>   out.
> - Live runs on Vertex AI, with a total spending cap of USD 10.
> - Open the course PR as a draft once its CI is ready.
> - Make the project repository public after a secret scan.
> - Fix the findings one by one, as stacked PRs from #21.


Audit date: **Monday 2026-10-26** (Session 7 checkpoint day). Submission: **Saturday 2026-11-07,
11:59 p.m.** That leaves 12 days, and one of those weeks has no class plus a required peer
playtest.

What I audited:
- the repo at `feat/codex-bridge` (`ee04947`), plus `main`, the open PRs #9–#20, and the local
  clone of `game-dev-f26`;
- I checked it against the midterm brief and the rubric, check by check;
- I ran the deterministic suite (398 passed, 54 s), ran `abuse-eval estimate` on the live
  config, read the offline traces, and ran the repo's own route solver on Level 1.

---

## 1. The verdict

**The engineering is excellent and mostly aimed at the wrong things. The experiment, which the
rubric actually grades, has not started.**

You have built a faithful port with:
- 129 `code`-cited rules;
- differential tests against compiled original C;
- a data-lineage study;
- process-isolated players;
- honest budget accounting;
- an independent review record for every milestone.

That is far beyond what the brief asks for the game. Since 2026-10-13, though, almost all the
effort went into things that earn **zero rubric credit**:
- the Remastered campaign (training level, Level 2, power-ups);
- Horde 2 (three arenas, boss, cards, high scores), sealed arenas, fullscreen, UI in the
  original art, and a hidden developer mode;
- the Codex bridge;
- a second game, Neon Protocol v1 and v2, with six open PRs.

The brief says it plainly: *"more scope earns no bonus."*

Meanwhile, as of today, none of these exist:
- a single live model call (the Session 7 checkpoint required one live episode with a trace);
- an `EVALUATION.md`, or a comparison table that includes a model player;
- a playtest, or a recording;
- an agent-team log in your voice (the current one is agent-written, with `TODO (student)`
  markers, and is about 180 lines long);
- a `midterms/adit-prabhu/` folder in the course repo, or the required workflow file;
- evidence that **Level 1, the one level in scope, can be finished from the start** (see §4.1).

### Estimated score if you submitted today (my reading of the rubric, not a grade)

| Category | Today | Why | Realistic after this plan |
|---|---|---|---|
| 1. Research & depth | 3 | Labels and locators strong; `SCOPE.md` contradicts the build (1b); non-rubric label names (1a) | 4 |
| 2. Game design & AI | 2 | 2b missing (the model has never submitted a live action); 2a unproven for Level 1 | 4 |
| 3. Engineering | 1–2 | 3a and 3c missing: nothing runs from `midterms/adit-prabhu/`, and no `midterm-adit-prabhu.yml` | 4 |
| 4. Creativity | 2 | Baseline wins 0/20 and is stuck on the full level; no "alternative it beat" table | 3–4 |
| 5. Reflection | 1 | 5a, 5b and 5c all missing: no live table, an agent-voiced log, no peer notes, no recording | 4 |
| **Total** | **≈ 9–10 / 20** | | **≈ 18–20 / 20** |

Every gap above is closable in 12 days, **if you stop building features today.**

---

## 2. Scope: too big where it doesn't count, too thin where it does

### 2.1 The game is too big. Freeze it now.

Classic Level 1 alone is a complete, bounded, defensible midterm. It has:
- a full core loop;
- every object type in the original file;
- a clear win (exit plus down) and clear losses (death, tick limit).

Each extra feature costs you in three places:
- it needs its own rule-map labels (1a);
- it must agree with the scope statement (1b), and today it doesn't;
- it is one more thing a TA can crash or get lost in (2a).

The default `uv run abuse-remake` on `feat/rm-polish` now opens a title menu whose campaign
**starts with the Training level**. So the first thing a TA sees is content your `SCOPE.md`
lists as *out of scope*.

**Recommendation:**

| Item | Decision I recommend | Why |
|---|---|---|
| Classic Level 1 | **The graded game.** The README's TA path is `--mode classic`. | This is the scope you declared and evaluate on |
| Remastered (#7, already merged) | Keep, as an "optional layer, not evaluated" | Already reviewed, tested and labelled |
| Remastered expansion (#15–#20) | Merge if you want it, **then freeze**. Update `SCOPE.md` to say what is in and that none of it is graded or evaluated. If you won't confirm it in writing, leave it out of the course folder | Built and reviewed, but every line of it is surface area |
| Codex bridge (`feat/codex-bridge`) | **Leave it out of the course submission**, or keep it with one line: "not used for any reported result" | A session with repo access choosing moves looks like a 2b violation to a skimming grader. Your own doc admits the boundary can't be enforced there |
| Neon Protocol (#9–#14) | **Out.** Close or park the PRs. Don't mention it in the submission | A second game. It doubles what a grader has to understand and adds CC-BY asset obligations |
| New features of any kind | **None until 2026-11-08** | Every hour goes to the experiment and the human evidence |

### 2.2 The experiment's plan is too big, it hasn't been run, and the task may be too hard

**The declared live suite is oversized.** `eval/configs/live.toml` covers 4 scenarios × 5 seeds
× 3 memory conditions = 60 model episodes. `abuse-eval estimate` puts that at:
- up to **12,000 requests**;
- about **21.6M input tokens**;
- up to 4M output tokens.

At flash-lite prices the money is small. The problems are the hours of wall time, the
rate-limit and failure surface, and the fact that it is three times the brief's minimum on every
axis. You have not run even the 20-request smoke test.

**Floor effect.** In the offline run (`evidence/reports/offline-baselines.md`):
- random wins **0/20** and scripted wins **0/20**;
- on the full level, scripted ends every seed at the same spot, (248, 321), after 600 decisions;
- 480 of those 600 decisions are `explore left` / `explore right`. It ping-pongs, which means it
  is not really playing that section.

If the model also wins 0/N, your headline is "nobody can finish", and the whole comparison rests
on an evaluator-invented progress metric. That is defensible, but weak for 4b ("the baseline is
a real competitor… the experiment can distinguish the two players").

**Budget mismatch.** The offline baseline numbers use 600 decisions; the live config uses 200
for every player. The published baseline table is not the one you will compare against. Re-run
it at 200 (it's free).

**The automated solver is missing.** The brief says *"Single-player games use an automated
solver."* You have one: `scripts/route_search.py`, a privileged engine search. It has never been
run on Level 1, and `tests/test_campaign_routes.py` explicitly skips `level01`.

### 2.3 The suite I recommend (declare it before any tuning)

You have not tuned anything yet: no live calls means no prompt tuning. So you can still honestly
**re-declare** a smaller suite today. Commit it with the date and the reason, before the first
live call.

| | Content |
|---|---|
| **Tuning set (never reported as results)** | `level01-cp2`, seeds 90–99. All prompt iteration and any baseline fixes happen only here. Log every prompt version |
| **Reported situations** | `level01-cp1`, `level01-cp2`, `level01-cp3`, `level01` (full level) |
| **Held out** | `level01-cp1`, `level01-cp3` and `level01` are never seen during tuning. `level01-cp2` is evaluated only on seeds the tuning never used |
| **Trials** | seeds 0, 1, 2 per situation (the brief asks for at least 2) |
| **Players** | random; scripted (A* + rules); **model M1** (bounded history, the primary player); **model M0** (observation only, the brief's required ablation for partial observation); the **solver** (privileged, an upper reference, not a competitor) |
| **Budgets (all players)** | 200 decisions, the scenario tick limit, 15 ticks per action, 600k / 150k tokens, 20 s per request, 3600 s per episode |
| **Dropped** | M2, unless time remains *after* the main run. If you run it, declare it as a separate, labelled study |
| **Size** | 4 × 3 × 2 = 24 model episodes, ≤ 4,800 requests. About 30–60 min with `--jobs 6` if Vertex quotas allow |

Write this into a new `eval/configs/midterm.toml` and a short `SUITE.md` that names:
- the date;
- the reason for shrinking from `live.toml`;
- the tuning/held-out split;
- the metrics: win, progress, deaths, invalid rate, failed requests, decisions, ticks, tokens,
  latency p50/p95, and dated cost;
- the rule that **no change to the suite or prompt happens after the first reported run**.

---

## 3. Rubric audit, check by check

Status: ✅ met · 🟡 weak · ❌ missing.

### 1. Research & critical depth

| Check | Status | Evidence | Gap → fix |
|---|---|---|---|
| 1a labels | 🟡 | `docs/rule-source-map.md`: 129 `code`, 2 `manual`, 6 `observed`, 5 `assumed`, plus 25 `course choice`, 2 `course rule`, 8 `remastered design` | The rubric's vocabulary is `code / manual / observed / assumed / design`. Relabel `course choice`, `course rule` and `remastered design` as **`design`** (keep the subtype in words), each pointing to its spec (`SCOPE.md`, `docs/action-interface.md`, `docs/remastered.md`) with a one-line rationale. Row 71 ("check:") has no label; mark it as a property of our code, `design` |
| 1b scope | 🟡→❌ risk | `SCOPE.md` has `TODO (human)`. Its "Out of scope" lists other levels and extra powers, which the Remastered build contains. The scope paragraph is "drafted by the implementation agent" | Rewrite `SCOPE.md` yourself: in-scope = Classic Level 1; optional = Remastered (list it); excluded = Neon, the bridge, network play, editor, music. Confirm it against your **Week 3 thread** and post the change there |
| 1c sources | ✅ (one stale line) | `data/original/PROVENANCE.md` quotes the release note; retail data and WAVs are excluded | It says the game "uses CC0 replacement audio from `assets/`". There is no `assets/` folder; audio is synthesised in `game/audio.py`. Fix the line. `human-responsibility.md` says "for personal and course use only", but the course repo is **public**. State that the shareware permission ("use pieces of the source code or shareware data … however you see fit") covers publication, or ask the instructor |

### 2. Game design & AI integration

| Check | Status | Evidence | Gap → fix |
|---|---|---|---|
| 2a core loop | 🟡 unproven | The exit rule is tested by teleporting the player to it (`test_exit_needs_touch_and_action_key`). There is no route from START, no human finish, and `test_campaign_routes.py` skips `level01` | **Prove Level 1 can be finished** (§4.1): a saved route replayed in CI, and finishing it yourself once in Classic. Make the README's TA path `uv run abuse-remake --mode classic` |
| 2b model player | ❌ | Code exists (`model_player.py`, 3 providers, M0–M2); **0 live calls ever** | Live smoke today or tomorrow, then the declared suite. Fallbacks are already labelled, and refusals are never substituted. Keep it that way |
| 2c information | ✅, with one argument to write down | `docs/information-boundary.md`, process isolation, seed withheld, leakage tests | **Hidden walls.** The original calls these `HIDDEN_WALL*` (`doors.lsp:184-197`); Level 1 has 102 of them. We report each as `wall_block`, offer `attack W4`, and the prompt says "a breakable wall; shoot it". I rendered the first column (x=210) in Classic: it is drawn as cracked stone, visibly unlike the smooth pillar next to it, so reporting it is defensible. But a grader reading "HIDDEN" next to "we tell the agent" will ask. Add one paragraph and a screenshot to `information-boundary.md` explaining why it is on-screen information, and put this in your hidden-information explanation for 2c |

### 3. Production / engineering quality

| Check | Status | Evidence | Gap → fix |
|---|---|---|---|
| 3a runs from a fresh clone | ❌ | Works in your private repo; nothing is in `game-dev-f26/midterms/adit-prabhu/` | Copy into the course repo early (§5); do a fresh-clone test **from that folder**, on a second machine or a clean directory |
| 3b limits | 🟡 | Ticks, decisions, tokens, wall clock and per-request timeout, with explicit terminal reasons (`docs/budgets.md`) | **A confirmed bug**, noted in `PROGRESS.md` and still unfixed. `step()` increments `decisions` (`agent/interface.py:168`) before `_execute`, whose loop checks `_status()`. That returns "budget" once `decisions >= max_decisions`, so **the last allowed action is accepted with 0 ticks**. Fix it test-first |
| 3c CI | ❌ in the course repo | `.github/workflows/ci.yml` is green in the private repo | Write **`.github/workflows/midterm-adit-prabhu.yml`** (sketch in §6). Make sure the five check kinds are *named* in `EVALUATION.md`: rule invariants, legal/illegal actions, a **terminal outcome** (the Level 1 route win), a **genuine observed regression** (the decision-cap bug, or "baseline stopped fighting after six shots"), and episode limits |
| 3d agent team | 🟡 | `CLAUDE.md`/`AGENTS.md`, 2 skills, `rules-reviewer.md`, 14 review records | The repo is **private**, so PR links don't resolve for graders. Either make it public (scan for secrets first) or commit 1–2 exported, sanitised session transcripts and link those. The release and live-eval workflows **cannot** go in the course PR (only one workflow file is allowed, and live-eval uses WIF credentials) |

### 4. Creativity & innovation

| Check | Status | Evidence | Gap → fix |
|---|---|---|---|
| 4a choices with alternatives | 🟡 | The choices are documented across many docs | Add one table to the README: *choice → alternative it beat → why*. Rows: macro actions vs per-tick inputs; the 15-tick action cap; death = loss vs the original respawn; checkpoint segments vs full-level only; M0/M1 vs persistent memory; A* scripted vs random baseline; progress metric vs win-only; Gemini flash-lite vs a bigger model; reconstruction vs original game |
| 4b real baseline, separable experiment | 🟡→❌ risk | Scripted beats random on cp2 and cp3, but is tied on `level01` and stuck on cp1; 0 wins anywhere | Fix the explore ping-pong on the **tuning set only** (cap: one day), re-run at 200 decisions, and add the solver as a reference. Interpret the result whichever way it falls |

### 5. Critical reflection

| Check | Status | Evidence | Gap → fix |
|---|---|---|---|
| 5a fair comparison | ❌ | Offline table only; the suite was declared on 2026-10-13 (good, and dated in git: `1d11bb1`); `[prices]` is empty; no held-out set is named | §2.3 suite. Fill `[prices]` with the **date and URL** of the Vertex price page. Report every episode, including failures |
| 5b authorship | ❌ | `docs/agent-team-log.md` is agent-voiced ("Drafted by the implementation agent… TODO (student)") and about three pages | Write `AGENT-TEAM.md` yourself, **one page, first person** (outline in §7). Use the peer notes in the limitations |
| 5c recording | ❌ | `docs/demo.md` scripts about 6 minutes (**over** the 3–5 limit); the only video is a 6.8 MB scripted-baseline replay with no narration | 3–5 minutes, showing the **model** choosing actions, with limits stated (§8) |

---

## 4. Bugs and risks found in this audit

### 4.1 Level 1 has no proof it can be finished (highest priority)

Only levels 0 and 2 have saved routes (`evidence/routes/`). Level 1, your scope, has none, and
the route test excludes it. No player (random, scripted, or a human on record) has ever
finished it.

I ran the solver on Level 1 for up to 9 minutes:

```
uv run python scripts/route_search.py --level level01 --goal level02 --budget 40000 --out <scratch>
```

**Result: no route.** The search was stopped at the 9-minute cap after expanding about 3,200
nodes. Its furthest point was around x≈1,200; the exit is at (2715, 306). It spent the second
half of its time circling x≈800–1,200, y≈366–503. Unguided search could not finish Level 2
either (`docs/agent-team-log.md`), so this is the same pattern: Level 1 probably needs a
segmented route. It is not evidence that Level 1 is unwinnable. But right now **nobody and
nothing has finished the level you are graded on**, and that has to change before you rely on
"a TA can play start to ending".

Note the solver got about 5× further right than the scripted baseline, which stalls at x=248.
That gap is itself worth a sentence in `EVALUATION.md`.

What to do:
1. Get a Level 1 route. Use segments if needed (`--to`, `--via`, `--prefix`, the method that
   worked for Level 2). Save it as `evidence/routes/level01.json` and remove the `level01`
   exclusion from `test_campaign_routes.py` so CI replays it. That is your rubric "terminal
   outcome" check, and your proof for 2a.
2. Run the solver from each checkpoint (cp1, cp2, cp3) as well. It becomes the "automated
   solver" row of the comparison, and proves every reported situation is winnable.
3. Play Level 1 to the exit yourself in Classic, with `--playtest` so a trace is recorded. If
   *you* can't finish it, say so and why; that is a fidelity finding, not a failure.

### 4.2 Other defects and inconsistencies

| # | Where | Problem | Fix |
|---|---|---|---|
| 1 | `agent/interface.py:164-180`, `:196` | The last decision under the cap is accepted with **0 ticks** (confirmed by reading the code; documented in `PROGRESS.md`, never fixed) | Test first (`test_last_decision_under_the_cap_still_runs`), then check the cap before incrementing, or exempt the current decision inside `_execute`. Re-run the offline baselines afterwards |
| 2 | `data/original/PROVENANCE.md` | Claims CC0 audio from `assets/`; there is no such folder, and the audio is procedural | One-line fix |
| 3 | `SCOPE.md` | `TODO (human)`; contradicts the build | Rewrite it yourself (§3, 1b) |
| 4 | `docs/human-responsibility.md` | `TODO (student)`; mentions the v1.0.0 tag, release, Asana (the midterm needs none of these); "personal use only" vs a public repo | Edit it and sign it, or fold it into `AGENT-TEAM.md` |
| 5 | `README.md` checklist | Points to the tag, `release.yml`, `live-eval.yml`, "Asana links" | Rewrite it for the course folder (§5) |
| 6 | `docs/demo.md` | About 6 minutes, over the limit | Cut to 4:30 (§8) |
| 7 | `docs/playtests/protocol.md` | Built for 25 minutes; the peer session is **15** | Make a 15-minute version: 2 warm-up, 8 Classic from START, 3 watching the agent replay, 2 questions |
| 8 | `evidence/video/*.mp4` (6.8 MB) | "Keep large generated files out of the submission" | Don't copy it; link the recording instead |
| 9 | `test.py` (untracked) | Unrelated scheduler code | Keep it out of every commit and the course folder |
| 10 | Run records | `config.json` records the **private repo's** SHA | Run the final evaluation from the course-repo folder at the commit you submit, or record both SHAs plus a tree hash in `EVALUATION.md` |
| 11 | Branches | `feat/rm-polish` (#20) and `feat/codex-bridge` diverge from #19 | Decide what goes in (§2.1), merge in order, then freeze `main` |
| 12 | `AGENTS.md` | Forbids "Generated with" footers in PRs | Write the course PR description yourself, with no AI footer; disclosure goes in `AGENT-TEAM.md` |
| 13 | `game/hud.py` (Classic too) | The health and weapon HUD is drawn **over** the bottom ~20% of the 316×162 play view (I rendered it at scale 3; the panels cover y≈380–470 of 486). The original drew its status bar *below* the view. So a human in Classic sees less than the agent, whose observation is the full view | Either draw Classic's HUD below the view, or state the asymmetry in `EVALUATION.md` wherever human playtest results sit next to agent results |

---

## 5. What goes in `game-dev-f26/midterms/adit-prabhu/`

No `midterms/` folder exists on `origin/main` yet, so there is no staff template. Follow the
brief literally:

```
midterms/adit-prabhu/
  README.md          scope statement, rule-map summary + link, reuse terms, setup/play/test/eval
                     commands (each "run from midterms/adit-prabhu/"), recording link,
                     design-choices table (4a)
  EVALUATION.md      suite (dated, pre-tuning), comparison table, held-out cases, traces,
                     CI run link for the submitted commit, limitations paragraph
  AGENT-TEAM.md      one page, your voice
  SCOPE.md           (or merged into README)
  peer-notes/        given.md, received.md (anonymous; private feedback stays on CourseWorks)
  pyproject.toml  uv.lock  .python-version
  src/  tests/  data/original/  eval/configs/  docs/  evidence/ (traces, reports; no mp4)
  scripts/  .claude/ (agents, skills)  AGENTS.md  CLAUDE.md  agent-config.json
.github/workflows/midterm-adit-prabhu.yml   ← the only file outside the folder
```

Leave out: `release.yml`, `live-eval.yml`, `packaging/` (optional), `runs/`, `cache/`,
`.venv/`, `test.py`, the Neon code, the mp4, and anything personal.

Check before pushing:
- `paths.repo_root()` resolves to the folder (it uses `parents[2]` of the package, so it
  should work), and the C-reference tests compile from the subfolder.
- `grep -ri` the folder for keys, emails, local paths (`/Users/enigma`) and project IDs.
- The data is 8.6 MB. That's fine, but say in the README why it is vendored (checksummed
  original data, needed for the port).

---

## 6. The CI workflow (sketch)

```yaml
# .github/workflows/midterm-adit-prabhu.yml
name: midterm-adit-prabhu
on:
  pull_request:
    paths: ['midterms/adit-prabhu/**', '.github/workflows/midterm-adit-prabhu.yml']
permissions:
  contents: read
jobs:
  deterministic:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    defaults:
      run:
        working-directory: midterms/adit-prabhu
    env:
      SDL_VIDEODRIVER: dummy
      SDL_AUDIODRIVER: dummy
      ABUSE_REQUIRE_C_REFERENCE: '1'
    steps:
      - uses: actions/checkout@v4
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v6
        with: { python-version: '3.12' }
      - run: uv sync --frozen --all-extras
      - run: uv run --frozen ruff check src tests scripts
      - run: uv run --frozen abuse-data verify
      - run: uv run --frozen pytest -v
      - run: uv run --frozen abuse-eval run --config eval/configs/ci-smoke.toml   # offline, no keys
```

It uses no secrets, touches no other folder, and has no `push:` trigger on other paths. Open
the course PR as a **draft early** (by 10-28) so you see CI green or red there, not on 11-07.

---

## 7. `AGENT-TEAM.md`: what it must say, in your words

One page. First person. The rubric treats an agent-voiced log as missing. Cover:
- **Agents and permissions**: implementation (Claude Code, later Codex), the reviewer (read-only
  `rules-reviewer`), the skills (`port-classic-rule`, `agent-eval`), the players (no repo access).
- **Decisions you made**, with dates:
  - Level 1 only;
  - Classic plus Remastered;
  - Vertex/Gemini;
  - stopping the agent's first attempt in the course repo;
  - expanding Remastered **against the agent's advice** on 2026-10-14;
  - dropping Neon;
  - shrinking the suite on 2026-10-26.
- **What reviewers found and what you decided**: the PR #1 provenance overclaim, the PR #6
  billing bug (several billed requests per decision), the PR #4 restart crash, the R4
  permanent-invulnerability bug.
- **What went wrong and what you'd change**, in your own words. The honest answer, which a
  grader will respect: the feature work crowded out the evaluation until two weeks before the
  deadline.
- **Where the evidence lives**: links.

Keep the long Codex session notes in `docs/`, and link them. Don't paste them in.

---

## 8. The recording (4:30 target, hard stop at 5:00)

| Time | Show | Say |
|---|---|---|
| 0:00 | Classic Level 1, you playing 30 s | What Abuse is, the bounded scope, Classic vs Remastered |
| 0:40 | The rule map, one row (the laser fire rate) | How fidelity is evidenced |
| 1:10 | `abuse-replay --trace <live M1 trace>`, with the side panel | **The model choosing actions**: the observation it gets, the legal list, one refused action and its feedback |
| 2:40 | The scripted baseline on the same situation, briefly | What the baseline is |
| 3:10 | The `EVALUATION.md` table | Results with counts and intervals; held-out cases; cost and latency |
| 4:00 | Limitations | Small sample; progress is an evaluator measure; where all players fail; what the peers said |

The agent must visibly play with **no manual move selection**. A replay of a recorded live
trace qualifies, but say on screen that it is a replay of trace X.

---

## 9. Day-by-day plan

| Date | Do | Done when |
|---|---|---|
| **Mon 10-26** (today) | Stop feature work. Make the §2.1 decisions. Book the peer playtest slot now. Set up Vertex (`gcloud auth application-default login`, `GOOGLE_CLOUD_PROJECT`, `COURSE_MODEL=gemini-3.5-flash-lite`, or whichever ID your project lists). Write and commit `SUITE.md` and `eval/configs/midterm.toml` (dated) | Suite committed before any live call |
| Tue 10-27 | Fill `[prices]` (date + URL). `abuse-eval estimate` → approve → **`live-smoke`** (≈ 20 requests). Commit the trace. This closes the Session 7 checkpoint item, a day late. Fix the decision-cap bug test-first | One live trace in `evidence/traces/live-smoke/` |
| Wed 10-28 | Level 1 route (§4.1) and the solver from cp1–3. Create the course branch `adit-prabhu/midterm`, copy the folder, add the workflow, open a **draft** PR | CI green in the course repo |
| Thu 10-29 | Prompt tuning on the **tuning set only**; log each version (hash + what changed + tuning-set result). Optional: one day on the baseline's ping-pong, tuning set only | Prompt and baseline frozen; SHA recorded in `SUITE.md` |
| Fri 10-30 | Rewrite `SCOPE.md`, relabel the rule map to `design`, fix PROVENANCE, add the 4a choices table, handle the hidden-wall check | Docs consistent with the build |
| Sat 10-31 – Sun 11-01 | **The reported run**, from the course folder: offline baselines at 200 decisions, M1, M0, the solver. Write `EVALUATION.md` with every episode, including failures | Table complete; traces committed (a few representative ones, the rest summarised or linked) |
| Mon 11-02 – Wed 11-04 | Peer playtest (15 min, both directions). Your own 2–3 informal playtests with the 15-minute protocol. Record the video | Notes written; video uploaded (unlisted), link works logged out |
| Thu 11-05 | `AGENT-TEAM.md` in your voice; limitations paragraph citing the peer notes; final README | Every `TODO` gone (`grep -rn TODO`) |
| Fri 11-06 | Send notes to your partner. **Fresh-clone test** of the course branch in a new directory: every README command, from `midterms/adit-prabhu/` | Everything runs; CI green |
| **Sat 11-07** | Final push **by noon**, not 11:59 p.m. PR description: login, title, links to README, EVALUATION, AGENT-TEAM, peer notes, recording. Submit the PR URL on CourseWorks | Done |

If something slips, cut in this order:
1. M2;
2. the baseline improvement;
3. the solver from cp1–3 (keep the Level 1 route);
4. seeds from 3 down to 2.

**Never cut:** the live M1 run, M0, held-out cases, the recording, the peer notes, or the
first-person log.

---

## 10. Decisions only you can make (needed today)

1. **What ships**: Classic L1, plus Remastered #7, plus (#15–#20 or not)? The bridge in or out?
   Neon out? (My recommendation is in §2.1.)
2. **Merge order** for #15–#20, and whether `feat/codex-bridge` is merged or abandoned.
3. **The model**: the exact Vertex model ID, and a hard spending cap you approve.
4. **The suite** in §2.3, or your own. It must be committed before the first live call.
5. **Repo visibility**: make `Adit-Prabhu/abuse_remake` public so PR and review links work for
   graders, or rely on committed records and transcripts.
6. **Week 3 thread**: post the scope update (Classic Level 1 graded; Remastered optional;
   suite re-declared on 10-26).

---

## 11. Things not to do

- Don't add features, art, levels, Horde content or Neon work before 11-08.
- Don't tune the prompt on cp1, cp3, `level01`, or seeds 0–2 of anything.
- Don't re-run a reported episode because it went badly. Every planned episode is reported.
- Don't use bridge or Codex-chosen moves as model-player evidence.
- Don't let an agent write `AGENT-TEAM.md`, the limitations, the peer notes, or the narration.
- Don't push after the deadline, and never force-push the PR branch.

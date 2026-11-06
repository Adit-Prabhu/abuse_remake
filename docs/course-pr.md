# The course PR: steps and description

The student opens one PR to `columbia-university-ai-games/game-dev-f26`, targeting `main`, by
2026-11-07 at 11:59 p.m., and submits its URL on CourseWorks. Agents never push to the course
repository or open the PR.

## Steps

From the project repository, with everything committed:

```sh
git -C ~/PycharmProjects/game-dev-f26 checkout main
git -C ~/PycharmProjects/game-dev-f26 pull
git -C ~/PycharmProjects/game-dev-f26 checkout -b adit-prabhu/midterm
uv run python scripts/export_submission.py ~/PycharmProjects/game-dev-f26
```

Then, in `~/PycharmProjects/game-dev-f26`: check that `git status` shows only
`midterms/adit-prabhu/` and `.github/workflows/midterm-adit-prabhu.yml`, commit, push the
branch to `origin`, and open the PR with the description below. Wait for the
`midterm-adit-prabhu` check to pass. Never force-push after the deadline.

## Description (paste, then edit in your own words)

```markdown
**GitHub login:** Adit-Prabhu (folder `midterms/adit-prabhu/`)
**Project:** Abuse, Level 1: a faithful reconstruction with a model-driven player

- README (setup, play, test and evaluation commands; scope; rule/source map; sources and terms): [midterms/adit-prabhu/README.md](https://github.com/columbia-university-ai-games/game-dev-f26/blob/adit-prabhu/midterm/midterms/adit-prabhu/README.md)
- Evaluation report: [midterms/adit-prabhu/EVALUATION.md](https://github.com/columbia-university-ai-games/game-dev-f26/blob/adit-prabhu/midterm/midterms/adit-prabhu/EVALUATION.md)
- Agent team log: [midterms/adit-prabhu/AGENT-TEAM.md](https://github.com/columbia-university-ai-games/game-dev-f26/blob/adit-prabhu/midterm/midterms/adit-prabhu/AGENT-TEAM.md)
- Human playtest notes: [midterms/adit-prabhu/docs/playtests/received/](https://github.com/columbia-university-ai-games/game-dev-f26/tree/adit-prabhu/midterm/midterms/adit-prabhu/docs/playtests/received)
- Recording (3–5 min): <recording URL>

Classic mode, Level 1 of Abuse (1996), on the original level file and rules. A model player
(`gemini-3.5-flash-lite` on Vertex AI) plays it through a five-operation interface and is
compared with a scripted baseline on a suite declared before tuning: 4 situations x 3 seeds,
48 episodes, run once live from the frozen commit. No player won; the scripted baseline led
both model players. The CI for this folder is `.github/workflows/midterm-adit-prabhu.yml`.

The project was built in its own repository, [Adit-Prabhu/abuse_remake](https://github.com/Adit-Prabhu/abuse_remake),
through reviewed, stacked PRs. This folder is an export of one commit of it
(`EXPORTED_FROM.json`). PR #58 was an early draft of this submission, closed on 2026-10-27.
```

## Before submitting

- The recording link opens for someone outside your account (try a private window).
- The links above open on the PR branch, and the playtest folder holds your notes.
- `grep -rn -i "to come\|TODO\|link added when" midterms/adit-prabhu/*.md` finds nothing.
- No project ID, email address, key or playtester detail is in the folder.
- A fresh clone of the PR branch runs the README's commands from `midterms/adit-prabhu/`.

# Agent team log

## Who was on the team

For this project, I mainly used Claude Code as the implementation agent, with Codex helping on October 15–16. They handled most of the coding, tests, and documentation. I also used a separate read-only reviewer that checked changes without being involved in writing them. There were two reusable skills, `port-classic-rule` for porting mechanics from the original game and `agent-eval` for setting up evaluations. Finally, I had the actual playing agents: random, scripted, and the Gemini model player. Unlike the implementation agents, these could only interact with the game through observations and legal actions, without access to the source code or internal game state.

## How I managed the work

I made the decisions about scope, priorities, and what was accepted. My rule was that the implementation agent had to give me a plan before making major changes. It could create branches, write code, run tests, and open PRs, but it couldn't merge, approve its own work, or create release tags. I used stacked PRs so changes could be reviewed separately before I merged them. For the live evaluation, I set a $10 spending cap and approved each run before it happened.

## What the reviews caught

The independent reviews ended up being more useful than I initially expected. In PR #25, the reviewer found that the agent observations revealed hidden walls that players shouldn't have known about. This mattered because it gave agents information they weren't supposed to have. The review of PRs #32–#34 caught another major issue: the scripted baseline knew hanging aliens couldn't be damaged, but the model prompt never explained that. This helped explain why the models kept shooting the same enemies without making progress. Another review, of PR #6, found that the Vertex SDK could make multiple billed requests for a single decision, which was important for keeping the evaluation fair and within budget.

## Decisions I made

One decision I made against the agent's advice, on October 14, was expanding Remastered mode before finishing the required evaluation work. I wanted the game to feel more complete, so I prioritized additional levels and features. Looking back, I think it was worth it for the game itself, but not necessarily for the assignment. It pushed the live comparison to about two weeks before the deadline and left less time for testing. On October 26, I asked for a more critical audit against the rubric, which helped me refocus on what was actually required.

## Where things went wrong

Early on, on October 13, I had to stop the agent because it started checking credentials and working in the wrong repository. After that, I made the boundaries clearer. There was another smaller incident on November 6 when it ran a read-only command against the course repository after I had told it to work only in the project repository. Nothing was changed, but it showed that instructions still needed to be enforced and checked.

## What I learned and AI use

If I did this again, I would finish the required evaluation and evidence earlier, then spend time on extra features. I would also check more of the game myself instead of relying mainly on automated tests and screenshots. The agents wrote most of the code, tests, and technical documentation, while I chose the scope, approved plans and spending, reviewed the results, and made the final decisions. I wrote the playtest observations, evaluation limitations, and this log myself. The biggest thing I learned was that having agents produce working code isn't enough. I still had to check whether the results were correct, whether the comparisons were fair, and whether the implementation actually matched what I wanted.

Sources: [`docs/agent-team-facts.md`](docs/agent-team-facts.md) (every fact above, with links), [`docs/agent-team-log.md`](docs/agent-team-log.md), and the review records in [`docs/reviews/`](docs/reviews/).

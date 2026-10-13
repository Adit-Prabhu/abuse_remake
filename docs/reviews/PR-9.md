# Review record: PR #9 (Neon Protocol simulation)

- Reviewer: fresh independent read-only Codex agent, `neon_engine_review`, briefed with
  `.claude/agents/rules-reviewer.md`; no edits, network or paid model calls.
- Input: `main..feat/neon-engine` at bbd8e3b, engine/tests/design docs and Classic boundary.
- New rules are labelled `neon design`; no original-game fidelity claim.
- Student owns acceptance and merge. This record reports findings and implementer fixes.

| Severity | Finding | Resolution |
|---|---|---|
| blocking | Jump could not reach lowest platform | Failing reachable-platform test; jump increased to −22 for 110 px rise |
| blocking | Same-tick pickup or relay revived lethally hit player | Failing lethal-shot + pickup + action test; death now stops before pickups/interactions |
| should fix | High Horde waves spawned outside bounds and could not clear | Failing wave-40 boundary test; spawns repeat within seven bounded edge slots |
| should fix | Dash protected five stepped ticks instead of six | Failing exact six-tick combat test; iframes now decay after combat |
| should fix | Hazards hurt airborne players near floor | Failing airborne-hazard test; hazards now require grounded state |

Reviewer confirmed deterministic snapshot continuation and no Neon imports into the Classic
playing-agent interface. The original 18 contracts passed before review; five regression
contracts above failed before their fixes. Full checks are repeated after fixes.

Independent follow-up: "No unresolved findings. All five reported defects are addressed,
and all 23 Neon engine contracts pass." Full validation: 222 tests, Ruff and data checksums pass.

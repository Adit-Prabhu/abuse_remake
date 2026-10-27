"""The configuration record (agent-config.json) must describe the code as it is."""

import json
import re
import subprocess
import tomllib
from pathlib import Path

from abuse_remake.agent.interface import Budgets
from abuse_remake.agent.memory import HISTORY_TURNS, NOTES_MAX
from abuse_remake.agent.players.model_player import parser
from abuse_remake.agent.providers import PROVIDERS
from abuse_remake.scope import FULL_LEVEL_TICK_LIMIT, SEGMENT_TICK_LIMIT

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "agent-config.json").read_text())


def test_schema_and_required_fields():
    assert CFG["schema_version"] == "course-1"
    for key in ("purpose", "tools_available", "prohibited_actions", "memory_policy", "context_sources",
                "model_choice", "prompts_or_system_instructions", "named_failure_modes", "evaluation_cases",
                "logging_policy", "human_override_points", "test_command", "ci_workflow_path", "native_artifact",
                "limits", "fallback", "limitations", "agent_team", "playing_agent_interface"):
        assert key in CFG, key


def test_limits_match_the_code_and_the_declared_suite():
    lim = CFG["limits"]
    defaults = parser().parse_args([])
    live = tomllib.loads((ROOT / "eval/configs/midterm.toml").read_text())
    assert lim["request_timeout_seconds"] == defaults.timeout
    assert lim["request_attempts"] == 1
    assert lim["max_decisions_per_episode"] == Budgets().max_decisions
    assert lim["max_action_ticks"] == Budgets().max_action_ticks
    assert lim["max_ticks_full_level"] == FULL_LEVEL_TICK_LIMIT and lim["max_ticks_segment"] == SEGMENT_TICK_LIMIT
    assert lim["history_turns"] == HISTORY_TURNS and lim["notes_characters"] == NOTES_MAX
    assert lim["max_decisions_per_episode_live_comparison"] == live["budgets"]["max_decisions"]
    assert lim["max_decisions_full_level_live_comparison"] == live["budgets"]["scenarios"]["level01"]["max_decisions"]
    assert lim["max_input_tokens_per_episode"] == live["budgets"]["max_input_tokens"]
    assert lim["max_output_tokens_per_episode"] == live["budgets"]["max_output_tokens"]
    assert lim["max_input_tokens_per_run"] == live["run"]["max_input_tokens"]
    assert lim["max_output_tokens_per_run"] == live["run"]["max_output_tokens"]
    assert lim["decision_timeout_seconds"] == live["decision_timeout"]
    for p in live["players"]:
        if p.get("live"):
            args = p["args"]
            assert int(args[args.index("--max-output-tokens") + 1]) == lim["max_output_tokens_per_request"]
    assert CFG["model_choice"]["live_providers"] == list(PROVIDERS)


def _repository_root() -> Path:
    """The workflow lives at the repository's root: this folder in the project repository, two
    levels up in the course repository (midterms/<login>/)."""
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             cwd=ROOT, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        top = ""
    return Path(top) if top else ROOT


def test_every_named_file_exists():
    text = json.dumps(CFG)
    paths = set(re.findall(r"((?:src|tests|eval|docs|\.claude|\.github)/[\w./-]+\.(?:py|md|toml|yml))", text))
    paths |= {"AGENTS.md", "CLAUDE.md", "SCOPE.md", "SUITE.md"}
    missing = [p for p in sorted(paths)
               if not ((_repository_root() if p.startswith(".github/") else ROOT) / p).exists()]
    assert not missing and len(paths) > 10, missing


def test_skills_and_reviewer_have_front_matter():
    for path in (".claude/skills/port-classic-rule/SKILL.md", ".claude/skills/agent-eval/SKILL.md",
                 ".claude/agents/rules-reviewer.md"):
        head = (ROOT / path).read_text().split("---")
        assert head[0] == "" and "name:" in head[1] and "description:" in head[1], path

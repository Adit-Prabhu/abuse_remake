"""The committed evidence still matches the game: every trace under evidence/traces replays
through the current engine. An agent episode replays through the interface with every
observation hash and the outcome matching; a human playtest trace (consented, committed under
evidence/traces/human/) replays with every recorded state check matching. A rule or interface
change that alters a recorded episode fails here, so the evidence is regenerated (and the change
noted) instead of silently going stale."""

import json
from pathlib import Path

import pytest

from abuse_remake.paths import repo_root

TRACES = sorted((Path(repo_root()) / "evidence" / "traces").rglob("*.jsonl"))


def test_there_is_committed_evidence():
    assert TRACES


@pytest.mark.parametrize("path", TRACES, ids=[str(p.relative_to(Path(repo_root()) / "evidence" / "traces"))
                                              for p in TRACES])
def test_a_committed_trace_replays_exactly(path, tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    header = json.loads(path.read_text().split("\n", 1)[0])
    if header.get("format") == "human-trace-1":
        from abuse_remake.game.human_replay import replay_human

        out = replay_human(path)
        assert out["mismatches"] == 0 and out["checks"] > 0
        return
    from abuse_remake.game.spectate import main

    assert main(["--trace", str(path), "--headless", "--scale", "1"]) == 0


def test_a_human_playtest_trace_is_replayed_by_the_human_replayer(tmp_path, monkeypatch):
    """The playtest protocol commits consented human traces under evidence/traces/human/; the
    test above must replay them with their own replayer (they have no agent scenario)."""
    from abuse_remake.game.app import App, parse_args

    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    rec = tmp_path / "human" / "P1.jsonl"
    app = App(parse_args(["--frames", "1", "--no-audio", "--seed", "1", "--scale", "1", "--mode", "classic",
                          "--record", str(rec)]))
    app.state = "play"
    for i in range(20):
        app.tick(i)
    app._check("session end")
    app.trace.close()
    test_a_committed_trace_replays_exactly(rec, tmp_path, monkeypatch)

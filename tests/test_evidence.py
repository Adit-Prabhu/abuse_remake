"""The committed evidence still matches the game: every episode trace under evidence/traces
replays through the current engine and interface with every observation hash and the outcome
matching. A rule or interface change that alters a recorded episode fails here, so the evidence
is regenerated (and the change noted) instead of silently going stale."""

from pathlib import Path

import pytest

from abuse_remake.paths import repo_root

TRACES = sorted((Path(repo_root()) / "evidence" / "traces").rglob("*.jsonl"))


def test_there_is_committed_evidence():
    assert TRACES


@pytest.mark.parametrize("path", TRACES, ids=[str(p.relative_to(Path(repo_root()) / "evidence" / "traces"))
                                              for p in TRACES])
def test_a_committed_trace_replays_exactly(path, tmp_path, monkeypatch):
    from abuse_remake.game.spectate import main

    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    assert main(["--trace", str(path), "--headless", "--scale", "1"]) == 0

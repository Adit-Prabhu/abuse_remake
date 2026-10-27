"""The documents a reader follows point only to files that exist, in this repository and in the
course folder exported from it. History (review records, progress notes, the agents' session
record) is left as written."""

import re
from pathlib import Path

import pytest

from abuse_remake.paths import repo_root

ROOT = Path(repo_root())
DOCS = [ROOT / n for n in ("README.md", "EVALUATION.md", "SUITE.md", "SCOPE.md", "AGENTS.md")] + [
    p for p in sorted((ROOT / "docs").rglob("*.md"))
    if "reviews" not in p.parts and p.name not in ("PROGRESS.md", "agent-team-log.md")]
PATH = re.compile(r"`((?:src|tests|docs|eval|evidence|scripts|data|\.claude|\.github)/[\w./-]+\.[a-z]+)`")
# outputs and placeholders, and what the course export leaves out (the docs say so where they cite it)
SKIP = ("runs/", "playtests/raw/")
EXPORT_LEAVES_OUT = (".github/", "packaging/", "evidence/video/")


@pytest.mark.parametrize("doc", DOCS, ids=[str(p.relative_to(ROOT)) for p in DOCS])
def test_cited_paths_exist(doc):
    missing = []
    for path in PATH.findall(doc.read_text()):
        if path.startswith(SKIP) or any(c in path for c in "<*{"):
            continue
        if path.startswith(EXPORT_LEAVES_OUT) and not (ROOT / ".git").exists():
            continue
        if not (ROOT / path).exists() and not (path.startswith(".github/") and _at_repository_root(path)):
            missing.append(path)
    assert not missing, missing


def _at_repository_root(path: str) -> bool:
    return any((d / path).exists() for d in ROOT.parents)

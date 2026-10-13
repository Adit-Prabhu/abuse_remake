"""SCOPE.md, scope.py and the level file must agree on what Level 1 contains."""

from pathlib import Path

from abuse_remake.formats.level_file import load_level
from abuse_remake.paths import level_path, repo_root
from abuse_remake.scope import LEVEL, LEVEL01_TYPES


def test_scope_lists_exactly_the_types_in_the_level_file():
    lv = load_level(level_path(LEVEL))
    assert {o.type_name for o in lv.live_objects()} == set(LEVEL01_TYPES)


def test_scope_document_names_every_type():
    text = Path(repo_root(), "SCOPE.md").read_text()
    missing = sorted(t for t in LEVEL01_TYPES if f"`{t}`" not in text)
    assert missing == []

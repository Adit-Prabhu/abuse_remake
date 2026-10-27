"""scripts/export_submission.py: what goes into the course folder, and when it refuses."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from abuse_remake.paths import repo_root


def _module():
    spec = importlib.util.spec_from_file_location("export_submission",
                                                  Path(repo_root()) / "scripts" / "export_submission.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _repo(path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c"]):
        subprocess.run(["git", *cmd], cwd=path, check=True, capture_output=True)
    return path


@pytest.fixture
def repos(tmp_path):
    mod = _module()
    project = _repo(tmp_path / "project", {
        "src/a.py": "x = 1\n", "README.md": "r\n", ".gitignore": "!evidence/reports/\n",
        mod.WORKFLOW: "name: w\n", "packaging/p.py": "p\n", "evidence/video/v.mp4": "v",
        "evidence/reports/r.md": "report\n"})
    course = _repo(tmp_path / "course", {"minigames/x.md": "m\n", ".gitignore": "reports/\n*.secret\n"})
    return mod, project, course


def test_the_folder_is_the_commit_minus_what_the_course_does_not_take(repos):
    mod, project, course = repos
    record = mod.export(project, course)
    dest = course / "midterms" / mod.LOGIN
    assert (dest / "src/a.py").read_text() == "x = 1\n" and (dest / "evidence/reports/r.md").exists()
    assert not (dest / ".github").exists() and not (dest / "packaging").exists()
    assert not (dest / "evidence/video").exists()
    assert (course / mod.WORKFLOW).read_text() == "name: w\n"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True).stdout.strip()
    assert json.loads((dest / "EXPORTED_FROM.json").read_text())["commit"] == head == record["commit"]


def test_it_refuses_a_dirty_project(repos):
    mod, project, course = repos
    (project / "src/a.py").write_text("x = 2\n")
    with pytest.raises(SystemExit, match="commit or stash"):
        mod.export(project, course)


def test_it_never_overwrites_uncommitted_work_in_the_course_folder(repos):
    mod, project, course = repos
    mod.export(project, course)
    subprocess.run(["git", "add", "-A"], cwd=course, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "e"], cwd=course, check=True)
    (course / "midterms" / mod.LOGIN / "AGENT-TEAM.md").write_text("my own words\n")
    with pytest.raises(SystemExit, match="uncommitted changes"):
        mod.export(project, course)
    assert (course / "midterms" / mod.LOGIN / "AGENT-TEAM.md").read_text() == "my own words\n"


def test_it_fails_when_the_course_would_ignore_an_exported_file(repos):
    mod, project, course = repos
    (project / "notes.secret").write_text("s\n")
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "s"], cwd=project, check=True)
    with pytest.raises(SystemExit, match="notes.secret"):
        mod.export(project, course)


def test_it_refuses_to_run_from_inside_the_course_repository(repos):
    mod, project, course = repos
    with pytest.raises(SystemExit, match="not from inside"):
        mod.export(course / "minigames", course)

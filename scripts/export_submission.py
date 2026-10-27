"""Copy the submission into the course repository: midterms/<login>/ and its one workflow file.

    uv run python scripts/export_submission.py ~/PycharmProjects/game-dev-f26

Run it from this (the project) repository. It copies the files git tracks at HEAD, so nothing
ignored or untracked goes in (.venv, runs, cache, scratch files; also a file you never
committed). It leaves out what the course submission must not or need not carry:
- this repository's own workflows (the course allows one workflow, copied separately to the
  course repository's root, from HEAD);
- the release packaging;
- generated video (the recording is linked instead).

It refuses:
- to run from inside the course repository;
- when either repository has uncommitted changes in the paths it would write. The student's
  own files in the course folder (for example AGENT-TEAM.md before it is copied back here) are
  never overwritten unnoticed.

It builds the archive before deleting anything. After writing, it checks every path against the
course repository's ignore rules, and fails if git would leave any of them out of a commit. It
writes ``EXPORTED_FROM.json`` into the folder: the project commit and git's tree hash of
``src/``, which every evaluation run records as ``src_tree``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

LOGIN = "adit-prabhu"
WORKFLOW = f".github/workflows/midterm-{LOGIN}.yml"
EXCLUDE = (".github/", "packaging/", "evidence/video/")
ROOT = Path(__file__).resolve().parents[1]


def git(cwd: Path, *args: str, data: bytes | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, input=data, check=False)
    if r.returncode not in (0, 1):  # check-ignore answers 1 when nothing is ignored
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout.decode(errors="replace").strip()


def export(root: Path, course: Path) -> dict:
    root, course = root.resolve(), course.expanduser().resolve()
    if not (course / ".git").exists() or not (course / "minigames").exists():
        raise SystemExit(f"{course} does not look like a clone of the course repository")
    if root == course or course in root.parents:
        raise SystemExit("run this from the project repository, not from inside the course repository")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("commit or stash your changes first: the export is a commit, not a working tree")
    folder = f"midterms/{LOGIN}"
    if git(course, "status", "--porcelain", "--", folder, WORKFLOW):
        raise SystemExit(f"the course repository has uncommitted changes in {folder} or {WORKFLOW}; "
                         "commit them there (or copy them back here) first")
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=root, capture_output=True, check=True)
    workflow = subprocess.run(["git", "show", f"HEAD:{WORKFLOW}"], cwd=root, capture_output=True, check=True).stdout
    files = []
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        for member in tar:
            if member.isfile() and not member.name.startswith(EXCLUDE):
                files.append((member.name, tar.extractfile(member).read(), member.mode & 0o777))
    commit = git(root, "rev-parse", "HEAD")
    record = {"project": "https://github.com/Adit-Prabhu/abuse_remake", "commit": commit,
              "src_tree": git(root, "rev-parse", "HEAD:src"),
              "exported_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "files": len(files)}
    dest = course / folder
    if dest.exists():
        shutil.rmtree(dest)
    for name, data, mode in files:
        out = dest / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        out.chmod(mode)
    (dest / "EXPORTED_FROM.json").write_text(json.dumps(record, indent=1) + "\n")
    (course / WORKFLOW).parent.mkdir(parents=True, exist_ok=True)
    (course / WORKFLOW).write_bytes(workflow)
    paths = [f"{folder}/{name}" for name, _, _ in files] + [f"{folder}/EXPORTED_FROM.json", WORKFLOW]
    ignored = git(course, "check-ignore", "--no-index", "--stdin", data="\n".join(paths).encode()).splitlines()
    if ignored:
        raise SystemExit("the course repository's ignore rules would leave these out of a commit:\n  "
                         + "\n  ".join(ignored) + f"\nadd a negation to {folder}/.gitignore (via this repository)")
    return record


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("course_repo", type=Path, help="a clone of the course repository")
    args = ap.parse_args(argv)
    record = export(ROOT, args.course_repo)
    print(f"copied {record['files']} files from {record['commit'][:7]} into {args.course_repo}/midterms/{LOGIN}")
    print(f"src tree {record['src_tree']}; workflow {WORKFLOW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

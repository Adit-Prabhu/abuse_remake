"""Copy the submission into the course repository: midterms/<login>/ and its one workflow file.

    uv run python scripts/export_submission.py ~/PycharmProjects/game-dev-f26

It copies the files git tracks at HEAD, so nothing ignored or untracked goes in (.venv, runs,
cache, scratch files). It leaves out what the course submission must not or need not carry:
- this repository's own workflows (the course allows one workflow, copied separately to the
  course repository's root);
- the release packaging;
- generated video (the recording is linked instead).

The folder is replaced, so a file deleted here is deleted there. The script refuses to run with
uncommitted changes, so the folder is exactly a commit of this repository. At the end it prints
git's tree hash of src/ for the commit, which a run's ``config.json`` records as ``src_tree``.
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

LOGIN = "adit-prabhu"
WORKFLOW = f".github/workflows/midterm-{LOGIN}.yml"
EXCLUDE = (".github/", "packaging/", "evidence/video/")
ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("course_repo", type=Path, help="a clone of the course repository")
    args = ap.parse_args(argv)
    course = args.course_repo.expanduser().resolve()
    if not (course / ".git").exists() or not (course / "minigames").exists():
        raise SystemExit(f"{course} does not look like a clone of the course repository")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("commit or stash your changes first: the export is a commit, not a working tree")
    dest = course / "midterms" / LOGIN
    if dest.exists():
        shutil.rmtree(dest)
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, capture_output=True, check=True)
    copied = 0
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        for member in tar:
            if not member.isfile() or member.name.startswith(EXCLUDE):
                continue
            out = dest / member.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(tar.extractfile(member).read())
            out.chmod(member.mode & 0o777)
            copied += 1
    wf = course / WORKFLOW
    wf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / WORKFLOW, wf)
    print(f"copied {copied} files from {git('rev-parse', '--short', 'HEAD')} to {dest}")
    print(f"workflow: {wf}")
    print(f"src tree: {git('rev-parse', 'HEAD:src')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

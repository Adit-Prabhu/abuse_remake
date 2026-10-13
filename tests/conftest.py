import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

C_REFERENCE = Path(__file__).parent / "c_reference"

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _compile(src: Path, out: Path) -> str | None:
    """Compile a reference harness; return None on success or the last error."""
    if src.suffix == ".cpp":
        cc = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    else:
        cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        return f"no compiler on PATH for {src.suffix}"
    attempts = [[cc, "-w", "-O0", "-o", str(out), str(src)]]
    if sys.platform == "darwin":  # some Command Line Tools ship an SDK the linker rejects
        sdks = sorted(Path("/Library/Developer/CommandLineTools/SDKs").glob("MacOSX1*.sdk"), reverse=True)
        attempts += [[cc, "-w", "-O0", "-isysroot", str(s), "-o", str(out), str(src)] for s in sdks]
    err = ""
    for cmd in attempts:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return None
        err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"exit {r.returncode}"
    return err


@pytest.fixture(scope="session")
def c_reference(tmp_path_factory):
    """Build a harness from tests/c_reference/<name>.c, made of verbatim original C code."""
    built: dict[str, Path] = {}

    def get(name: str) -> Path:
        if name not in built:
            out = tmp_path_factory.mktemp("cref") / name
            src = C_REFERENCE / f"{name}.c"
            if not src.exists():
                src = C_REFERENCE / f"{name}.cpp"
            err = _compile(src, out)
            if err is not None:
                if os.environ.get("ABUSE_REQUIRE_C_REFERENCE") == "1":
                    pytest.fail(f"cannot build C reference {name}: {err}")
                pytest.skip(f"cannot build C reference {name}: {err}")
            built[name] = out
        return built[name]

    return get

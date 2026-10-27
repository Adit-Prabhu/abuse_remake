"""Make the key that unlocks developer test mode on this machine (``game/devmode.py``).

    uv run python scripts/new_dev_key.py

It writes a random secret to ``~/.abuse_remake/dev.key`` (readable by you alone) and prints its
SHA-256. Put that hash in ``devmode.KEY_SHA256`` and commit it; the secret itself never goes in the
repository. A key made on another machine has another hash, so it unlocks nothing until its hash
is committed. Run it again with ``--force`` to replace a key, which locks out the old one.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from abuse_remake.game.devmode import key_path  # noqa: E402


def main(argv: list[str]) -> int:
    path = key_path()
    if path.exists() and "--force" not in argv:
        print(f"{path} already exists; --force replaces it (and locks out its hash)", file=sys.stderr)
        return 1
    secret = secrets.token_hex(32).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(secret + b"\n")
    os.chmod(path, 0o600)
    print(f"key written to {path}")
    print(f'KEY_SHA256 = "{hashlib.sha256(secret).hexdigest()}"')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

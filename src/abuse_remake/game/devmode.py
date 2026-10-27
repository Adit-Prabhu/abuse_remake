"""Developer test mode: the student's testing tool, locked to the student's machine.

``uv run abuse-remake --dev`` starts it, and only where ``~/.abuse_remake/dev.key`` holds the
secret whose SHA-256 is ``KEY_SHA256``. The secret is in no file of the repository, its export or
a release, so a published copy cannot enter dev mode: without the key, ``--dev`` is refused like
any made-up option, and nothing on screen or in ``--help`` mentions it. The lock guards the game as
published and launched; anyone who edits the source or runs their own Python against it
(``Game(dev=True)``, or ``args.dev``) can turn anything on.

In dev mode (Remastered only; the rules are ``Game(dev=True)`` in ``engine/remastered.py``):
- the player takes no damage and health stays full;
- guns 1-4 are owned and never run out;
- Tab opens a menu that gives any power-up and switches the two above.
It never saves best times, ghosts or Horde scores, and it cannot be combined with ``--record`` or
``--playtest``, so no record or trace holds a dev game. Classic, the fidelity tests and every
evaluation are untouched.

``scripts/new_dev_key.py`` makes a key for a new machine and prints the hash to put here.
"""

from __future__ import annotations

import hashlib
import hmac

from .remaster import data_dir

FLAG = "--dev"
# the SHA-256 of the student's key (made by scripts/new_dev_key.py); the key itself is not in the repo
KEY_SHA256 = "bf04788428f4476227d2b04f8917749ce137fb05a76aa7f146149cd8a2f17a5a"


def key_path():
    return data_dir() / "dev.key"


def unlocked() -> bool:
    try:
        secret = key_path().read_bytes().strip()
    except OSError:
        return False
    return bool(secret) and hmac.compare_digest(hashlib.sha256(secret).hexdigest(), KEY_SHA256)


def take_flag(argv: list[str]) -> tuple[list[str], bool]:
    """``--dev`` taken out of the arguments when the key unlocks it. Otherwise the arguments are
    left as they are, so argparse refuses ``--dev`` as an unknown option."""
    if FLAG in argv and unlocked():
        return [a for a in argv if a != FLAG], True
    return argv, False

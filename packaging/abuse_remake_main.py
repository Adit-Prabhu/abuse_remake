"""Entry point for the PyInstaller build of the game (``.github/workflows/release.yml``)."""

import sys

from abuse_remake.game.app import main

if __name__ == "__main__":
    sys.exit(main())

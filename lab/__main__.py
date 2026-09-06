"""Allow ``python -m lab`` as well as the installed ``lab`` command."""

from __future__ import annotations

from lab.cli import app

if __name__ == "__main__":
    app()

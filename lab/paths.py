"""Filesystem layout of the lab.

Every other module asks this one where things live, so the layout is defined in
exactly one place. Paths are resolved from the repository root, which is found by
walking up from this file until a directory containing ``pyproject.toml`` appears.
That keeps the CLI working regardless of the directory it is invoked from.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "CORRECTIONS_DIR",
    "DATA_DIR",
    "EXERCISES_DIR",
    "REPO_ROOT",
    "STATE_DIR",
    "WAREHOUSE_PATH",
    "find_repo_root",
]


def find_repo_root(start: Path | None = None) -> Path:
    """Return the repository root: the nearest ancestor holding ``pyproject.toml``.

    Falls back to the package's parent directory when no marker is found, which
    happens if the package is installed outside a checkout.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path(__file__).resolve().parent.parent


REPO_ROOT: Path = find_repo_root()

#: Exercise files you edit.
EXERCISES_DIR: Path = REPO_ROOT / "exercises"

#: Reference implementations and hints. Hidden by convention, not by git.
CORRECTIONS_DIR: Path = REPO_ROOT / ".corrections"

#: Generated dataset. Rebuilt from your seed, never committed.
DATA_DIR: Path = REPO_ROOT / "data"

#: The DuckDB database the SQL track queries.
WAREHOUSE_PATH: Path = DATA_DIR / "warehouse.duckdb"

#: Per-learner state: the session seed and your progress.
STATE_DIR: Path = REPO_ROOT / ".lab"

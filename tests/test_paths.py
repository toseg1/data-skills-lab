"""The layout module is the single source of truth for where things live."""

from __future__ import annotations

from lab.paths import (
    CORRECTIONS_DIR,
    DATA_DIR,
    EXERCISES_DIR,
    REPO_ROOT,
    STATE_DIR,
    WAREHOUSE_PATH,
    find_repo_root,
)


def test_repo_root_holds_the_project_file() -> None:
    assert (REPO_ROOT / "pyproject.toml").is_file()


def test_find_repo_root_walks_up_from_a_nested_path() -> None:
    nested = REPO_ROOT / "lab" / "paths.py"
    assert find_repo_root(nested) == REPO_ROOT


def test_find_repo_root_falls_back_outside_a_checkout(tmp_path) -> None:
    # No pyproject.toml anywhere above tmp_path, so the fallback branch is taken
    # rather than raising.
    assert find_repo_root(tmp_path).is_dir()


def test_every_path_sits_inside_the_repo() -> None:
    for path in (EXERCISES_DIR, CORRECTIONS_DIR, DATA_DIR, WAREHOUSE_PATH, STATE_DIR):
        assert path.is_relative_to(REPO_ROOT)


def test_exercises_and_corrections_mirror_each_other() -> None:
    # The grader pairs an exercise with its reference by relative path, so the
    # two trees must be siblings with the same root.
    assert EXERCISES_DIR.parent == CORRECTIONS_DIR.parent


def test_warehouse_lives_in_the_data_directory() -> None:
    assert WAREHOUSE_PATH.parent == DATA_DIR

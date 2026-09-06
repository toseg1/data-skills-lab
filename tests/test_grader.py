"""Running exercises against their references, and reporting what happened."""

from __future__ import annotations

import pytest

from lab.discovery import discover
from lab.grader import grade
from lab.paths import CORRECTIONS_DIR, EXERCISES_DIR
from lab.workspace import Workspace


@pytest.fixture
def graded(mini_lab):
    exercises = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    with Workspace(mini_lab.data) as workspace:
        yield exercises, workspace


def test_a_correct_answer_passes(graded) -> None:
    exercises, workspace = graded
    result = grade(exercises["demo/01_scalar"], workspace)
    assert result.outcome == "passed"
    assert result.seconds >= 0


def test_a_wrong_answer_fails_with_an_explanation(graded) -> None:
    exercises, workspace = graded
    result = grade(exercises["demo/02_frame"], workspace)
    assert result.outcome == "failed"
    assert result.comparison is not None
    assert result.comparison.details


def test_an_untouched_stub_is_not_started_rather_than_wrong(graded) -> None:
    """The distinction matters: `lab status` should not call unstarted work wrong."""
    exercises, workspace = graded
    assert grade(exercises["demo/03_stub"], workspace).outcome == "not_started"


def test_an_exception_is_reported_with_a_traceback(graded) -> None:
    exercises, workspace = graded
    result = grade(exercises["demo/04_broken"], workspace)
    assert result.outcome == "error"
    assert "ZeroDivisionError" in (result.error or "")


def test_a_sql_exercise_is_executed_against_the_warehouse(graded) -> None:
    exercises, workspace = graded
    assert grade(exercises["demo/05_query"], workspace).outcome == "passed"


def test_an_empty_query_counts_as_not_started(mini_lab) -> None:
    (mini_lab.exercises / "demo" / "06_empty.sql").write_text(
        "-- Write your query here.\n", encoding="utf-8"
    )
    (mini_lab.corrections / "demo" / "06_empty.sql").write_text("SELECT 1 AS n\n", encoding="utf-8")
    exercises = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    with Workspace(mini_lab.data) as workspace:
        assert grade(exercises["demo/06_empty"], workspace).outcome == "not_started"


def test_a_missing_reference_is_flagged_not_silently_passed(mini_lab) -> None:
    (mini_lab.exercises / "demo" / "07_orphan.py").write_text(
        '"""Orphan"""\n\ndef solve(trades):\n    return 1\n', encoding="utf-8"
    )
    exercises = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    with Workspace(mini_lab.data) as workspace:
        assert grade(exercises["demo/07_orphan"], workspace).outcome == "no_reference"


def test_asking_for_an_unavailable_input_says_what_is_available(mini_lab) -> None:
    (mini_lab.exercises / "demo" / "08_bad_input.py").write_text(
        '"""Bad input"""\n\ndef solve(bananas):\n    return bananas\n', encoding="utf-8"
    )
    (mini_lab.corrections / "demo" / "08_bad_input.py").write_text(
        '"""Reference"""\n\ndef solve(trades):\n    return len(trades)\n', encoding="utf-8"
    )
    exercises = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    with Workspace(mini_lab.data) as workspace:
        result = grade(exercises["demo/08_bad_input"], workspace)
    assert result.outcome == "error"
    assert "bananas" in (result.error or "")
    assert "trades" in (result.error or "")


def test_a_file_without_solve_is_reported_clearly(mini_lab) -> None:
    (mini_lab.exercises / "demo" / "09_no_solve.py").write_text(
        '"""No solve"""\n\nx = 1\n', encoding="utf-8"
    )
    (mini_lab.corrections / "demo" / "09_no_solve.py").write_text(
        '"""Reference"""\n\ndef solve(trades):\n    return 1\n', encoding="utf-8"
    )
    exercises = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    with Workspace(mini_lab.data) as workspace:
        result = grade(exercises["demo/09_no_solve"], workspace)
    assert result.outcome == "error"
    assert "solve" in (result.error or "")


def test_a_broken_reference_is_labelled_a_lab_bug(mini_lab) -> None:
    """A learner should never be told their correct answer is wrong."""
    (mini_lab.exercises / "demo" / "10_bad_ref.py").write_text(
        '"""Fine"""\n\ndef solve(trades):\n    return 1\n', encoding="utf-8"
    )
    (mini_lab.corrections / "demo" / "10_bad_ref.py").write_text(
        '"""Reference"""\n\ndef solve(trades):\n    return undefined_name\n', encoding="utf-8"
    )
    exercises = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    with Workspace(mini_lab.data) as workspace:
        result = grade(exercises["demo/10_bad_ref"], workspace)
    assert result.outcome == "error"
    assert "bug in the lab" in (result.error or "")


def test_exercises_do_not_leak_into_one_another(mini_lab) -> None:
    """Two files defining the same names must not collide in sys.modules."""
    for name in ("11_first", "12_second"):
        (mini_lab.exercises / "demo" / f"{name}.py").write_text(
            f'"""{name}"""\n\nSHARED = "{name}"\n\ndef solve(trades):\n    return SHARED\n',
            encoding="utf-8",
        )
        (mini_lab.corrections / "demo" / f"{name}.py").write_text(
            f'"""Reference"""\n\ndef solve(trades):\n    return "{name}"\n', encoding="utf-8"
        )
    exercises = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    with Workspace(mini_lab.data) as workspace:
        assert grade(exercises["demo/11_first"], workspace).outcome == "passed"
        assert grade(exercises["demo/12_second"], workspace).outcome == "passed"


def test_mutating_a_table_cannot_affect_the_reference(mini_lab) -> None:
    """Both sides must be graded against identical inputs."""
    (mini_lab.exercises / "demo" / "13_mutates.py").write_text(
        '"""Mutates its input"""\n\n'
        "def solve(trades):\n"
        "    trades.drop(trades.index[:5], inplace=True)\n"
        "    return len(trades)\n",
        encoding="utf-8",
    )
    (mini_lab.corrections / "demo" / "13_mutates.py").write_text(
        '"""Reference"""\n\ndef solve(trades):\n    return len(trades)\n', encoding="utf-8"
    )
    exercises = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    with Workspace(mini_lab.data) as workspace:
        result = grade(exercises["demo/13_mutates"], workspace)
    # The learner deleted rows, so their count is wrong — but the reference must
    # still have seen the full table.
    assert result.outcome == "failed"
    assert "120" in result.comparison.headline


# --------------------------------------------------------------------------- #
# The shipped exercises
# --------------------------------------------------------------------------- #


def test_every_shipped_reference_runs_and_agrees_with_itself(tiny_dataset_dir) -> None:
    """Catches a reference that crashes or is non-deterministic."""
    from dataclasses import replace as dataclass_replace

    with Workspace(tiny_dataset_dir) as workspace:
        for exercise in discover(EXERCISES_DIR, CORRECTIONS_DIR):
            as_if_solved = dataclass_replace(exercise, path=exercise.reference)
            result = grade(as_if_solved, workspace)
            assert result.outcome == "passed", f"{exercise.id}: {result.error or result.comparison}"


def test_shipped_stubs_are_all_unattempted(tiny_dataset_dir) -> None:
    with Workspace(tiny_dataset_dir) as workspace:
        for exercise in discover(EXERCISES_DIR, CORRECTIONS_DIR):
            assert grade(exercise, workspace).outcome == "not_started", exercise.id

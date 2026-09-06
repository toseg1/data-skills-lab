"""Finding exercises, reading their headers, and resolving selectors."""

from __future__ import annotations

from lab.discovery import discover, read_brief, select, split_hints
from lab.paths import CORRECTIONS_DIR, EXERCISES_DIR


def test_discovers_the_mini_lab(mini_lab) -> None:
    found = discover(mini_lab.exercises, mini_lab.corrections)
    assert [e.id for e in found] == [
        "demo/01_scalar",
        "demo/02_frame",
        "demo/03_stub",
        "demo/04_broken",
        "demo/05_query",
    ]


def test_kind_comes_from_the_suffix(mini_lab) -> None:
    found = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    assert found["demo/01_scalar"].kind == "python"
    assert found["demo/05_query"].kind == "sql"


def test_title_is_read_from_the_docstring(mini_lab) -> None:
    found = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    assert found["demo/01_scalar"].title == "Count the trades"


def test_references_and_hints_are_paired(mini_lab) -> None:
    found = {e.id: e for e in discover(mini_lab.exercises, mini_lab.corrections)}
    assert found["demo/01_scalar"].has_reference()
    assert found["demo/01_scalar"].read_hints() == ["First hint.", "Second hint."]
    assert found["demo/02_frame"].read_hints() == []


def test_track_and_section(mini_lab) -> None:
    exercise = discover(mini_lab.exercises, mini_lab.corrections)[0]
    assert exercise.track == "demo"
    assert exercise.section == "demo"


def test_selector_tiers(mini_lab) -> None:
    found = discover(mini_lab.exercises, mini_lab.corrections)
    assert [e.id for e in select(found, "demo/01_scalar")] == ["demo/01_scalar"]
    assert len(select(found, "demo")) == 5
    assert [e.id for e in select(found, "demo/05")] == ["demo/05_query"]
    assert [e.id for e in select(found, "scalar")] == ["demo/01_scalar"]
    assert select(found, "nonsense") == []
    assert len(select(found, None)) == 5


def test_split_hints_handles_trailing_whitespace() -> None:
    assert split_hints("a\n\n---\n\nb\n\n---\n\n") == ["a", "b"]


def test_brief_is_the_task_text(mini_lab) -> None:
    exercise = discover(mini_lab.exercises, mini_lab.corrections)[0]
    assert "Return the number of rows" in read_brief(exercise)


# --------------------------------------------------------------------------- #
# The real exercise tree
# --------------------------------------------------------------------------- #


def test_the_shipped_setup_exercises_are_wired_up() -> None:
    found = {e.id: e for e in discover(EXERCISES_DIR, CORRECTIONS_DIR)}
    assert "00_setup/01_environment" in found
    assert "00_setup/02_first_query" in found
    assert "00_setup/03_first_frame" in found


def test_every_shipped_exercise_has_a_reference() -> None:
    for exercise in discover(EXERCISES_DIR, CORRECTIONS_DIR):
        assert exercise.has_reference(), f"{exercise.id} has no reference"


def test_the_top_five_query_is_order_sensitive() -> None:
    found = {e.id: e for e in discover(EXERCISES_DIR, CORRECTIONS_DIR)}
    assert found["00_setup/02_first_query"].ordered is True
    assert found["00_setup/01_environment"].ordered is False


def test_shipped_exercises_have_hints() -> None:
    for exercise in discover(EXERCISES_DIR, CORRECTIONS_DIR):
        assert len(exercise.read_hints()) >= 2, f"{exercise.id} needs hints"

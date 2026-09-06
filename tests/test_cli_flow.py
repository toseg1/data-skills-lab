"""The commands a learner actually types, end to end."""

from __future__ import annotations

from typer.testing import CliRunner

import lab.cli
from lab.cli import app
from lab.session import load_session

runner = CliRunner()


def test_next_shows_the_first_unsolved_exercise_and_its_task(mini_lab) -> None:
    result = runner.invoke(app, ["next"])
    assert result.exit_code == 0
    assert "demo/01_scalar" in result.stdout
    assert "Return the number of rows" in result.stdout


def test_check_passes_a_correct_answer(mini_lab) -> None:
    result = runner.invoke(app, ["check", "demo/01_scalar"])
    assert result.exit_code == 0
    assert "pass" in result.stdout
    assert load_session(mini_lab.state).is_passed("demo/01_scalar")


def test_check_fails_a_wrong_answer_and_exits_non_zero(mini_lab) -> None:
    result = runner.invoke(app, ["check", "demo/02_frame"])
    assert result.exit_code == 1
    assert "fail" in result.stdout
    assert not load_session(mini_lab.state).is_passed("demo/02_frame")


def test_check_reports_an_unstarted_exercise_as_todo(mini_lab) -> None:
    result = runner.invoke(app, ["check", "demo/03_stub"])
    assert "todo" in result.stdout


def test_check_a_whole_section_summarises(mini_lab) -> None:
    result = runner.invoke(app, ["check", "demo"])
    assert result.exit_code == 1  # the section contains failures
    assert "passed" in result.stdout


def test_check_records_attempts(mini_lab) -> None:
    runner.invoke(app, ["check", "demo/02_frame"])
    runner.invoke(app, ["check", "demo/02_frame"])
    assert load_session(mini_lab.state).progress["demo/02_frame"].attempts == 2


def test_an_unknown_selector_is_rejected(mini_lab) -> None:
    result = runner.invoke(app, ["check", "not-a-thing"])
    assert result.exit_code == 1
    assert "Nothing matches" in result.stdout


def test_hints_come_one_at_a_time(mini_lab) -> None:
    first = runner.invoke(app, ["hint", "demo/01_scalar"])
    assert "First hint." in first.stdout
    assert "hint 1 of 2" in first.stdout

    second = runner.invoke(app, ["hint", "demo/01_scalar"])
    assert "Second hint." in second.stdout

    again = runner.invoke(app, ["hint", "demo/01_scalar"])
    assert "Second hint." in again.stdout  # stays on the last one

    reset = runner.invoke(app, ["hint", "demo/01_scalar", "--reset"])
    assert "First hint." in reset.stdout


def test_hint_without_hints_says_so(mini_lab) -> None:
    result = runner.invoke(app, ["hint", "demo/02_frame"])
    assert result.exit_code == 1
    assert "No hints" in result.stdout


def test_solve_refuses_without_confirmation(mini_lab) -> None:
    result = runner.invoke(app, ["solve", "demo/01_scalar"])
    assert result.exit_code == 1
    assert "--yes" in result.stdout


def test_solve_with_yes_prints_the_reference(mini_lab) -> None:
    result = runner.invoke(app, ["solve", "demo/01_scalar", "--yes"])
    assert result.exit_code == 0
    assert "return len(trades)" in result.stdout


def test_status_tracks_what_has_been_solved(mini_lab) -> None:
    before = runner.invoke(app, ["status"])
    assert "0/5" in before.stdout

    runner.invoke(app, ["check", "demo/01_scalar"])
    after = runner.invoke(app, ["status"])
    assert "1/5" in after.stdout
    assert str(mini_lab.seed) in after.stdout


def test_status_points_at_the_next_exercise(mini_lab) -> None:
    runner.invoke(app, ["check", "demo/01_scalar"])
    result = runner.invoke(app, ["status"])
    assert "Next up" in result.stdout
    assert "demo/02_frame" in result.stdout


def test_next_reports_completion_when_everything_passes(mini_lab, monkeypatch) -> None:
    session = load_session(mini_lab.state)
    for name in ("01_scalar", "02_frame", "03_stub", "04_broken", "05_query"):
        session.record_attempt(f"demo/{name}", passed=True)
    from lab.session import save_session

    save_session(session, mini_lab.state)
    result = runner.invoke(app, ["next"])
    assert "solved" in result.stdout


def test_info_reports_the_seed_once_a_session_exists(mini_lab) -> None:
    result = runner.invoke(app, ["info"])
    assert str(mini_lab.seed) in result.stdout


# --------------------------------------------------------------------------- #
# init and reseed
# --------------------------------------------------------------------------- #


def test_init_refuses_to_clobber_an_existing_session(mini_lab) -> None:
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert "already have a session" in result.stdout
    assert "reseed" in result.stdout


def test_init_force_starts_over(mini_lab, monkeypatch) -> None:
    built: list[int] = []
    monkeypatch.setattr(lab.cli, "_build_dataset", lambda seed, out: built.append(seed))

    result = runner.invoke(app, ["init", "--seed", "777", "--force"])
    assert result.exit_code == 0
    assert built == [777]
    assert load_session(mini_lab.state).seed == 777


def test_reseed_keeps_progress_by_default(mini_lab, monkeypatch) -> None:
    monkeypatch.setattr(lab.cli, "_build_dataset", lambda seed, out: None)
    runner.invoke(app, ["check", "demo/01_scalar"])

    result = runner.invoke(app, ["reseed", "--seed", "4242"])
    assert result.exit_code == 0
    session = load_session(mini_lab.state)
    assert session.seed == 4242
    assert session.is_passed("demo/01_scalar")


def test_reseed_can_clear_progress(mini_lab, monkeypatch) -> None:
    monkeypatch.setattr(lab.cli, "_build_dataset", lambda seed, out: None)
    runner.invoke(app, ["check", "demo/01_scalar"])

    runner.invoke(app, ["reseed", "--seed", "5", "--reset-progress"])
    assert not load_session(mini_lab.state).is_passed("demo/01_scalar")


def test_commands_needing_a_session_say_how_to_start(tmp_path, monkeypatch) -> None:
    import lab.session

    monkeypatch.setattr(lab.session, "STATE_DIR", tmp_path / "empty")
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "lab init" in result.stdout

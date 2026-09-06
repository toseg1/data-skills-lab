"""Session state: the seed and the progress record."""

from __future__ import annotations

import json

import pytest

from lab.session import (
    Session,
    SessionError,
    draw_seed,
    load_session,
    new_session,
    save_session,
    session_path,
)


def test_a_drawn_seed_is_positive_and_varies() -> None:
    seeds = {draw_seed() for _ in range(20)}
    assert all(s > 0 for s in seeds)
    assert len(seeds) > 1


def test_round_trip(tmp_path) -> None:
    session = new_session(999)
    session.record_attempt("sql/01", passed=True)
    save_session(session, tmp_path)

    loaded = load_session(tmp_path)
    assert loaded.seed == 999
    assert loaded.is_passed("sql/01")
    assert loaded.progress["sql/01"].attempts == 1


def test_attempts_accumulate_and_pass_is_sticky(tmp_path) -> None:
    session = new_session(1)
    session.record_attempt("a", passed=False)
    session.record_attempt("a", passed=True)
    first_solved_at = session.progress["a"].solved_at
    session.record_attempt("a", passed=True)

    assert session.progress["a"].attempts == 3
    assert session.is_passed("a")
    # The moment you first solved it should not drift on re-checks.
    assert session.progress["a"].solved_at == first_solved_at


def test_hints_advance_and_stop_at_the_end(tmp_path) -> None:
    session = new_session(1)
    assert session.next_hint("a", available=2) == 1
    assert session.next_hint("a", available=2) == 2
    assert session.next_hint("a", available=2) == 2
    session.reset_hints("a")
    assert session.entry("a").hints_shown == 0


def test_missing_session_explains_how_to_start(tmp_path) -> None:
    with pytest.raises(SessionError, match="lab init"):
        load_session(tmp_path)


def test_corrupt_session_is_reported_not_swallowed(tmp_path) -> None:
    path = session_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError, match="not valid JSON"):
        load_session(tmp_path)


def test_session_missing_fields_is_reported(tmp_path) -> None:
    path = session_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"created_at": "now"}), encoding="utf-8")
    with pytest.raises(SessionError, match="missing fields"):
        load_session(tmp_path)


def test_saving_leaves_no_temporary_file_behind(tmp_path) -> None:
    save_session(new_session(5), tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


def test_written_json_is_human_readable(tmp_path) -> None:
    session = Session(seed=7, created_at="2026-01-01T00:00:00+00:00")
    session.record_attempt("x", passed=True)
    payload = json.loads(save_session(session, tmp_path).read_text(encoding="utf-8"))
    assert payload["seed"] == 7
    assert payload["progress"]["x"]["status"] == "passed"

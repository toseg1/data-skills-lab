"""Smoke tests for the command line surface."""

from __future__ import annotations

from typer.testing import CliRunner

from lab import __version__
from lab.cli import app

runner = CliRunner()


def test_version_flag_reports_the_package_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_bare_invocation_shows_help_rather_than_failing_silently() -> None:
    result = runner.invoke(app, [])
    assert "Usage" in result.stdout


def test_info_runs_and_names_the_directories() -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    for label in ("exercises", "corrections", "warehouse"):
        assert label in result.stdout


def test_unknown_command_exits_non_zero() -> None:
    result = runner.invoke(app, ["definitely-not-a-command"])
    assert result.exit_code != 0

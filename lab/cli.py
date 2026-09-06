"""Command line entry point.

This scaffold ships ``lab info`` and ``lab --version`` only. The exercise
commands (``init``, ``next``, ``check``, ``hint``, ``solve``, ``status``,
``reseed``) arrive with the grading engine.
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from lab import __version__
from lab.paths import (
    CORRECTIONS_DIR,
    DATA_DIR,
    EXERCISES_DIR,
    REPO_ROOT,
    STATE_DIR,
    WAREHOUSE_PATH,
)

app = typer.Typer(
    name="lab",
    help="Graded exercises for SQL (DuckDB), Pandas, NumPy and APIs.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"data-skills-lab {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Data Skills Lab."""


@app.command()
def info() -> None:
    """Show how the lab is wired up on this machine."""
    table = Table(title="Data Skills Lab", title_style="bold", header_style="bold")
    table.add_column("Item")
    table.add_column("Path or value")
    table.add_column("Status")

    table.add_row("version", __version__, "")
    table.add_row("python", f"{sys.version_info.major}.{sys.version_info.minor}", "")
    table.add_row("repo root", str(REPO_ROOT), "")

    for label, path in (
        ("exercises", EXERCISES_DIR),
        ("corrections", CORRECTIONS_DIR),
        ("data", DATA_DIR),
        ("warehouse", WAREHOUSE_PATH),
        ("session state", STATE_DIR),
    ):
        present = path.exists()
        table.add_row(
            label,
            str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
            "[green]found[/green]" if present else "[yellow]not yet created[/yellow]",
        )

    console.print(table)
    console.print(
        "\n[dim]Exercise commands (init, next, check, hint, solve, status) "
        "arrive with the grading engine.[/dim]"
    )

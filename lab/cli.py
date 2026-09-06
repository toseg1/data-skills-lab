"""Command line entry point.

``generate`` is the plumbing command: it builds a dataset from an explicit seed.
The learner-facing ``init``, which draws a seed, records it as your session and
then calls this, arrives with the grading engine — along with ``next``, ``check``,
``hint``, ``solve`` and ``status``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from lab import __version__
from lab.paths import (
    CORRECTIONS_DIR,
    DATA_DIR,
    EXERCISES_DIR,
    PARQUET_DIR,
    RAW_DIR,
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


def _display(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


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
        ("warehouse", WAREHOUSE_PATH),
        ("parquet", PARQUET_DIR),
        ("raw files", RAW_DIR),
        ("session state", STATE_DIR),
    ):
        table.add_row(
            label,
            _display(path),
            "[green]found[/green]" if path.exists() else "[yellow]not yet created[/yellow]",
        )

    console.print(table)
    console.print(
        "\n[dim]Exercise commands (init, next, check, hint, solve, status) "
        "arrive with the grading engine.[/dim]"
    )


@app.command()
def generate(
    seed: Annotated[int, typer.Option("--seed", "-s", help="Seed for the dataset.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Directory to write into.")] = DATA_DIR,
    days: Annotated[
        int | None, typer.Option("--days", help="Business days of history. Default 756.")
    ] = None,
    trades: Annotated[
        int | None, typer.Option("--trades", help="Number of trades. Default 25000.")
    ] = None,
) -> None:
    """Build the dataset from a seed and write it to disk.

    The same seed always produces the same data, so this is safe to re-run.
    """
    # Imported here rather than at module scope so `lab --version` stays instant.
    from lab.data import GeneratorConfig, generate_dataset, schema, write_all

    overrides = {}
    if days is not None:
        overrides["n_days"] = days
    if trades is not None:
        overrides["n_trades"] = trades

    try:
        config = GeneratorConfig(**overrides)
    except ValueError as exc:
        console.print(f"[red]Invalid configuration:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    with console.status(f"Generating dataset from seed {seed}..."):
        dataset = generate_dataset(seed, config)
        written = write_all(dataset, out)

    rows = Table(title=f"Dataset (seed {seed})", title_style="bold", header_style="bold")
    rows.add_column("Table")
    rows.add_column("Layer")
    rows.add_column("Rows", justify="right")
    for name, df in dataset.tables.items():
        rows.add_row(name, schema.TABLES[name].layer, f"{len(df):,}")
    console.print(rows)

    parquet_dir = _display(out / "parquet")
    raw_dir = _display(out / "raw")
    console.print(f"\n[green]Wrote[/green] {_display(written['duckdb'][0])}")
    console.print(f"[green]Wrote[/green] {len(written['parquet'])} Parquet files to {parquet_dir}")
    console.print(f"[green]Wrote[/green] {len(written['raw'])} raw files to {raw_dir}")

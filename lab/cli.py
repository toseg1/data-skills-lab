"""Command line entry point.

lab init          draw a seed and build your dataset
lab next          open the next unsolved exercise
lab check <sel>   grade one exercise, a section, or everything
lab hint <id>     reveal one more hint
lab solve <id>    show the reference answer (needs --yes)
lab status        progress across the path
lab reseed        new seed, new numbers, same exercises
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from lab import __version__
from lab.discovery import Exercise, discover, read_brief, select
from lab.grader import Result, grade
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
from lab.session import Session, SessionError, load_session, new_session, save_session
from lab.workspace import Workspace, WorkspaceError

app = typer.Typer(
    name="lab",
    help="Graded exercises for SQL (DuckDB), Pandas, NumPy and APIs.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

_STATUS_STYLE = {
    "passed": ("[green]pass[/green]", "green"),
    "failed": ("[red]fail[/red]", "red"),
    "not_started": ("[yellow]todo[/yellow]", "yellow"),
    "error": ("[red]error[/red]", "red"),
    "no_reference": ("[magenta]no reference[/magenta]", "magenta"),
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _display(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"data-skills-lab {__version__}")
        raise typer.Exit


def _require_session() -> Session:
    try:
        return load_session()
    except SessionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


def _require_workspace() -> Workspace:
    workspace = Workspace()
    try:
        workspace.require()
    except WorkspaceError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    return workspace


def _resolve(selector: str | None) -> list[Exercise]:
    exercises = discover()
    if not exercises:
        console.print("[yellow]No exercises found yet.[/yellow]")
        raise typer.Exit(code=1)
    chosen = select(exercises, selector)
    if not chosen:
        console.print(f"[red]Nothing matches {selector!r}.[/red] Try `lab status` to see the path.")
        raise typer.Exit(code=1)
    return chosen


def _build_dataset(seed: int, out: Path) -> None:
    from lab.data import generate_dataset, write_all

    with console.status(f"Building your dataset from seed {seed}..."):
        write_all(generate_dataset(seed), out)


def _render_result(result: Result) -> None:
    label, colour = _STATUS_STYLE[result.outcome]
    console.print(f"{label}  [bold]{result.exercise.id}[/bold]  {result.exercise.title}")

    if result.outcome == "passed":
        for note in result.comparison.notes if result.comparison else []:
            console.print(f"      [dim]{note}[/dim]")
        return

    if result.outcome == "not_started":
        console.print(f"      [dim]not attempted yet — {_display(result.exercise.path)}[/dim]")
        return

    if result.outcome in {"error", "no_reference"}:
        console.print(Panel(result.error or "", border_style=colour, title="error"))
        return

    comparison = result.comparison
    if comparison is None:
        return
    # The headline is the panel title, so it is not repeated in the body.
    body = "\n".join(comparison.details) or comparison.headline
    console.print(Panel(body, border_style=colour, title=comparison.headline, title_align="left"))
    for note in comparison.notes:
        console.print(f"      [dim]{note}[/dim]")
    console.print(f"      [dim]hint: lab hint {result.exercise.id}[/dim]")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


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

    try:
        seed = str(load_session().seed)
    except SessionError:
        seed = "[yellow]no session — run `lab init`[/yellow]"
    table.add_row("seed", seed, "")

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


@app.command()
def init(
    seed: Annotated[
        int | None, typer.Option("--seed", "-s", help="Use this seed instead of a random one.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Replace an existing session and its progress.")
    ] = False,
) -> None:
    """Draw a dataset seed, record it as your session, and build the data."""
    try:
        existing = load_session()
    except SessionError:
        existing = None

    if existing and not force:
        console.print(
            f"[yellow]You already have a session[/yellow] (seed {existing.seed}). "
            "Use `lab reseed` for fresh numbers, or `lab init --force` to start over "
            "and lose your progress."
        )
        raise typer.Exit(code=1)

    session = new_session(seed)
    save_session(session)
    _build_dataset(session.seed, DATA_DIR)

    console.print(f"\n[green]Ready.[/green] Your dataset seed is [bold]{session.seed}[/bold].")
    console.print("[dim]It is recorded in .lab/session.json and is not committed.[/dim]")
    console.print("\nStart with: [bold]lab next[/bold]")


@app.command()
def reseed(
    seed: Annotated[int | None, typer.Option("--seed", "-s", help="Use this seed.")] = None,
    reset_progress: Annotated[
        bool, typer.Option("--reset-progress", help="Also clear what you have solved.")
    ] = False,
) -> None:
    """Draw new numbers for the same exercises. Progress is kept unless you say otherwise."""
    session = _require_session()
    session.seed = seed if seed is not None else new_session().seed
    if reset_progress:
        session.progress.clear()
    save_session(session)
    _build_dataset(session.seed, DATA_DIR)
    console.print(f"\n[green]New seed:[/green] [bold]{session.seed}[/bold]")
    if not reset_progress:
        console.print("[dim]Progress kept. Re-run `lab check` to grade against the new data.[/dim]")


@app.command("next")
def next_exercise() -> None:
    """Show the next exercise you have not solved."""
    session = _require_session()
    for exercise in discover():
        if not session.is_passed(exercise.id):
            console.print(f"[bold]{exercise.id}[/bold]  —  {exercise.title}")
            console.print(f"[dim]{_display(exercise.path)}[/dim]\n")
            brief = read_brief(exercise)
            if brief:
                console.print(Panel(brief, border_style="blue", title="task", title_align="left"))
            console.print(f"\nWhen ready: [bold]lab check {exercise.id}[/bold]")
            return
    console.print("[green]Everything on the path is solved.[/green]")


@app.command()
def check(
    selector: Annotated[
        str | None,
        typer.Argument(help="An exercise id, a section, a track, or nothing for everything."),
    ] = None,
) -> None:
    """Grade your answers against the reference."""
    session = _require_session()
    exercises = _resolve(selector)
    workspace = _require_workspace()

    results: list[Result] = []
    try:
        for exercise in exercises:
            result = grade(exercise, workspace)
            results.append(result)
            session.record_attempt(exercise.id, passed=result.ok)
            _render_result(result)
    finally:
        workspace.close()
        save_session(session)

    passed = sum(r.ok for r in results)
    todo = sum(r.outcome == "not_started" for r in results)
    if len(results) > 1:
        console.print(
            f"\n[bold]{passed}/{len(results)} passed[/bold]"
            + (f", {todo} not started" if todo else "")
        )
    if any(r.outcome in {"failed", "error", "no_reference"} for r in results):
        raise typer.Exit(code=1)


@app.command()
def hint(
    exercise_id: Annotated[str, typer.Argument(help="Which exercise to get a hint for.")],
    reset: Annotated[
        bool, typer.Option("--reset", help="Start again from the first hint.")
    ] = False,
) -> None:
    """Reveal one more hint. Call it again for the next one."""
    session = _require_session()
    matches = _resolve(exercise_id)
    if len(matches) > 1:
        console.print(f"[yellow]{exercise_id!r} matches {len(matches)} exercises.[/yellow]")
        for match in matches[:10]:
            console.print(f"  {match.id}")
        raise typer.Exit(code=1)

    exercise = matches[0]
    hints = exercise.read_hints()
    if not hints:
        console.print(f"[yellow]No hints written for {exercise.id} yet.[/yellow]")
        raise typer.Exit(code=1)

    if reset:
        session.reset_hints(exercise.id)
    shown = session.next_hint(exercise.id, len(hints))
    save_session(session)

    console.print(
        Panel(
            hints[shown - 1],
            title=f"hint {shown} of {len(hints)} · {exercise.id}",
            title_align="left",
            border_style="blue",
        )
    )
    if shown < len(hints):
        console.print(f"[dim]Another one: lab hint {exercise.id}[/dim]")
    else:
        console.print(f"[dim]That was the last hint. lab solve {exercise.id} --yes[/dim]")


@app.command()
def solve(
    exercise_id: Annotated[str, typer.Argument(help="Which exercise to reveal.")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm you want the answer.")] = False,
) -> None:
    """Show the reference answer. Deliberately requires --yes."""
    matches = _resolve(exercise_id)
    if len(matches) > 1:
        console.print(f"[yellow]{exercise_id!r} matches {len(matches)} exercises.[/yellow]")
        raise typer.Exit(code=1)
    exercise = matches[0]

    if not yes:
        console.print(
            f"This prints the answer to [bold]{exercise.id}[/bold]. "
            f"Try [bold]lab hint {exercise.id}[/bold] first, or re-run with --yes."
        )
        raise typer.Exit(code=1)

    if not exercise.has_reference():
        console.print(f"[red]No reference for {exercise.id}.[/red]")
        raise typer.Exit(code=1)

    source = exercise.reference.read_text(encoding="utf-8")
    lexer = "python" if exercise.kind == "python" else "sql"
    console.print(
        Panel(
            Syntax(source.strip(), lexer, theme="ansi_dark", word_wrap=True),
            title=f"reference · {exercise.id}",
            title_align="left",
            border_style="magenta",
        )
    )


@app.command()
def status() -> None:
    """Progress across the whole path."""
    session = _require_session()
    exercises = discover()
    if not exercises:
        console.print("[yellow]No exercises found yet.[/yellow]")
        return

    table = Table(title=f"Progress (seed {session.seed})", title_style="bold", header_style="bold")
    table.add_column("Section")
    table.add_column("Solved", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("")

    sections: dict[str, list[Exercise]] = {}
    for exercise in exercises:
        sections.setdefault(exercise.section, []).append(exercise)

    total_done = 0
    for section, items in sections.items():
        done = sum(session.is_passed(e.id) for e in items)
        total_done += done
        filled = round(10 * done / len(items))
        bar = "█" * filled + "·" * (10 - filled)
        style = "green" if done == len(items) else "dim"
        table.add_row(section, str(done), str(len(items)), f"[{style}]{bar}[/{style}]")

    console.print(table)
    console.print(f"[bold]{total_done}/{len(exercises)}[/bold] solved overall")

    for exercise in exercises:
        if not session.is_passed(exercise.id):
            console.print(f"\nNext up: [bold]{exercise.id}[/bold] — {exercise.title}")
            break


@app.command()
def generate(
    seed: Annotated[int, typer.Option("--seed", "-s", help="Seed for the dataset.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Directory to write into.")] = DATA_DIR,
) -> None:
    """Build a dataset from an explicit seed, without touching your session.

    `lab init` is the normal way in; this is for inspecting a specific dataset.
    """
    from lab.data import generate_dataset, schema, write_all

    with console.status(f"Generating dataset from seed {seed}..."):
        dataset = generate_dataset(seed)
        written = write_all(dataset, out)

    rows = Table(title=f"Dataset (seed {seed})", title_style="bold", header_style="bold")
    rows.add_column("Table")
    rows.add_column("Layer")
    rows.add_column("Rows", justify="right")
    for name, df in dataset.tables.items():
        rows.add_row(name, schema.TABLES[name].layer, f"{len(df):,}")
    console.print(rows)
    console.print(f"\n[green]Wrote[/green] {_display(written['duckdb'][0])} and friends")

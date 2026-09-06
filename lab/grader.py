"""Running an exercise and its reference, then comparing the two.

No expected answers are stored anywhere. The reference implementation is executed
against the same dataset your code sees, in the same process, and the two results
are compared. That is what lets the dataset be unique to your clone.

A Python exercise declares its inputs by parameter name; a SQL exercise is a
single query run against the warehouse.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from lab.compare import Comparison, compare
from lab.discovery import Exercise
from lab.workspace import INPUT_NAMES, Workspace

__all__ = ["Result", "grade", "grade_all", "run_solution"]

Outcome = Literal["passed", "failed", "not_started", "error", "no_reference"]

MAX_TRACEBACK_LINES = 14

#: The marker an unattempted exercise raises. Kept distinct from a wrong answer
#: so `lab status` can tell "not started" from "not working yet".
_NOT_STARTED = NotImplementedError


@dataclass
class Result:
    exercise: Exercise
    outcome: Outcome
    comparison: Comparison | None = None
    error: str | None = None
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.outcome == "passed"


class ExerciseError(RuntimeError):
    """A problem with the exercise file itself rather than with the answer."""


def _load_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ExerciseError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution so dataclasses and pickling inside the module
    # can resolve it, then removed so repeated runs never see a stale copy.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def _call_solve(module: ModuleType, workspace: Workspace, where: Path) -> Any:
    solve = getattr(module, "solve", None)
    if solve is None or not callable(solve):
        raise ExerciseError(f"{where} defines no `solve` function")

    signature = inspect.signature(solve)
    unknown = [
        name
        for name, parameter in signature.parameters.items()
        if name not in INPUT_NAMES
        and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    if unknown:
        raise ExerciseError(
            f"{where}: `solve` asks for {unknown}, which the lab cannot supply. "
            f"Available inputs: {', '.join(sorted(INPUT_NAMES))}."
        )

    kwargs = {name: workspace.resolve(name) for name in signature.parameters}
    return solve(**kwargs)


def run_solution(path: Path, exercise: Exercise, workspace: Workspace, *, tag: str) -> Any:
    """Execute one exercise or reference file and return whatever it produced."""
    if exercise.kind == "sql":
        query = path.read_text(encoding="utf-8").strip()
        if not query or all(
            line.strip().startswith("--") or not line.strip() for line in query.splitlines()
        ):
            raise _NOT_STARTED("The query is empty")
        return workspace.sql(query)

    module_name = f"_lab_{tag}_{exercise.id.replace('/', '_')}"
    module = _load_module(path, module_name)
    return _call_solve(module, workspace, path)


def _format_error(exc: BaseException) -> str:
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    text = "".join(lines).rstrip().splitlines()
    if len(text) > MAX_TRACEBACK_LINES:
        text = ["  ... earlier frames hidden ...", *text[-MAX_TRACEBACK_LINES:]]
    return "\n".join(text)


def grade(exercise: Exercise, workspace: Workspace) -> Result:
    """Run one exercise against its reference."""
    started = time.perf_counter()

    if not exercise.has_reference():
        return Result(exercise, "no_reference", error=f"No reference at {exercise.reference}")

    try:
        actual = run_solution(exercise.path, exercise, workspace, tag="you")
    except _NOT_STARTED:
        return Result(exercise, "not_started", seconds=time.perf_counter() - started)
    except ExerciseError as exc:
        return Result(exercise, "error", error=str(exc), seconds=time.perf_counter() - started)
    except Exception as exc:
        return Result(
            exercise, "error", error=_format_error(exc), seconds=time.perf_counter() - started
        )

    try:
        expected = run_solution(exercise.reference, exercise, workspace, tag="ref")
    except Exception as exc:
        # The reference is our code, so this is a lab bug, not a learner mistake.
        return Result(
            exercise,
            "error",
            error=(
                "The reference implementation failed. This is a bug in the lab, "
                f"not a problem with your answer.\n{_format_error(exc)}"
            ),
            seconds=time.perf_counter() - started,
        )

    comparison = compare(
        actual,
        expected,
        ordered=exercise.ordered,
        rtol=exercise.rtol,
        atol=exercise.atol,
    )
    return Result(
        exercise,
        "passed" if comparison.ok else "failed",
        comparison=comparison,
        seconds=time.perf_counter() - started,
    )


def grade_all(exercises: list[Exercise], workspace: Workspace) -> list[Result]:
    return [grade(exercise, workspace) for exercise in exercises]

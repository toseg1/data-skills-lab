"""Finding exercises and pairing them with their references.

An exercise is a single file under ``exercises/``. Its id is the path relative to
that directory without the suffix, so ``exercises/sql/04_windows/07_lag.sql`` has
the id ``sql/04_windows/07_lag``. The reference lives at the mirrored path under
``.corrections/``, and optional hints sit beside it as ``<stem>.hints.md``.

Headers are parsed rather than executed: a title and grading options are read
statically, so listing exercises never runs anyone's code.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from lab.paths import CORRECTIONS_DIR, EXERCISES_DIR

__all__ = ["DiscoveryError", "Exercise", "discover", "read_brief", "select", "split_hints"]

Kind = Literal["python", "sql"]

_SUFFIXES: dict[str, Kind] = {".py": "python", ".sql": "sql"}
_META_LINE = re.compile(r"^\s*--\s*meta:\s*(.+)$", re.IGNORECASE)
_HINT_SEPARATOR = re.compile(r"^---\s*$", re.MULTILINE)


class DiscoveryError(RuntimeError):
    """Raised when the exercise tree is malformed."""


@dataclass(frozen=True)
class Exercise:
    id: str
    path: Path
    kind: Kind
    title: str
    reference: Path
    hints_path: Path | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def track(self) -> str:
        """Top-level directory: ``sql``, ``pandas``, ``numpy``, ``api``, ``00_setup``."""
        return self.id.split("/")[0]

    @property
    def section(self) -> str:
        parts = self.id.split("/")
        return "/".join(parts[:-1]) if len(parts) > 1 else parts[0]

    @property
    def ordered(self) -> bool:
        """Whether row order is part of the answer. Defaults to no."""
        return bool(self.meta.get("ordered", False))

    @property
    def rtol(self) -> float:
        return float(self.meta.get("rtol", 1e-7))

    @property
    def atol(self) -> float:
        return float(self.meta.get("atol", 1e-9))

    def has_reference(self) -> bool:
        return self.reference.is_file()

    def read_hints(self) -> list[str]:
        if self.hints_path is None or not self.hints_path.is_file():
            return []
        return split_hints(self.hints_path.read_text(encoding="utf-8"))


def split_hints(text: str) -> list[str]:
    """Hints are markdown sections separated by a line containing only ``---``."""
    return [chunk.strip() for chunk in _HINT_SEPARATOR.split(text) if chunk.strip()]


def _coerce(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value.strip()


def _parse_python_header(source: str) -> tuple[str, dict[str, Any]]:
    """Read the docstring title and a literal ``META`` dict without importing."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # A half-written exercise should still be listable; grading will report
        # the syntax error properly when it runs.
        return "", {}

    docstring = ast.get_docstring(tree) or ""
    title = docstring.strip().splitlines()[0].strip() if docstring.strip() else ""

    meta: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "META" for t in node.targets
        ):
            try:
                candidate = ast.literal_eval(node.value)
            except ValueError:
                continue
            if isinstance(candidate, dict):
                meta = {str(k): v for k, v in candidate.items()}
    return title, meta


def _parse_sql_header(source: str) -> tuple[str, dict[str, Any]]:
    title = ""
    meta: dict[str, Any] = {}
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("--"):
            break
        match = _META_LINE.match(stripped)
        if match:
            for pair in match.group(1).split(","):
                if "=" in pair:
                    key, _, value = pair.partition("=")
                    meta[key.strip()] = _coerce(value)
            continue
        if not title:
            title = stripped.lstrip("-").strip()
    return title, meta


def read_brief(exercise: Exercise) -> str:
    """The task text as written at the top of the file, for printing in a terminal."""
    source = exercise.path.read_text(encoding="utf-8")
    if exercise.kind == "python":
        try:
            return (ast.get_docstring(ast.parse(source)) or "").strip()
        except SyntaxError:
            return ""
    lines: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith("--"):
            if lines:
                break
            continue
        if _META_LINE.match(stripped):
            continue
        lines.append(stripped.lstrip("-").strip())
    return "\n".join(lines).strip()


def _build(path: Path, exercises_dir: Path, corrections_dir: Path) -> Exercise:
    relative = path.relative_to(exercises_dir)
    exercise_id = relative.with_suffix("").as_posix()
    kind = _SUFFIXES[path.suffix]
    source = path.read_text(encoding="utf-8")
    title, meta = _parse_python_header(source) if kind == "python" else _parse_sql_header(source)
    reference = corrections_dir / relative
    hints_path = reference.with_suffix(".hints.md")
    return Exercise(
        id=exercise_id,
        path=path,
        kind=kind,
        title=title or exercise_id,
        reference=reference,
        hints_path=hints_path if hints_path.is_file() else None,
        meta=meta,
    )


def discover(
    exercises_dir: Path | None = None, corrections_dir: Path | None = None
) -> list[Exercise]:
    """Every exercise on the path, in the order it should be worked through."""
    exercises_dir = exercises_dir or EXERCISES_DIR
    corrections_dir = corrections_dir or CORRECTIONS_DIR
    if not exercises_dir.is_dir():
        raise DiscoveryError(f"No exercises directory at {exercises_dir}")

    found = [
        p
        for p in exercises_dir.rglob("*")
        if p.is_file()
        and p.suffix in _SUFFIXES
        and not p.name.startswith(("_", "."))
        and "__pycache__" not in p.parts
    ]
    return sorted(
        (_build(p, exercises_dir, corrections_dir) for p in found),
        key=lambda e: e.id,
    )


def select(exercises: list[Exercise], selector: str | None) -> list[Exercise]:
    """Resolve a selector to exercises, from most to least specific.

    ``lab check sql`` takes a whole track, ``sql/04`` a section, and a full id a
    single exercise. A bare fragment matches anywhere in the path.
    """
    if not selector:
        return list(exercises)

    needle = selector.strip().strip("/")
    for candidates in (
        [e for e in exercises if e.id == needle],
        [e for e in exercises if e.id.startswith(needle)],
        [e for e in exercises if needle in e.id],
    ):
        if candidates:
            return candidates
    return []

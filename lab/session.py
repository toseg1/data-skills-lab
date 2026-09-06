"""Per-learner state: the dataset seed and your progress through the path.

Lives in a gitignored ``.lab/session.json``, so it never travels with the repo.
The seed is the important part — it decides which dataset you get, and therefore
what every reference implementation is graded against.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from lab import __version__
from lab.paths import STATE_DIR

__all__ = ["Progress", "Session", "SessionError", "draw_seed", "load_session", "save_session"]

Status = Literal["passed", "attempted"]

SESSION_FILENAME = "session.json"


class SessionError(RuntimeError):
    """Raised when the session is missing or unreadable."""


def draw_seed() -> int:
    """A fresh dataset seed. Large enough that two learners will not collide."""
    return secrets.randbelow(2**31 - 1) + 1


@dataclass
class Progress:
    """What has happened on one exercise."""

    status: Status = "attempted"
    attempts: int = 0
    hints_shown: int = 0
    solved_at: str | None = None


@dataclass
class Session:
    seed: int
    created_at: str
    lab_version: str = __version__
    progress: dict[str, Progress] = field(default_factory=dict)

    # -- progress helpers -------------------------------------------------- #

    def entry(self, exercise_id: str) -> Progress:
        return self.progress.setdefault(exercise_id, Progress())

    def record_attempt(self, exercise_id: str, *, passed: bool) -> Progress:
        item = self.entry(exercise_id)
        item.attempts += 1
        if passed:
            item.status = "passed"
            item.solved_at = item.solved_at or _now()
        return item

    def next_hint(self, exercise_id: str, available: int) -> int:
        """Reveal one more hint and return how many are now visible."""
        item = self.entry(exercise_id)
        item.hints_shown = min(item.hints_shown + 1, available)
        return item.hints_shown

    def reset_hints(self, exercise_id: str) -> None:
        self.entry(exercise_id).hints_shown = 0

    def is_passed(self, exercise_id: str) -> bool:
        return exercise_id in self.progress and self.progress[exercise_id].status == "passed"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def session_path(state_dir: Path | None = None) -> Path:
    return (state_dir or STATE_DIR) / SESSION_FILENAME


def new_session(seed: int | None = None) -> Session:
    return Session(seed=seed if seed is not None else draw_seed(), created_at=_now())


def save_session(session: Session, state_dir: Path | None = None) -> Path:
    path = session_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "seed": session.seed,
        "created_at": session.created_at,
        "lab_version": session.lab_version,
        "progress": {k: asdict(v) for k, v in sorted(session.progress.items())},
    }
    # Written whole rather than appended, so a half-finished write cannot leave
    # a session file that parses but lies about your progress.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def load_session(state_dir: Path | None = None) -> Session:
    path = session_path(state_dir)
    if not path.is_file():
        raise SessionError("No session yet. Run `lab init` to draw a seed and build your dataset.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SessionError(f"{path} is not valid JSON. Delete it and run `lab init`.") from exc

    try:
        progress = {k: Progress(**v) for k, v in raw.get("progress", {}).items()}
        return Session(
            seed=int(raw["seed"]),
            created_at=raw.get("created_at", _now()),
            lab_version=raw.get("lab_version", "unknown"),
            progress=progress,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SessionError(f"{path} is missing fields. Delete it and run `lab init`.") from exc

"""A miniature lab on disk, so the engine can be tested without the real exercises.

Builds a tiny dataset and a handful of exercises covering every outcome the
grader has to report — correct, wrong, unattempted, broken, and SQL — then points
the lab's directory constants at it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lab.data import GeneratorConfig, generate_dataset, write_all
from lab.session import new_session, save_session

TINY = GeneratorConfig(
    n_clients=6,
    n_securities=5,
    n_days=30,
    n_trades=120,
    min_tickers_per_client=2,
    max_tickers_per_client=3,
    n_orders_json=5,
)

SEED = 12345

_FILES: dict[str, str] = {
    # id -> (exercise source, reference source)
    "demo/01_scalar.py": '''"""Count the trades

TASK
    Return the number of rows in trades.
"""

def solve(trades):
    return len(trades)
''',
    "demo/02_frame.py": '''"""Notional per side

TASK
    Total notional per side.
"""

def solve(trades):
    out = trades.copy()
    out["notional"] = out["quantity"] * out["price"]
    # Deliberately wrong: sums quantity instead of notional.
    return out.groupby("side", as_index=False)["quantity"].sum().rename(
        columns={"quantity": "notional"}
    )
''',
    "demo/03_stub.py": '''"""Not attempted yet

TASK
    Return anything.
"""

def solve(trades):
    raise NotImplementedError("Replace this line with your answer.")
''',
    "demo/04_broken.py": '''"""Raises

TASK
    Return anything.
"""

def solve(trades):
    return 1 / 0
''',
    "demo/05_query.sql": "SELECT side, COUNT(*) AS n FROM trades GROUP BY side\n",
}

_REFERENCES: dict[str, str] = {
    "demo/01_scalar.py": '''"""Reference"""

def solve(trades):
    return len(trades)
''',
    "demo/02_frame.py": '''"""Reference"""

def solve(trades):
    out = trades.copy()
    out["notional"] = out["quantity"] * out["price"]
    return out.groupby("side", as_index=False)["notional"].sum()
''',
    "demo/03_stub.py": '''"""Reference"""

def solve(trades):
    return len(trades)
''',
    "demo/04_broken.py": '''"""Reference"""

def solve(trades):
    return len(trades)
''',
    "demo/05_query.sql": "SELECT side, COUNT(*) AS n FROM trades GROUP BY side\n",
}


@pytest.fixture(scope="session")
def tiny_dataset_dir(tmp_path_factory) -> Path:
    """A small dataset written once and shared by every test that needs one."""
    out = tmp_path_factory.mktemp("tiny-data")
    write_all(generate_dataset(SEED, TINY), out)
    return out


@pytest.fixture
def mini_lab(tmp_path, tiny_dataset_dir, monkeypatch) -> SimpleNamespace:
    """Point the lab's directories at a throwaway tree and return the pieces."""
    exercises = tmp_path / "exercises"
    corrections = tmp_path / ".corrections"
    state = tmp_path / ".lab"

    for rel, source in _FILES.items():
        path = exercises / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    for rel, source in _REFERENCES.items():
        path = corrections / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    (corrections / "demo" / "01_scalar.hints.md").write_text(
        "First hint.\n\n---\n\nSecond hint.\n", encoding="utf-8"
    )

    import lab.cli
    import lab.discovery
    import lab.session
    import lab.workspace

    monkeypatch.setattr(lab.discovery, "EXERCISES_DIR", exercises)
    monkeypatch.setattr(lab.discovery, "CORRECTIONS_DIR", corrections)
    monkeypatch.setattr(lab.session, "STATE_DIR", state)
    monkeypatch.setattr(lab.workspace, "DATA_DIR", tiny_dataset_dir)
    monkeypatch.setattr(lab.cli, "DATA_DIR", tiny_dataset_dir)

    save_session(new_session(SEED), state)

    return SimpleNamespace(
        root=tmp_path,
        exercises=exercises,
        corrections=corrections,
        state=state,
        data=tiny_dataset_dir,
        seed=SEED,
    )

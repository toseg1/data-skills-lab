"""Access to the generated dataset while grading.

An exercise declares what it needs by naming its parameters:

    def solve(trades, prices):
        ...

The runner reads the signature and supplies exactly those. That keeps exercise
files free of boilerplate and makes the dependency obvious at a glance.

Available names are the five curated tables plus ``con``, a read-only DuckDB
connection, and ``raw_dir`` for the exercises that read vendor files directly.
Tables are loaded once per run and shared between your solution and the
reference, so both are graded against byte-identical inputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from lab.paths import DATA_DIR

__all__ = ["TABLE_NAMES", "Workspace", "WorkspaceError"]

TABLE_NAMES: tuple[str, ...] = ("clients", "securities", "prices", "trades", "positions")

#: Everything an exercise may name as a parameter.
INPUT_NAMES: frozenset[str] = frozenset({*TABLE_NAMES, "con", "raw_dir", "parquet_dir"})


class WorkspaceError(RuntimeError):
    """Raised when the dataset is missing or an exercise asks for something unknown."""


class Workspace:
    """Lazily loads the dataset and hands pieces of it to exercises."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or DATA_DIR
        self.parquet_dir = self.data_dir / "parquet"
        self.raw_dir = self.data_dir / "raw"
        self.warehouse_path = self.data_dir / "warehouse.duckdb"
        self._tables: dict[str, pd.DataFrame] = {}
        self._con: duckdb.DuckDBPyConnection | None = None

    # -- availability ------------------------------------------------------ #

    def exists(self) -> bool:
        return self.warehouse_path.is_file() and self.parquet_dir.is_dir()

    def require(self) -> None:
        if not self.exists():
            raise WorkspaceError("No dataset found. Run `lab init` to draw a seed and build one.")

    # -- inputs ------------------------------------------------------------ #

    def table(self, name: str) -> pd.DataFrame:
        """Return a table. A fresh copy each time, so one exercise cannot
        mutate the data another is graded against."""
        if name not in TABLE_NAMES:
            raise WorkspaceError(f"Unknown table {name!r}")
        if name not in self._tables:
            path = self.parquet_dir / f"{name}.parquet"
            if not path.is_file():
                raise WorkspaceError(f"Missing {path}. Run `lab init` to rebuild the dataset.")
            self._tables[name] = pd.read_parquet(path)
        return self._tables[name].copy(deep=True)

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """A read-only DuckDB connection to the warehouse."""
        if self._con is None:
            self.require()
            self._con = duckdb.connect(str(self.warehouse_path), read_only=True)
        return self._con

    def sql(self, query: str) -> pd.DataFrame:
        """Run a query and return the result as a DataFrame.

        Each call uses its own cursor so a query cannot disturb another's state.
        """
        return self.connection.cursor().execute(query).fetchdf()

    def resolve(self, name: str) -> Any:
        """Map a parameter name to the thing it asks for."""
        if name in TABLE_NAMES:
            return self.table(name)
        if name == "con":
            return self.connection.cursor()
        if name == "raw_dir":
            return self.raw_dir
        if name == "parquet_dir":
            return self.parquet_dir
        raise WorkspaceError(
            f"Exercise asked for {name!r}, which is not available. "
            f"Choose from: {', '.join(sorted(INPUT_NAMES))}."
        )

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None
        self._tables.clear()

    def __enter__(self) -> Workspace:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

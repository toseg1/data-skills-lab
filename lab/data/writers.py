"""Materialise a generated dataset to disk.

Three outputs, each earning its place:

* **DuckDB** (``data/warehouse.duckdb``) — what the SQL track queries. Tables are
  created from the schema DDL and rows inserted with explicit casts, so warehouse
  types match the declaration rather than whatever pandas happened to infer. That
  matters: a date column arriving as `TIMESTAMP` would quietly change what
  `DATE_TRUNC` returns.
* **Parquet** (``data/parquet/``) — what the Pandas and NumPy tracks load.
* **Raw files** (``data/raw/``) — messy CSVs and a nested JSON order feed, for the
  exercises that read files directly rather than tables.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from lab.data import schema
from lab.data.generate import Dataset

__all__ = ["write_all", "write_duckdb", "write_parquet", "write_raw_files"]


def write_parquet(dataset: Dataset, out_dir: Path) -> list[Path]:
    """Write every table as Parquet. Returns the paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, df in dataset.tables.items():
        path = out_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        written.append(path)
    return written


def write_duckdb(dataset: Dataset, path: Path) -> Path:
    """Build the warehouse from scratch at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)

    con = duckdb.connect(str(path))
    try:
        for name, df in dataset.tables.items():
            table = schema.TABLES[name]
            con.execute(schema.create_table_sql(table))
            con.register("_source", df)
            columns = ", ".join(
                f"CAST({c.name} AS {c.duckdb_type}) AS {c.name}" for c in table.columns
            )
            con.execute(f"INSERT INTO {table.name} SELECT {columns} FROM _source")
            con.unregister("_source")

        # A view the exercises lean on constantly, and a fair thing to hand over:
        # trades already joined to their instrument reference data.
        con.execute(
            """
            CREATE OR REPLACE VIEW trades_enriched AS
            SELECT t.*, s.security_name, s.sector, s.exchange, s.currency,
                   t.quantity * t.price AS notional
            FROM trades t
            LEFT JOIN securities s USING (ticker)
            """
        )
    finally:
        con.close()
    return path


def write_raw_files(dataset: Dataset, out_dir: Path) -> list[Path]:
    """Write the messy CSVs and the nested JSON order feed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    raw = dataset.trades_raw.copy()
    # Split by delivery month so the file-globbing exercises have several files.
    parsed = pd.to_datetime(raw["trade_date"], format="mixed", dayfirst=False, errors="coerce")
    raw = raw.assign(_month=parsed.dt.strftime("%Y-%m"))
    months = sorted(m for m in raw["_month"].dropna().unique())[:3]
    for month in months:
        chunk = raw.loc[raw["_month"] == month].drop(columns="_month")
        path = out_dir / f"trades_{month}.csv"
        chunk.to_csv(path, index=False)
        written.append(path)

    clients_path = out_dir / "clients.csv"
    dataset.clients_raw.to_csv(clients_path, index=False)
    written.append(clients_path)

    orders_path = out_dir / "orders.json"
    orders_path.write_text(json.dumps(dataset.orders_json, indent=2), encoding="utf-8")
    written.append(orders_path)

    return written


def write_all(dataset: Dataset, data_dir: Path) -> dict[str, list[Path]]:
    """Write every artefact under ``data_dir`` and report what was produced."""
    warehouse = write_duckdb(dataset, data_dir / "warehouse.duckdb")
    return {
        "duckdb": [warehouse],
        "parquet": write_parquet(dataset, data_dir / "parquet"),
        "raw": write_raw_files(dataset, data_dir / "raw"),
    }

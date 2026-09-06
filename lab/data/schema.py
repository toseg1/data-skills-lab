"""Table definitions for the Northwind Capital dataset.

The schema is declared once here and used three ways: to coerce generated frames
to stable dtypes, to emit `CREATE TABLE` DDL for DuckDB, and to let tests assert
that what the generator produced matches what was promised.

## Two layers

**Curated** tables (`clients`, `securities`, `prices`, `trades`, `positions`) are
tidy. They still contain *legitimate* nulls — a client with no onboarding date, a
trade with no commission booked, a price series with holiday gaps — because
handling those is real work that the exercises ask for. What they do not contain
is corruption.

**Raw** tables (`clients_raw`, `trades_raw`) are what a vendor actually delivers:
every column typed as text, duplicated rows, padded strings, inconsistent casing,
mixed date formats, thousands separators. They exist so the cleaning exercises
have something honest to clean, and so the data-engineering track has a real
raw-to-curated load to build.

Exercises use the curated tables unless they say otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

__all__ = [
    "CURATED_TABLES",
    "RAW_TABLES",
    "TABLES",
    "Column",
    "Table",
    "coerce",
    "create_table_sql",
]


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    pandas_dtype: str
    duckdb_type: str
    nullable: bool = False
    description: str = ""


@dataclass(frozen=True, slots=True)
class Table:
    name: str
    layer: Literal["curated", "raw"]
    grain: str
    columns: tuple[Column, ...]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def column(self, name: str) -> Column:
        for col in self.columns:
            if col.name == name:
                return col
        raise KeyError(f"{self.name} has no column {name!r}")


_STR = ("string", "VARCHAR")
_DATE = ("datetime64[ns]", "DATE")
_INT = ("int64", "BIGINT")
_FLOAT = ("float64", "DOUBLE")


def _col(name: str, kind: tuple[str, str], *, null: bool = False, desc: str = "") -> Column:
    return Column(name, kind[0], kind[1], nullable=null, description=desc)


CLIENTS = Table(
    name="clients",
    layer="curated",
    grain="One client of the firm",
    columns=(
        _col("client_id", _STR, desc="Primary key, C001 upwards"),
        _col("client_name", _STR),
        _col("country", _STR, desc="ISO 3166-1 alpha-2"),
        _col("segment", _STR, desc="Institutional, Private or Wholesale"),
        _col("onboard_date", _DATE, null=True, desc="Null for a few legacy clients"),
        _col("aum_usd", _FLOAT, desc="Assets under management in USD"),
    ),
)

SECURITIES = Table(
    name="securities",
    layer="curated",
    grain="One tradable instrument",
    columns=(
        _col("ticker", _STR, desc="Primary key"),
        _col("security_name", _STR),
        _col("sector", _STR),
        _col("exchange", _STR),
        _col("currency", _STR),
    ),
)

PRICES = Table(
    name="prices",
    layer="curated",
    grain="One ticker on one business day",
    columns=(
        _col("price_date", _DATE),
        _col("ticker", _STR),
        _col("open_px", _FLOAT),
        _col("high_px", _FLOAT),
        _col("low_px", _FLOAT),
        _col("close_px", _FLOAT, null=True, desc="Null where the vendor sent no print"),
        _col("volume", _INT),
    ),
)

TRADES = Table(
    name="trades",
    layer="curated",
    grain="One executed order",
    columns=(
        _col("trade_id", _STR, desc="Primary key, T10001 upwards"),
        _col("trade_date", _DATE),
        _col("client_id", _STR),
        _col("ticker", _STR),
        _col("side", _STR, desc="BUY or SELL"),
        _col("quantity", _INT, desc="Always positive; direction lives in side"),
        _col("price", _FLOAT, desc="Execution price, near that day's close"),
        _col("commission", _FLOAT, null=True, desc="Null where none was booked"),
    ),
)

POSITIONS = Table(
    name="positions",
    layer="curated",
    grain="One client's holding in one ticker on one day",
    columns=(
        _col("as_of_date", _DATE),
        _col("client_id", _STR),
        _col("ticker", _STR),
        _col("quantity", _INT, desc="Signed; zero rows mark closed-out holdings"),
        _col("avg_cost", _FLOAT, desc="Running average cost of the buys to date"),
        _col("market_value", _FLOAT),
    ),
)

CLIENTS_RAW = Table(
    name="clients_raw",
    layer="raw",
    grain="One client, as delivered by the vendor feed",
    columns=(
        _col("client_id", _STR),
        _col("client_name", _STR, desc="Padded and inconsistently cased"),
        _col("country", _STR, desc="Mixed case: FR, fr, Fr"),
        _col("segment", _STR),
        _col("onboard_date", _STR, null=True, desc="Mixed formats, some empty"),
        _col("aum_usd", _STR, desc="Text with thousands separators"),
    ),
)

TRADES_RAW = Table(
    name="trades_raw",
    layer="raw",
    grain="One order line, as delivered by the vendor feed",
    columns=(
        _col("trade_id", _STR, desc="Not unique: the feed repeats rows"),
        _col("trade_date", _STR, desc="Mixed formats"),
        _col("client_id", _STR),
        _col("ticker", _STR, desc="Inconsistently cased"),
        _col("side", _STR, desc="BUY/SELL/B/S"),
        _col("quantity", _STR, desc="Text; a few are negative"),
        _col("price", _STR),
        _col("commission", _STR, null=True),
    ),
)

CURATED_TABLES: tuple[Table, ...] = (CLIENTS, SECURITIES, PRICES, TRADES, POSITIONS)
RAW_TABLES: tuple[Table, ...] = (CLIENTS_RAW, TRADES_RAW)
TABLES: dict[str, Table] = {t.name: t for t in (*CURATED_TABLES, *RAW_TABLES)}


def coerce(df: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Return ``df`` with the table's columns, in order, at the declared dtypes.

    Raises if a column is missing, so a generator bug surfaces here rather than
    three steps later inside a comparison.
    """
    missing = [c.name for c in table.columns if c.name not in df.columns]
    if missing:
        raise ValueError(f"{table.name} is missing columns: {missing}")

    out = df.loc[:, table.column_names].copy()
    for col in table.columns:
        out[col.name] = out[col.name].astype(col.pandas_dtype)
    return out.reset_index(drop=True)


def create_table_sql(table: Table) -> str:
    """Emit the DuckDB DDL for a table, so warehouse types match the schema."""
    body = ",\n".join(
        f"    {c.name} {c.duckdb_type}{'' if c.nullable else ' NOT NULL'}" for c in table.columns
    )
    return f"CREATE OR REPLACE TABLE {table.name} (\n{body}\n)"

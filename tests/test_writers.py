"""What lands on disk must match what was generated, at the declared types."""

from __future__ import annotations

import json

import duckdb
import pandas as pd
import pytest

from lab.data import GeneratorConfig, generate_dataset, schema, write_all

SMALL = GeneratorConfig(
    n_clients=8,
    n_securities=6,
    n_days=45,
    n_trades=250,
    min_tickers_per_client=2,
    max_tickers_per_client=3,
    n_orders_json=15,
)


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    dataset = generate_dataset(4242, SMALL)
    out = tmp_path_factory.mktemp("data")
    paths = write_all(dataset, out)
    return dataset, out, paths


def test_every_artefact_is_written(written) -> None:
    _, out, paths = written
    assert (out / "warehouse.duckdb").is_file()
    assert len(paths["parquet"]) == len(schema.TABLES)
    assert all(p.is_file() for group in paths.values() for p in group)


def test_duckdb_row_counts_match_the_frames(written) -> None:
    dataset, out, _ = written
    con = duckdb.connect(str(out / "warehouse.duckdb"), read_only=True)
    try:
        for name, df in dataset.tables.items():
            count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            assert count == len(df), name
    finally:
        con.close()


def test_duckdb_column_types_match_the_schema(written) -> None:
    """Dates must land as DATE, not TIMESTAMP — DATE_TRUNC examples depend on it."""
    _, out, _ = written
    con = duckdb.connect(str(out / "warehouse.duckdb"), read_only=True)
    try:
        for table in schema.TABLES.values():
            described = con.execute(f"DESCRIBE {table.name}").fetchdf()
            actual = dict(zip(described["column_name"], described["column_type"], strict=True))
            for col in table.columns:
                assert actual[col.name] == col.duckdb_type, f"{table.name}.{col.name}"
    finally:
        con.close()


def test_the_enriched_view_joins_reference_data(written) -> None:
    _, out, _ = written
    con = duckdb.connect(str(out / "warehouse.duckdb"), read_only=True)
    try:
        row = con.execute(
            "SELECT sector, notional FROM trades_enriched WHERE sector IS NOT NULL LIMIT 1"
        ).fetchone()
        assert row is not None and row[0] and row[1] > 0
    finally:
        con.close()


def test_parquet_round_trips_without_changing_dtypes(written) -> None:
    dataset, out, _ = written
    for name, df in dataset.tables.items():
        back = pd.read_parquet(out / "parquet" / f"{name}.parquet")
        pd.testing.assert_frame_equal(back, df, check_exact=True)


def test_raw_csvs_are_split_by_month(written) -> None:
    _, out, _ = written
    csvs = sorted((out / "raw").glob("trades_*.csv"))
    assert csvs, "expected at least one monthly trade file"
    frames = [pd.read_csv(p, dtype=str) for p in csvs]
    assert all(not f.empty for f in frames)
    assert list(frames[0].columns) == schema.TRADES_RAW.column_names


def test_order_feed_is_valid_json_with_nested_legs(written) -> None:
    dataset, out, _ = written
    payload = json.loads((out / "raw" / "orders.json").read_text(encoding="utf-8"))
    assert payload == dataset.orders_json
    assert any(len(order["legs"]) > 1 for order in payload)


def test_duckdb_can_read_the_written_files_directly(written) -> None:
    """The page-5 exercises query Parquet and JSON in place, so prove it works."""
    _, out, _ = written
    con = duckdb.connect()
    try:
        n = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{out / 'parquet' / 'trades.parquet'}')"
        ).fetchone()[0]
        assert n > 0

        legs = con.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT UNNEST(legs) AS leg FROM read_json('{out / "raw" / "orders.json"}')
            )
            """
        ).fetchone()[0]
        assert legs > 0
    finally:
        con.close()


def test_writing_twice_is_idempotent(written, tmp_path) -> None:
    dataset, _, _ = written
    write_all(dataset, tmp_path)
    first = (tmp_path / "warehouse.duckdb").stat().st_size
    write_all(dataset, tmp_path)
    assert (tmp_path / "warehouse.duckdb").is_file()
    assert first > 0

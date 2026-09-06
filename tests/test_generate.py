"""The generator's contract: deterministic, well-typed, and internally consistent.

These use a deliberately small config. The properties under test do not depend on
size, and a fast suite is one you actually run.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from lab.data import GeneratorConfig, generate_dataset, schema

SEED = 20250906

SMALL = GeneratorConfig(
    n_clients=12,
    n_securities=10,
    n_days=90,
    n_trades=600,
    min_tickers_per_client=2,
    max_tickers_per_client=4,
    n_orders_json=25,
)


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SEED, SMALL)


# --------------------------------------------------------------------------- #
# Determinism — the property the whole grading model rests on
# --------------------------------------------------------------------------- #


def test_same_seed_reproduces_every_table(dataset) -> None:
    again = generate_dataset(SEED, SMALL)
    for name, df in dataset.tables.items():
        pd.testing.assert_frame_equal(df, again.tables[name], check_exact=True)


def test_same_seed_reproduces_the_json_feed(dataset) -> None:
    assert generate_dataset(SEED, SMALL).orders_json == dataset.orders_json


def test_a_different_seed_changes_the_numbers(dataset) -> None:
    other = generate_dataset(SEED + 1, SMALL)
    assert not other.prices["close_px"].equals(dataset.prices["close_px"])
    assert not other.trades["quantity"].equals(dataset.trades["quantity"])


def test_streams_are_independent(dataset) -> None:
    """Changing trade count must not disturb the price series.

    Each table draws from its own derived stream precisely so that adding or
    resizing one part of the dataset does not silently re-roll another.
    """
    more_trades = generate_dataset(SEED, replace(SMALL, n_trades=900))
    pd.testing.assert_frame_equal(dataset.prices, more_trades.prices, check_exact=True)


# --------------------------------------------------------------------------- #
# Schema conformance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("table_name", sorted(schema.TABLES))
def test_columns_and_dtypes_match_the_schema(dataset, table_name) -> None:
    table = schema.TABLES[table_name]
    df = dataset.tables[table_name]
    assert df.columns.tolist() == table.column_names
    for col in table.columns:
        assert str(df[col.name].dtype) == col.pandas_dtype, col.name


@pytest.mark.parametrize("table_name", sorted(schema.TABLES))
def test_non_nullable_columns_hold_no_nulls(dataset, table_name) -> None:
    table = schema.TABLES[table_name]
    df = dataset.tables[table_name]
    for col in table.columns:
        if not col.nullable:
            assert df[col.name].notna().all(), f"{table_name}.{col.name}"


def test_row_counts_track_the_config(dataset) -> None:
    assert len(dataset.clients) == SMALL.n_clients
    assert len(dataset.securities) == SMALL.n_securities
    assert len(dataset.trades) == SMALL.n_trades
    # Prices lose about 1% of rows to simulated vendor gaps.
    full_grid = SMALL.n_days * SMALL.n_securities
    assert 0.95 * full_grid <= len(dataset.prices) <= full_grid


# --------------------------------------------------------------------------- #
# Referential integrity
# --------------------------------------------------------------------------- #


def test_primary_keys_are_unique(dataset) -> None:
    assert dataset.clients["client_id"].is_unique
    assert dataset.securities["ticker"].is_unique
    assert dataset.trades["trade_id"].is_unique
    assert not dataset.prices.duplicated(subset=["price_date", "ticker"]).any()
    assert not dataset.positions.duplicated(subset=["as_of_date", "client_id", "ticker"]).any()


def test_foreign_keys_resolve(dataset) -> None:
    clients = set(dataset.clients["client_id"])
    tickers = set(dataset.securities["ticker"])
    for frame, cols in (
        (dataset.trades, ("client_id", "ticker")),
        (dataset.positions, ("client_id", "ticker")),
    ):
        assert set(frame[cols[0]]) <= clients
        assert set(frame[cols[1]]) <= tickers
    assert set(dataset.prices["ticker"]) <= tickers


def test_dates_fall_on_business_days_inside_the_calendar(dataset) -> None:
    calendar = pd.bdate_range(SMALL.start_date, periods=SMALL.n_days)
    for frame, col in (
        (dataset.prices, "price_date"),
        (dataset.trades, "trade_date"),
        (dataset.positions, "as_of_date"),
    ):
        assert frame[col].isin(calendar).all(), col


# --------------------------------------------------------------------------- #
# Internal consistency — the part that makes the data usable for teaching
# --------------------------------------------------------------------------- #


def test_positions_reconcile_to_trades(dataset) -> None:
    """Holdings on the last day equal the cumulative signed quantity traded."""
    trades = dataset.trades
    signed = np.where(trades["side"] == "BUY", trades["quantity"], -trades["quantity"])
    expected = (
        trades.assign(signed=signed)
        .groupby(["client_id", "ticker"], observed=True)["signed"]
        .sum()
        .sort_index()
    )

    last_day = dataset.positions["as_of_date"].max()
    actual = (
        dataset.positions.loc[dataset.positions["as_of_date"] == last_day]
        .set_index(["client_id", "ticker"])["quantity"]
        .sort_index()
    )
    pd.testing.assert_series_equal(
        actual, expected, check_names=False, check_dtype=False, check_index_type=False
    )


def test_a_client_never_sells_more_than_it_holds(dataset) -> None:
    assert (dataset.positions["quantity"] >= 0).all()


def test_trade_quantities_are_positive_and_direction_lives_in_side(dataset) -> None:
    assert (dataset.trades["quantity"] > 0).all()
    assert set(dataset.trades["side"]) == {"BUY", "SELL"}


def test_average_cost_is_positive_wherever_a_holding_exists(dataset) -> None:
    assert (dataset.positions["avg_cost"] > 0).all()


def test_ohlc_bars_are_coherent(dataset) -> None:
    px = dataset.prices.dropna(subset=["close_px"])
    assert (px["high_px"] >= px[["open_px", "close_px"]].max(axis=1) - 1e-9).all()
    assert (px["low_px"] <= px[["open_px", "close_px"]].min(axis=1) + 1e-9).all()
    assert (px[["open_px", "high_px", "low_px", "close_px"]] > 0).all().all()
    assert (dataset.prices["volume"] > 0).all()


def test_sector_correlation_is_real(dataset) -> None:
    """Same-sector tickers should co-move more than cross-sector ones.

    Guards the factor model: if the sector term were dropped, this fails.
    """
    wide = dataset.prices.pivot(index="price_date", columns="ticker", values="close_px")
    returns = np.log(wide).diff().dropna()
    corr = returns.corr()
    sector_of = dataset.securities.set_index("ticker")["sector"].to_dict()

    same, cross = [], []
    for a in corr.columns:
        for b in corr.columns:
            if a < b:
                (same if sector_of[a] == sector_of[b] else cross).append(corr.loc[a, b])

    assert same, "expected at least one same-sector pair in the test universe"
    assert np.mean(same) > np.mean(cross)


# --------------------------------------------------------------------------- #
# Imperfections — the exercises depend on these existing
# --------------------------------------------------------------------------- #


def test_curated_tables_carry_legitimate_nulls(dataset) -> None:
    assert dataset.clients["onboard_date"].isna().any()
    assert dataset.trades["commission"].isna().any()
    assert dataset.prices["close_px"].isna().any()


def test_the_notion_example_client_has_no_onboarding_date(dataset) -> None:
    """C004 is documented as missing on the hub page; keep the two in step."""
    c004 = dataset.clients.loc[dataset.clients["client_id"] == "C004"].iloc[0]
    assert pd.isna(c004["onboard_date"])


def test_price_series_have_gaps_to_forward_fill(dataset) -> None:
    calendar = pd.bdate_range(SMALL.start_date, periods=SMALL.n_days)
    counts = dataset.prices.groupby("ticker", observed=True).size()
    assert (counts < len(calendar)).any()


def test_raw_feeds_are_dirty_in_the_documented_ways(dataset) -> None:
    raw_trades = dataset.trades_raw
    raw_clients = dataset.clients_raw

    assert raw_trades.duplicated().any(), "the vendor feed should repeat rows"
    assert not raw_trades["trade_id"].is_unique
    assert raw_clients["client_name"].str.strip().ne(raw_clients["client_name"]).any()
    assert raw_clients["country"].nunique() > raw_clients["country"].str.upper().nunique()
    assert (raw_clients["onboard_date"] == "").any()
    assert raw_clients["aum_usd"].str.contains(",").any()


def test_raw_tables_are_entirely_text(dataset) -> None:
    for table in schema.RAW_TABLES:
        df = dataset.tables[table.name]
        assert all(str(df[c].dtype) == "string" for c in df.columns), table.name


def test_curated_tables_are_clean(dataset) -> None:
    """Whatever mess lives in the raw feeds must not leak into the curated ones."""
    assert not dataset.trades.duplicated().any()
    assert not dataset.clients.duplicated().any()
    names = dataset.clients["client_name"]
    assert names.str.strip().equals(names)


# --------------------------------------------------------------------------- #
# The nested JSON feed
# --------------------------------------------------------------------------- #


def test_order_feed_is_nested_and_well_formed(dataset) -> None:
    orders = dataset.orders_json
    assert len(orders) == SMALL.n_orders_json
    tickers = set(dataset.securities["ticker"])
    for order in orders:
        assert order["client"]["id"].startswith("C")
        assert 1 <= len(order["legs"]) <= 3
        for leg in order["legs"]:
            assert leg["ticker"] in tickers
            assert leg["quantity"] > 0


# --------------------------------------------------------------------------- #
# Config validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "overrides",
    [
        {"n_securities": 0},
        {"n_securities": 999},
        {"min_tickers_per_client": 9, "max_tickers_per_client": 3},
        {"n_securities": 3, "max_tickers_per_client": 5},
    ],
)
def test_impossible_configs_are_rejected(overrides) -> None:
    with pytest.raises(ValueError):
        GeneratorConfig(**overrides)

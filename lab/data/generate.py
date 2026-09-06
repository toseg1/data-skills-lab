"""Seeded generation of the Northwind Capital dataset.

Everything here is a pure function of ``(seed, config)``. Run it twice with the
same seed and you get byte-identical frames; run it with a different seed and
every number changes. That is what makes the grader work: your dataset is
unique to your clone, so an answer cannot be memorised, shared or hand-computed,
yet the reference implementation sees exactly the data your code sees.

## Independent random streams

Each part of the dataset draws from its own generator, derived from the master
seed and a stable hash of a stream name. Adding a new table later therefore does
not shift the numbers in existing ones — an exercise you solved last week still
grades the same today.

``zlib.crc32`` does the hashing rather than the builtin ``hash``, which is salted
per process and would make the whole dataset non-reproducible across runs.

## Consistency guarantees

Positions are *derived* from trades rather than invented alongside them, so the
two reconcile exactly: cumulative signed quantity per client and ticker equals
the position on any date. Trades are generated sequentially so a client can never
sell more than it holds, which keeps quantities non-negative.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from lab.data import schema
from lab.data.universe import (
    CLIENT_SEGMENTS,
    COUNTRIES,
    NAME_PARTS,
    NAMED_CLIENTS,
    SECURITIES,
)

__all__ = ["Dataset", "GeneratorConfig", "generate_dataset", "stream_rng"]

# Share of each security's variance explained by the market, its sector, and
# itself. Must sum to 1 so realised vol matches the universe's annual_vol.
_W_MARKET, _W_SECTOR, _W_IDIO = 0.45, 0.25, 0.30

_TRADING_DAYS = 252


def stream_rng(seed: int, stream: str) -> np.random.Generator:
    """A generator for one named stream, stable across processes and versions."""
    return np.random.default_rng([seed, zlib.crc32(stream.encode("utf-8"))])


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """Knobs for dataset size. Defaults give roughly 30k prices and 25k trades."""

    n_clients: int = 60
    n_securities: int = len(SECURITIES)
    n_days: int = 756  # three years of business days
    start_date: str = "2023-01-02"
    n_trades: int = 25_000
    min_tickers_per_client: int = 2
    max_tickers_per_client: int = 8
    n_orders_json: int = 200

    # Imperfection rates, applied to the curated tables. These are realistic
    # gaps rather than corruption; see schema.py for the two-layer split.
    price_gap_rate: float = 0.010
    null_close_rate: float = 0.003
    null_commission_rate: float = 0.040
    null_onboard_rate: float = 0.070

    def __post_init__(self) -> None:
        if not 0 < self.n_securities <= len(SECURITIES):
            raise ValueError(f"n_securities must be 1..{len(SECURITIES)}")
        if self.min_tickers_per_client > self.max_tickers_per_client:
            raise ValueError("min_tickers_per_client exceeds max_tickers_per_client")
        if self.max_tickers_per_client > self.n_securities:
            raise ValueError("max_tickers_per_client exceeds the universe size")


@dataclass(frozen=True, slots=True)
class Dataset:
    """The generated tables, plus the seed and config that produced them."""

    seed: int
    config: GeneratorConfig
    clients: pd.DataFrame
    securities: pd.DataFrame
    prices: pd.DataFrame
    trades: pd.DataFrame
    positions: pd.DataFrame
    clients_raw: pd.DataFrame
    trades_raw: pd.DataFrame
    orders_json: list[dict] = field(default_factory=list)

    @property
    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "clients": self.clients,
            "securities": self.securities,
            "prices": self.prices,
            "trades": self.trades,
            "positions": self.positions,
            "clients_raw": self.clients_raw,
            "trades_raw": self.trades_raw,
        }


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #


def _build_securities(config: GeneratorConfig) -> pd.DataFrame:
    rows = [s._asdict() for s in SECURITIES[: config.n_securities]]
    df = pd.DataFrame(rows).drop(columns=["base_price", "annual_vol"])
    return schema.coerce(df, schema.SECURITIES)


def _build_clients(seed: int, config: GeneratorConfig) -> pd.DataFrame:
    rng = stream_rng(seed, "clients")
    first, second, suffix = NAME_PARTS

    names: list[str] = []
    countries: list[str] = []
    segments: list[str] = []

    for name, country, segment in NAMED_CLIENTS[: config.n_clients]:
        names.append(name)
        countries.append(country)
        segments.append(segment)

    # Remaining clients get generated names, kept unique by construction.
    used = set(names)
    while len(names) < config.n_clients:
        candidate = " ".join(
            (
                first[rng.integers(len(first))],
                second[rng.integers(len(second))],
                suffix[rng.integers(len(suffix))],
            )
        )
        if candidate in used:
            continue
        used.add(candidate)
        names.append(candidate)
        countries.append(COUNTRIES[rng.integers(len(COUNTRIES))])
        segments.append(CLIENT_SEGMENTS[rng.integers(len(CLIENT_SEGMENTS))])

    n = config.n_clients
    # AUM is heavily right-skewed: a few very large institutions, a long tail.
    aum = np.round(np.exp(rng.normal(18.6, 1.35, n)), 2)

    onboard_offsets = rng.integers(0, 3_500, n)
    onboard = pd.Timestamp("2015-01-05") + pd.to_timedelta(onboard_offsets, unit="D")
    onboard = pd.Series(onboard)
    missing = rng.random(n) < config.null_onboard_rate
    missing[3] = True  # C004 is documented as missing on the Notion hub page
    onboard[missing] = pd.NaT

    df = pd.DataFrame(
        {
            "client_id": [f"C{i + 1:03d}" for i in range(n)],
            "client_name": names,
            "country": countries,
            "segment": segments,
            "onboard_date": onboard,
            "aum_usd": aum,
        }
    )
    return schema.coerce(df, schema.CLIENTS)


def _simulate_closes(
    seed: int, config: GeneratorConfig, calendar: pd.DatetimeIndex
) -> tuple[np.ndarray, np.ndarray]:
    """Return the (days, securities) close matrix and its daily log returns.

    A three-factor model — market, sector, idiosyncratic — so tickers in the same
    sector correlate. Building correlation this way is always valid, unlike
    inventing a covariance matrix that may not be positive semi-definite.
    """
    rng = stream_rng(seed, "prices")
    secs = SECURITIES[: config.n_securities]
    n_days, n_sec = len(calendar), len(secs)

    sectors = sorted({s.sector for s in secs})
    sector_idx = np.array([sectors.index(s.sector) for s in secs])

    daily_vol = np.array([s.annual_vol for s in secs]) / np.sqrt(_TRADING_DAYS)
    annual_drift = rng.normal(0.06, 0.05, n_sec)

    market = rng.standard_normal(n_days)
    sector = rng.standard_normal((n_days, len(sectors)))
    idio = rng.standard_normal((n_days, n_sec))

    shock = (
        np.sqrt(_W_MARKET) * market[:, None]
        + np.sqrt(_W_SECTOR) * sector[:, sector_idx]
        + np.sqrt(_W_IDIO) * idio
    )
    drift = annual_drift / _TRADING_DAYS - 0.5 * daily_vol**2
    log_ret = drift + daily_vol * shock

    base = np.array([s.base_price for s in secs])
    closes = base * np.exp(np.cumsum(log_ret, axis=0))
    return closes, log_ret


def _build_prices(
    seed: int, config: GeneratorConfig, calendar: pd.DatetimeIndex, closes: np.ndarray
) -> pd.DataFrame:
    rng = stream_rng(seed, "prices_ohlc")
    secs = SECURITIES[: config.n_securities]
    n_days, n_sec = closes.shape

    prev_close = np.vstack([np.array([s.base_price for s in secs]), closes[:-1]])
    open_px = prev_close * (1 + rng.normal(0, 0.002, (n_days, n_sec)))
    upper = np.maximum(open_px, closes)
    lower = np.minimum(open_px, closes)
    high_px = upper * (1 + np.abs(rng.normal(0, 0.004, (n_days, n_sec))))
    low_px = lower * (1 - np.abs(rng.normal(0, 0.004, (n_days, n_sec))))

    volume = np.exp(rng.normal(15.5, 0.8, (n_days, n_sec))).astype(np.int64)

    tickers = [s.ticker for s in secs]
    df = pd.DataFrame(
        {
            "price_date": np.repeat(calendar.values, n_sec),
            "ticker": np.tile(tickers, n_days),
            "open_px": open_px.ravel().round(4),
            "high_px": high_px.ravel().round(4),
            "low_px": low_px.ravel().round(4),
            "close_px": closes.ravel().round(4),
            "volume": volume.ravel(),
        }
    )

    # A stale run: one ticker repeats the same close for several days. Realistic,
    # and exactly what a data-quality exercise should catch. The window scales
    # with the calendar so small test configs stay valid.
    stale_ticker = tickers[rng.integers(n_sec)]
    stale_len = min(5, max(2, n_days // 8))
    margin = min(20, n_days // 6)
    span = max(1, n_days - stale_len - 2 * margin)
    stale_start = margin + int(rng.random() * span)
    stale_rows = df.index[
        (df["ticker"] == stale_ticker)
        & df["price_date"].isin(calendar[stale_start : stale_start + stale_len])
    ]
    if len(stale_rows):
        df.loc[stale_rows, "close_px"] = df.loc[stale_rows[0], "close_px"]
        # Re-widen the bar so it still brackets the frozen close: a stale price
        # is a data-quality problem, an incoherent OHLC bar is a generator bug.
        bar = df.loc[stale_rows, ["open_px", "high_px", "low_px", "close_px"]]
        df.loc[stale_rows, "high_px"] = bar[["high_px", "open_px", "close_px"]].max(axis=1)
        df.loc[stale_rows, "low_px"] = bar[["low_px", "open_px", "close_px"]].min(axis=1)

    # Holiday gaps: whole rows the vendor never sent.
    keep = rng.random(len(df)) >= config.price_gap_rate
    df = df.loc[keep].reset_index(drop=True)

    # Missing prints: the row arrived, the close did not.
    df.loc[rng.random(len(df)) < config.null_close_rate, "close_px"] = np.nan

    df = df.sort_values(["ticker", "price_date"], kind="stable").reset_index(drop=True)
    return schema.coerce(df, schema.PRICES)


def _client_books(
    seed: int, config: GeneratorConfig, n_sec: int
) -> tuple[list[np.ndarray], np.ndarray]:
    """Which tickers each client trades, and how trade volume splits between them."""
    rng = stream_rng(seed, "books")
    books = [
        rng.choice(
            n_sec,
            size=int(
                rng.integers(config.min_tickers_per_client, config.max_tickers_per_client + 1)
            ),
            replace=False,
        )
        for _ in range(config.n_clients)
    ]
    weights = rng.random(config.n_clients) ** 2 + 0.05
    return books, weights / weights.sum()


def _build_trades(
    seed: int,
    config: GeneratorConfig,
    calendar: pd.DatetimeIndex,
    closes: np.ndarray,
    clients: pd.DataFrame,
    books: list[np.ndarray],
    client_weights: np.ndarray,
) -> pd.DataFrame:
    """Generate trades sequentially so a client never sells more than it holds."""
    rng = stream_rng(seed, "trades")
    secs = SECURITIES[: config.n_securities]
    tickers = [s.ticker for s in secs]
    client_ids = clients["client_id"].tolist()

    n = config.n_trades
    client_of = rng.choice(config.n_clients, size=n, p=client_weights)
    day_of = np.sort(rng.integers(0, len(calendar), size=n))
    pick = rng.random(n)
    want_qty = np.maximum(100, (np.exp(rng.normal(8.6, 0.9, n)) // 100 * 100).astype(np.int64))
    sell_draw = rng.random(n)
    px_noise = rng.normal(0, 0.0015, n)
    comm_bps = rng.uniform(2.0, 8.0, n)
    comm_missing = rng.random(n) < config.null_commission_rate

    holdings: dict[tuple[int, int], int] = {}
    rows_c, rows_t, rows_d, rows_side, rows_q = [], [], [], [], []

    for i in range(n):
        c = int(client_of[i])
        book = books[c]
        t = int(book[int(pick[i] * len(book))])
        held = holdings.get((c, t), 0)

        # Sell only what is held; otherwise buy. 38% sell pressure when possible.
        if held > 0 and sell_draw[i] < 0.38:
            qty = int(min(want_qty[i], held) // 100 * 100)
            if qty <= 0:
                side, qty = "BUY", int(want_qty[i])
            else:
                side = "SELL"
        else:
            side, qty = "BUY", int(want_qty[i])

        holdings[(c, t)] = held + (qty if side == "BUY" else -qty)
        rows_c.append(c)
        rows_t.append(t)
        rows_d.append(int(day_of[i]))
        rows_side.append(side)
        rows_q.append(qty)

    day_arr = np.array(rows_d)
    tick_arr = np.array(rows_t)
    price = closes[day_arr, tick_arr] * (1 + px_noise)
    notional = price * np.array(rows_q)
    commission = np.round(notional * comm_bps / 10_000, 2)
    commission[comm_missing] = np.nan

    df = pd.DataFrame(
        {
            "trade_id": [f"T{10_001 + i}" for i in range(n)],
            "trade_date": calendar.values[day_arr],
            "client_id": [client_ids[c] for c in rows_c],
            "ticker": [tickers[t] for t in tick_arr],
            "side": rows_side,
            "quantity": rows_q,
            "price": price.round(4),
            "commission": commission,
        }
    )
    return schema.coerce(df, schema.TRADES)


def _build_positions(
    calendar: pd.DatetimeIndex,
    closes: np.ndarray,
    trades: pd.DataFrame,
    tickers: list[str],
) -> pd.DataFrame:
    """Derive daily holdings from trades, so the two tables reconcile exactly."""
    t = trades.copy()
    t["signed"] = np.where(t["side"] == "BUY", t["quantity"], -t["quantity"])
    t["buy_qty"] = np.where(t["side"] == "BUY", t["quantity"], 0)
    t["buy_notional"] = t["buy_qty"] * t["price"]

    def _matrix(values: str) -> pd.DataFrame:
        grid = (
            t.pivot_table(
                index="trade_date",
                columns=["client_id", "ticker"],
                values=values,
                aggfunc="sum",
                observed=True,
            )
            .reindex(calendar)
            .fillna(0.0)
        )
        return grid.cumsum()

    qty = _matrix("signed")
    cum_buy_qty = _matrix("buy_qty")
    cum_buy_notional = _matrix("buy_notional")

    with np.errstate(invalid="ignore", divide="ignore"):
        avg_cost = cum_buy_notional / cum_buy_qty.replace(0.0, np.nan)

    # A pair only exists from its first trade onwards.
    first_trade = t.groupby(["client_id", "ticker"], observed=True)["trade_date"].min()
    active = pd.DataFrame(
        np.greater_equal.outer(calendar.values, first_trade.reindex(qty.columns).values),
        index=calendar,
        columns=qty.columns,
    )

    close_df = pd.DataFrame(closes, index=calendar, columns=tickers)
    px = close_df.loc[:, [tk for _, tk in qty.columns]]
    px.columns = qty.columns

    long = (
        pd.concat(
            {
                "quantity": qty.where(active),
                "avg_cost": avg_cost.where(active),
                "market_value": (qty * px).where(active),
            },
            axis=1,
        )
        .stack(level=[1, 2], future_stack=True)
        .reset_index()
    )
    long.columns = ["as_of_date", "client_id", "ticker", "quantity", "avg_cost", "market_value"]
    long = long.dropna(subset=["quantity"])

    long["quantity"] = long["quantity"].astype("int64")
    long["avg_cost"] = long["avg_cost"].round(4)
    long["market_value"] = long["market_value"].round(2)
    long = long.sort_values(["as_of_date", "client_id", "ticker"], kind="stable")
    return schema.coerce(long, schema.POSITIONS)


# --------------------------------------------------------------------------- #
# Raw feeds
# --------------------------------------------------------------------------- #


def _build_clients_raw(seed: int, clients: pd.DataFrame) -> pd.DataFrame:
    rng = stream_rng(seed, "clients_raw")
    df = clients.copy()
    n = len(df)

    pad = rng.random(n)
    names = df["client_name"].astype(str)
    names = np.where(pad < 0.20, "  " + names, np.where(pad < 0.35, names + "   ", names))

    case = rng.random(n)
    country = df["country"].astype(str)
    country = np.where(
        case < 0.25, country.str.lower(), np.where(case < 0.4, country.str.title(), country)
    )

    # Two date formats, plus empty strings where the date is genuinely missing.
    iso = df["onboard_date"].dt.strftime("%Y-%m-%d")
    euro = df["onboard_date"].dt.strftime("%d/%m/%Y")
    onboard = np.where(rng.random(n) < 0.3, euro, iso)
    onboard = pd.Series(onboard).where(df["onboard_date"].notna(), "")

    raw = pd.DataFrame(
        {
            "client_id": df["client_id"],
            "client_name": names,
            "country": country,
            "segment": df["segment"],
            "onboard_date": onboard,
            "aum_usd": df["aum_usd"].map(lambda v: f"{v:,.2f}"),
        }
    )
    # The feed repeats a handful of rows.
    dupes = raw.sample(n=max(1, n // 20), random_state=int(rng.integers(1e9)))
    raw = pd.concat([raw, dupes], ignore_index=True)
    return schema.coerce(raw, schema.CLIENTS_RAW)


def _build_trades_raw(seed: int, trades: pd.DataFrame) -> pd.DataFrame:
    rng = stream_rng(seed, "trades_raw")
    df = trades.copy()
    n = len(df)

    iso = df["trade_date"].dt.strftime("%Y-%m-%d")
    euro = df["trade_date"].dt.strftime("%d/%m/%Y")
    trade_date = np.where(rng.random(n) < 0.25, euro, iso)

    side = df["side"].astype(str)
    short = rng.random(n) < 0.15
    side = np.where(short, side.str[0], side)

    ticker = df["ticker"].astype(str)
    ticker = np.where(rng.random(n) < 0.12, ticker.str.lower(), ticker)

    # A few sells arrive as negative quantities instead of a SELL flag.
    qty = df["quantity"].to_numpy().copy()
    flip = (rng.random(n) < 0.01) & (df["side"] == "SELL").to_numpy()
    qty[flip] = -qty[flip]

    raw = pd.DataFrame(
        {
            "trade_id": df["trade_id"],
            "trade_date": trade_date,
            "client_id": df["client_id"],
            "ticker": ticker,
            "side": side,
            "quantity": [str(q) for q in qty],
            "price": df["price"].map(lambda v: f"{v:.4f}"),
            "commission": df["commission"].map(lambda v: "" if pd.isna(v) else f"{v:.2f}"),
        }
    )
    dupes = raw.sample(n=max(1, n // 300), random_state=int(rng.integers(1e9)))
    raw = pd.concat([raw, dupes], ignore_index=True)
    raw = raw.sample(frac=1.0, random_state=int(rng.integers(1e9))).reset_index(drop=True)
    return schema.coerce(raw, schema.TRADES_RAW)


def _build_orders_json(
    seed: int, config: GeneratorConfig, clients: pd.DataFrame, tickers: list[str]
) -> list[dict]:
    """A nested order feed, for the JSON and UNNEST exercises."""
    rng = stream_rng(seed, "orders_json")
    venues = ("XPAR", "XLON", "XETR", "XNYS", "XNAS")
    out = []
    for i in range(config.n_orders_json):
        client = clients.iloc[int(rng.integers(len(clients)))]
        n_legs = int(rng.integers(1, 4))
        out.append(
            {
                "order_id": f"O{i + 1:05d}",
                "received_at": (
                    pd.Timestamp("2025-01-02")
                    + pd.Timedelta(days=int(rng.integers(0, 250)))
                    + pd.Timedelta(minutes=int(rng.integers(0, 480)))
                ).isoformat(),
                "venue": venues[int(rng.integers(len(venues)))],
                "client": {"id": client["client_id"], "name": client["client_name"]},
                "legs": [
                    {
                        "ticker": tickers[int(rng.integers(len(tickers)))],
                        "side": "BUY" if rng.random() < 0.6 else "SELL",
                        "quantity": int(rng.integers(1, 40) * 100),
                        "limit_price": round(float(rng.uniform(20, 700)), 2),
                    }
                    for _ in range(n_legs)
                ],
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def generate_dataset(seed: int, config: GeneratorConfig | None = None) -> Dataset:
    """Build the whole dataset deterministically from ``seed``."""
    config = config or GeneratorConfig()
    calendar = pd.bdate_range(config.start_date, periods=config.n_days)
    tickers = [s.ticker for s in SECURITIES[: config.n_securities]]

    securities = _build_securities(config)
    clients = _build_clients(seed, config)
    closes, _ = _simulate_closes(seed, config, calendar)
    prices = _build_prices(seed, config, calendar, closes)

    books, weights = _client_books(seed, config, config.n_securities)
    trades = _build_trades(seed, config, calendar, closes, clients, books, weights)
    positions = _build_positions(calendar, closes, trades, tickers)

    return Dataset(
        seed=seed,
        config=config,
        clients=clients,
        securities=securities,
        prices=prices,
        trades=trades,
        positions=positions,
        clients_raw=_build_clients_raw(seed, clients),
        trades_raw=_build_trades_raw(seed, trades),
        orders_json=_build_orders_json(seed, config, clients, tickers),
    )

"""Static reference data: the tradable universe and client name components.

This is the only part of the dataset that does *not* vary with the seed. Keeping
the instrument list fixed means exercises can refer to a ticker by name, and the
API track can fetch the same symbols from Yahoo Finance and compare them against
the synthetic series.

``base_price`` and ``annual_vol`` seed the price simulation; they are plausible
rather than accurate, and every path generated from them is fictional.
"""

from __future__ import annotations

from typing import NamedTuple

__all__ = ["CLIENT_SEGMENTS", "COUNTRIES", "NAMED_CLIENTS", "SECURITIES", "Security"]


class Security(NamedTuple):
    ticker: str
    security_name: str
    sector: str
    exchange: str
    currency: str
    base_price: float
    annual_vol: float


#: 40 instruments across eight sectors. Sector membership drives the correlation
#: structure in the price simulation, so the groupings need to be sensible.
SECURITIES: tuple[Security, ...] = (
    # Technology
    Security("AAPL", "Apple Inc.", "Technology", "NASDAQ", "USD", 241.35, 0.26),
    Security("MSFT", "Microsoft Corp.", "Technology", "NASDAQ", "USD", 412.75, 0.24),
    Security("NVDA", "NVIDIA Corp.", "Technology", "NASDAQ", "USD", 132.40, 0.48),
    Security("AVGO", "Broadcom Inc.", "Technology", "NASDAQ", "USD", 178.90, 0.35),
    Security("ORCL", "Oracle Corp.", "Technology", "NYSE", "USD", 168.20, 0.28),
    Security("CRM", "Salesforce Inc.", "Technology", "NYSE", "USD", 289.60, 0.31),
    Security("ADBE", "Adobe Inc.", "Technology", "NASDAQ", "USD", 512.30, 0.30),
    Security("AMD", "Advanced Micro Devices", "Technology", "NASDAQ", "USD", 141.85, 0.45),
    # Financials
    Security("JPM", "JPMorgan Chase & Co.", "Financials", "NYSE", "USD", 248.10, 0.22),
    Security("BAC", "Bank of America Corp.", "Financials", "NYSE", "USD", 45.20, 0.25),
    Security("GS", "Goldman Sachs Group", "Financials", "NYSE", "USD", 578.40, 0.24),
    Security("MS", "Morgan Stanley", "Financials", "NYSE", "USD", 128.75, 0.26),
    Security("AXP", "American Express Co.", "Financials", "NYSE", "USD", 296.50, 0.23),
    # Healthcare
    Security("JNJ", "Johnson & Johnson", "Healthcare", "NYSE", "USD", 152.80, 0.16),
    Security("PFE", "Pfizer Inc.", "Healthcare", "NYSE", "USD", 26.40, 0.22),
    Security("LLY", "Eli Lilly & Co.", "Healthcare", "NYSE", "USD", 782.10, 0.29),
    Security("MRK", "Merck & Co.", "Healthcare", "NYSE", "USD", 99.30, 0.19),
    Security("ABBV", "AbbVie Inc.", "Healthcare", "NYSE", "USD", 176.55, 0.20),
    # Energy
    Security("XOM", "Exxon Mobil Corp.", "Energy", "NYSE", "USD", 118.60, 0.24),
    Security("CVX", "Chevron Corp.", "Energy", "NYSE", "USD", 158.30, 0.23),
    Security("TTE", "TotalEnergies SE", "Energy", "EPA", "EUR", 58.90, 0.25),
    Security("SHEL", "Shell plc", "Energy", "LSE", "GBP", 28.45, 0.24),
    Security("BP", "BP plc", "Energy", "LSE", "GBP", 4.05, 0.28),
    # Consumer Staples
    Security("PG", "Procter & Gamble Co.", "Staples", "NYSE", "USD", 168.90, 0.15),
    Security("KO", "Coca-Cola Co.", "Staples", "NYSE", "USD", 62.80, 0.16),
    Security("PEP", "PepsiCo Inc.", "Staples", "NASDAQ", "USD", 152.40, 0.16),
    Security("NESN", "Nestle SA", "Staples", "SIX", "CHF", 84.20, 0.17),
    Security("UL", "Unilever plc", "Staples", "LSE", "GBP", 46.75, 0.18),
    # Industrials
    Security("CAT", "Caterpillar Inc.", "Industrials", "NYSE", "USD", 386.20, 0.26),
    Security("BA", "Boeing Co.", "Industrials", "NYSE", "USD", 178.40, 0.38),
    Security("HON", "Honeywell International", "Industrials", "NASDAQ", "USD", 224.60, 0.20),
    Security("SIE", "Siemens AG", "Industrials", "ETR", "EUR", 189.30, 0.23),
    Security("AIR", "Airbus SE", "Industrials", "EPA", "EUR", 162.80, 0.25),
    # Consumer Discretionary
    Security("AMZN", "Amazon.com Inc.", "Discretionary", "NASDAQ", "USD", 224.90, 0.30),
    Security("TSLA", "Tesla Inc.", "Discretionary", "NASDAQ", "USD", 352.60, 0.55),
    Security("HD", "Home Depot Inc.", "Discretionary", "NYSE", "USD", 412.30, 0.21),
    Security("MC", "LVMH SE", "Discretionary", "EPA", "EUR", 648.50, 0.27),
    Security("NKE", "Nike Inc.", "Discretionary", "NYSE", "USD", 76.90, 0.28),
    # Communication
    Security("GOOGL", "Alphabet Inc.", "Communication", "NASDAQ", "USD", 191.20, 0.27),
    Security("META", "Meta Platforms Inc.", "Communication", "NASDAQ", "USD", 604.80, 0.33),
)

#: The five clients quoted on the Notion hub page, pinned so the reference
#: material and the generated data agree. Remaining clients are generated.
NAMED_CLIENTS: tuple[tuple[str, str, str], ...] = (
    ("Aurora Pension Fund", "FR", "Institutional"),
    ("Beaumont Family Office", "FR", "Private"),
    ("Castellan Insurance", "DE", "Institutional"),
    ("Delacroix Wealth", "CH", "Private"),
    ("Eurofin Asset Mgmt", "LU", "Wholesale"),
)

COUNTRIES: tuple[str, ...] = ("FR", "DE", "CH", "LU", "GB", "NL", "IT", "ES", "BE", "IE")

CLIENT_SEGMENTS: tuple[str, ...] = ("Institutional", "Private", "Wholesale")

#: Name parts for generated clients: "<first> <second> <suffix>".
_FIRST = (
    "Adelphi",
    "Belvedere",
    "Cascadia",
    "Drakemoor",
    "Ellesmere",
    "Fairhaven",
    "Granville",
    "Halcyon",
    "Ironbridge",
    "Jardine",
    "Kingsmere",
    "Lauriston",
    "Marchmont",
    "Northgate",
    "Osterley",
    "Pemberton",
    "Quayside",
    "Rothsay",
    "Stonebridge",
    "Thornbury",
    "Ullswater",
    "Verity",
    "Westmark",
    "Yarrow",
)
_SECOND = ("Capital", "Partners", "Asset", "Wealth", "Investment", "Financial", "Global")
_SUFFIX = ("Management", "Advisors", "Group", "Holdings", "Trust", "Fund", "LLP", "SA")

NAME_PARTS: tuple[tuple[str, ...], ...] = (_FIRST, _SECOND, _SUFFIX)

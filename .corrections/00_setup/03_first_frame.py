"""Reference · Setup 03"""


def solve(trades, securities):
    enriched = trades.merge(securities[["ticker", "sector"]], on="ticker", how="left")
    enriched["notional"] = enriched["quantity"] * enriched["price"]
    return enriched.groupby("sector", as_index=False)["notional"].sum()

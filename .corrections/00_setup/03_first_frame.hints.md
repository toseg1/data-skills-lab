Three steps: bring `sector` onto the trades, work out the notional, then total it per sector.

---

`trades.merge(securities, on="ticker", how="left")` joins the two. You only need `ticker` and `sector` from `securities`, so select those first to avoid dragging in columns you do not want.

For the total, `groupby("sector", as_index=False)["notional"].sum()` gives you a DataFrame with `sector` as a column rather than an index — which is what the task asked for.

---

    enriched = trades.merge(securities[["ticker", "sector"]], on="ticker", how="left")
    enriched["notional"] = enriched["quantity"] * enriched["price"]
    return enriched.groupby("sector", as_index=False)["notional"].sum()

Without `as_index=False` you get `sector` as the index instead of a column, and the grader would tell you a column was missing.

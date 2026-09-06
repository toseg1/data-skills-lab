Four clauses, in this order: pick the columns, group by ticker, sort, then limit.

---

`SUM(quantity * price)` is the notional. Alias it with `AS notional` so the column name matches what the task asked for.

`ORDER BY` has to come before `LIMIT`, and you want `DESC` for "largest first".

---

    SELECT ticker, SUM(quantity * price) AS notional
    FROM trades
    GROUP BY ticker
    ORDER BY notional DESC
    LIMIT 5

DuckDB would also accept `GROUP BY ALL` here, which saves listing the key columns.

-- Reference · Setup 02
SELECT
    ticker,
    SUM(quantity * price) AS notional
FROM trades
GROUP BY ticker
ORDER BY notional DESC
LIMIT 5

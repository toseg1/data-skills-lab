`trades` is an ordinary pandas DataFrame. How do you ask any Python container how many things are in it?

---

`len(df)` gives the row count. `df.shape` gives `(rows, columns)` if you want both.

---

    return len(trades)

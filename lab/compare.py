"""Comparing your answer against the reference.

The feedback here is the product. A bare "expected X, got Y" on a 200-row frame
teaches nothing, so this module works out *how* two results differ — wrong shape,
wrong columns, right rows in the wrong order, close-but-not-equal floats — and
says so in those terms.

Deliberate leniency, so you fail for real mistakes rather than cosmetic ones:

* the index is ignored; it is an artefact of how you got there, not the answer
* column *order* is ignored, though column *names* must match
* row order is ignored unless the exercise says otherwise (a `TOP 5` question
  sets ``ordered``)
* ints and floats compare equal when their values are, and floats compare within
  a tolerance, because ``0.1 + 0.2`` is not a bug worth failing someone over
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

__all__ = ["Comparison", "compare", "describe"]

MAX_SAMPLE_ROWS = 6


@dataclass
class Comparison:
    ok: bool
    headline: str
    details: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @classmethod
    def passed(cls, headline: str = "Correct", notes: list[str] | None = None) -> Comparison:
        return cls(True, headline, notes=notes or [])

    @classmethod
    def failed(
        cls, headline: str, details: list[str] | None = None, notes: list[str] | None = None
    ) -> Comparison:
        return cls(False, headline, details or [], notes or [])


def describe(value: Any) -> str:
    """A short human description of what something is."""
    if isinstance(value, pd.DataFrame):
        return f"DataFrame {value.shape[0]} x {value.shape[1]}"
    if isinstance(value, pd.Series):
        return f"Series of {len(value)}"
    if isinstance(value, np.ndarray):
        return f"ndarray {value.shape}"
    if value is None:
        return "None"
    return f"{type(value).__name__} ({value!r})" if not _is_long(value) else type(value).__name__


def _is_long(value: Any) -> bool:
    try:
        return len(repr(value)) > 60
    except TypeError:
        return False


def _is_numeric(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)


def _values_equal(left: pd.Series, right: pd.Series, rtol: float, atol: float) -> pd.Series:
    """Elementwise equality with null-aware and float-tolerant semantics."""
    both_null = left.isna().to_numpy() & right.isna().to_numpy()

    if _is_numeric(left) and _is_numeric(right):
        close = np.isclose(
            pd.to_numeric(left, errors="coerce").astype("float64").to_numpy(),
            pd.to_numeric(right, errors="coerce").astype("float64").to_numpy(),
            rtol=rtol,
            atol=atol,
            equal_nan=True,
        )
        return pd.Series(close | both_null)

    if _is_numeric(left) != _is_numeric(right):
        # One side is text where the other is a number: never equal, and worth
        # saying so rather than showing a confusing value diff.
        return pd.Series(both_null)

    same = (left.astype("object").to_numpy() == right.astype("object").to_numpy()) | both_null
    return pd.Series(same)


def _normalise(df: pd.DataFrame, *, ordered: bool) -> tuple[pd.DataFrame, bool]:
    out = df.reset_index(drop=True)
    if ordered:
        return out, True
    try:
        out = out.sort_values(by=list(out.columns), kind="stable", na_position="last")
    except TypeError:
        # Unsortable column (a list or dict in a cell); fall back to given order.
        return out.reset_index(drop=True), False
    return out.reset_index(drop=True), True


def _format_float(value: float) -> str:
    """Readable in a terminal: no scientific notation on money, no lost precision
    on returns. Both sides of a diff use this, so columns line up."""
    if value != value:  # NaN
        return "NaN"
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.2f}"
    if magnitude == 0:
        return "0"
    return f"{value:,.6g}"


def _frame_sample(df: pd.DataFrame, rows: pd.Index) -> str:
    return df.loc[rows].to_string(max_cols=12, max_colwidth=24, float_format=_format_float)


def _compare_frame(
    actual: Any, expected: pd.DataFrame, *, ordered: bool, rtol: float, atol: float
) -> Comparison:
    if isinstance(actual, pd.Series):
        return Comparison.failed(
            f"Expected a DataFrame, got a {describe(actual)}",
            notes=["If you have a Series, `.to_frame()` or `.reset_index()` may be what you want."],
        )
    if not isinstance(actual, pd.DataFrame):
        return Comparison.failed(f"Expected a DataFrame, got {describe(actual)}")

    notes: list[str] = []

    expected_cols, actual_cols = list(expected.columns), list(actual.columns)
    missing = [c for c in expected_cols if c not in actual_cols]
    extra = [c for c in actual_cols if c not in expected_cols]
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing columns: {missing}")
        if extra:
            details.append(f"unexpected columns: {extra}")
        details.append(f"expected columns: {expected_cols}")
        details.append(f"your columns:     {actual_cols}")
        return Comparison.failed("Wrong columns", details)

    if actual_cols != expected_cols:
        notes.append("Column order differs from the reference; that is fine, values are compared.")
        actual = actual.loc[:, expected_cols]

    left, sorted_ok = _normalise(actual, ordered=ordered)
    right, _ = _normalise(expected, ordered=ordered)
    if not ordered and not sorted_ok:
        notes.append("A column could not be sorted, so rows were compared in the order given.")

    if len(left) != len(right):
        return Comparison.failed(
            f"Wrong number of rows: expected {len(right)}, got {len(left)}",
            [
                "first rows expected:",
                _frame_sample(right, right.index[:MAX_SAMPLE_ROWS]),
                "first rows yours:",
                _frame_sample(left, left.index[:MAX_SAMPLE_ROWS]),
            ],
            notes,
        )

    if left.empty:
        return Comparison.passed("Correct (both empty)", notes)

    mismatched = pd.Series(False, index=left.index)
    bad_columns: list[str] = []
    for column in expected_cols:
        equal = _values_equal(left[column], right[column], rtol, atol).to_numpy()
        if not equal.all():
            bad_columns.append(column)
            mismatched |= ~equal

    if not bad_columns:
        return Comparison.passed(notes=notes)

    rows = mismatched[mismatched].index[:MAX_SAMPLE_ROWS]
    total_bad = int(mismatched.sum())
    label = "row" if total_bad == 1 else "rows"
    details = [
        f"{total_bad} {label} differ, in column(s): {bad_columns}",
        f"expected (showing {len(rows)}):",
        _frame_sample(right[expected_cols], rows),
        "yours:",
        _frame_sample(left[expected_cols], rows),
    ]
    if not ordered:
        details.append("Row order was ignored, so these are genuinely different values.")
    return Comparison.failed("Values differ", details, notes)


def _compare_series(
    actual: Any, expected: pd.Series, *, ordered: bool, rtol: float, atol: float
) -> Comparison:
    if isinstance(actual, pd.DataFrame) and actual.shape[1] == 1:
        actual = actual.iloc[:, 0]
    if not isinstance(actual, pd.Series):
        return Comparison.failed(f"Expected a Series, got {describe(actual)}")

    name = expected.name or "value"
    result = _compare_frame(
        actual.rename(name).to_frame(),
        expected.rename(name).to_frame(),
        ordered=ordered,
        rtol=rtol,
        atol=atol,
    )
    return result


def _compare_array(actual: Any, expected: np.ndarray, *, rtol: float, atol: float) -> Comparison:
    if isinstance(actual, list | tuple):
        actual = np.asarray(actual)
    if not isinstance(actual, np.ndarray):
        return Comparison.failed(f"Expected an ndarray, got {describe(actual)}")

    if actual.shape != expected.shape:
        return Comparison.failed(
            f"Wrong shape: expected {expected.shape}, got {actual.shape}",
            notes=["`reshape` or an extra axis via `np.newaxis` is often the fix."],
        )

    if expected.dtype.kind in "fciu" and actual.dtype.kind in "fciu":
        equal = np.isclose(
            actual.astype("float64"),
            expected.astype("float64"),
            rtol=rtol,
            atol=atol,
            equal_nan=True,
        )
    else:
        equal = actual == expected

    if bool(np.all(equal)):
        return Comparison.passed()

    bad = np.argwhere(~equal)
    shown = bad[:MAX_SAMPLE_ROWS]
    lines = [f"{len(bad)} of {equal.size} values differ. First few:"]
    lines += [
        f"  at {tuple(int(i) for i in idx)}: expected {expected[tuple(idx)]!r}, "
        f"got {actual[tuple(idx)]!r}"
        for idx in shown
    ]
    return Comparison.failed("Values differ", lines)


def _compare_scalar(actual: Any, expected: Any, *, rtol: float, atol: float) -> Comparison:
    if isinstance(expected, bool) or isinstance(actual, bool):
        if bool(actual) == bool(expected) and type(actual) is type(expected):
            return Comparison.passed()
        return Comparison.failed(f"Expected {expected!r}, got {actual!r}")

    if isinstance(expected, int | float | np.number) and isinstance(
        actual, int | float | np.number
    ):
        if bool(np.isclose(float(actual), float(expected), rtol=rtol, atol=atol, equal_nan=True)):
            return Comparison.passed()
        return Comparison.failed(f"Expected {expected!r}, got {actual!r}")

    if actual == expected:
        return Comparison.passed()
    return Comparison.failed(
        f"Expected {describe(expected)}, got {describe(actual)}",
        [f"expected: {expected!r}", f"yours:    {actual!r}"],
    )


def compare(
    actual: Any,
    expected: Any,
    *,
    ordered: bool = False,
    rtol: float = 1e-7,
    atol: float = 1e-9,
) -> Comparison:
    """Compare a submitted answer against the reference answer."""
    if actual is None and expected is not None:
        return Comparison.failed(
            "Nothing returned",
            notes=["Did you forget the `return`, or leave the `raise NotImplementedError`?"],
        )

    if isinstance(expected, pd.DataFrame):
        return _compare_frame(actual, expected, ordered=ordered, rtol=rtol, atol=atol)
    if isinstance(expected, pd.Series):
        return _compare_series(actual, expected, ordered=ordered, rtol=rtol, atol=atol)
    if isinstance(expected, np.ndarray):
        return _compare_array(actual, expected, rtol=rtol, atol=atol)
    return _compare_scalar(actual, expected, rtol=rtol, atol=atol)

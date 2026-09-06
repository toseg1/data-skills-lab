"""The comparator decides whether an answer is right, and how to explain it.

Its leniency is deliberate and load-bearing, so each allowance is pinned here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lab.compare import compare


def frame(**columns) -> pd.DataFrame:
    return pd.DataFrame(columns)


# --------------------------------------------------------------------------- #
# What must pass
# --------------------------------------------------------------------------- #


def test_identical_frames_pass() -> None:
    df = frame(a=[1, 2, 3], b=["x", "y", "z"])
    assert compare(df.copy(), df).ok


def test_index_is_ignored() -> None:
    expected = frame(a=[1, 2, 3])
    actual = expected.copy()
    actual.index = [10, 20, 30]
    assert compare(actual, expected).ok


def test_row_order_is_ignored_by_default() -> None:
    expected = frame(a=[1, 2, 3], b=["x", "y", "z"])
    actual = expected.iloc[::-1]
    assert compare(actual, expected).ok


def test_row_order_matters_when_the_exercise_says_so() -> None:
    expected = frame(a=[1, 2, 3])
    actual = expected.iloc[::-1]
    assert not compare(actual, expected, ordered=True).ok


def test_column_order_is_ignored_but_noted() -> None:
    expected = frame(a=[1, 2], b=[3, 4])
    actual = expected.loc[:, ["b", "a"]]
    result = compare(actual, expected)
    assert result.ok
    assert any("order" in note.lower() for note in result.notes)


def test_int_and_float_compare_by_value() -> None:
    assert compare(frame(a=[1.0, 2.0]), frame(a=[1, 2])).ok


def test_floats_compare_within_tolerance() -> None:
    assert compare(frame(a=[0.1 + 0.2]), frame(a=[0.3])).ok


def test_nulls_match_nulls() -> None:
    expected = frame(a=[1.0, np.nan])
    assert compare(expected.copy(), expected).ok


def test_empty_frames_match() -> None:
    empty = frame(a=pd.Series(dtype="int64"))
    assert compare(empty.copy(), empty).ok


def test_a_single_column_frame_is_accepted_for_a_series() -> None:
    expected = pd.Series([1, 2, 3], name="a")
    assert compare(expected.to_frame(), expected).ok


# --------------------------------------------------------------------------- #
# What must fail, and how it is explained
# --------------------------------------------------------------------------- #


def test_missing_column_is_named() -> None:
    result = compare(frame(a=[1]), frame(a=[1], b=[2]))
    assert not result.ok
    assert "Wrong columns" in result.headline
    assert any("missing columns" in d and "b" in d for d in result.details)


def test_extra_column_is_named() -> None:
    result = compare(frame(a=[1], b=[2]), frame(a=[1]))
    assert not result.ok
    assert any("unexpected columns" in d for d in result.details)


def test_row_count_mismatch_reports_both_counts() -> None:
    result = compare(frame(a=[1, 2]), frame(a=[1, 2, 3]))
    assert not result.ok
    assert "expected 3, got 2" in result.headline


def test_value_difference_names_the_column_and_shows_rows() -> None:
    expected = frame(k=["a", "b", "c"], v=[1, 2, 3])
    actual = frame(k=["a", "b", "c"], v=[1, 99, 3])
    result = compare(actual, expected)
    assert not result.ok
    assert result.headline == "Values differ"
    assert any("'v'" in d or '"v"' in d for d in result.details)
    assert any("99" in d for d in result.details)


def test_text_where_a_number_was_expected_fails() -> None:
    assert not compare(frame(a=["1", "2"]), frame(a=[1, 2])).ok


def test_returning_nothing_is_called_out_kindly() -> None:
    result = compare(None, frame(a=[1]))
    assert not result.ok
    assert "Nothing returned" in result.headline
    assert any("return" in note for note in result.notes)


def test_series_where_a_frame_was_expected_suggests_the_fix() -> None:
    result = compare(pd.Series([1, 2]), frame(a=[1, 2], b=[3, 4]))
    assert not result.ok
    assert any("to_frame" in note for note in result.notes)


# --------------------------------------------------------------------------- #
# Arrays and scalars
# --------------------------------------------------------------------------- #


def test_arrays_compare_by_value_within_tolerance() -> None:
    assert compare(np.array([1.0, 2.0000000001]), np.array([1.0, 2.0])).ok


def test_array_shape_mismatch_suggests_reshape() -> None:
    result = compare(np.zeros((3, 1)), np.zeros(3))
    assert not result.ok
    assert "Wrong shape" in result.headline
    assert any("reshape" in note for note in result.notes)


def test_array_value_mismatch_points_at_the_index() -> None:
    result = compare(np.array([1, 2, 9]), np.array([1, 2, 3]))
    assert not result.ok
    assert any("at (2,)" in d for d in result.details)


def test_a_list_is_accepted_for_an_array() -> None:
    assert compare([1, 2, 3], np.array([1, 2, 3])).ok


@pytest.mark.parametrize(
    ("actual", "expected", "ok"),
    [
        (42, 42, True),
        (42.0, 42, True),
        (41, 42, False),
        ("BUY", "BUY", True),
        ("SELL", "BUY", False),
        (True, True, True),
        (True, 1, False),
    ],
)
def test_scalars(actual, expected, ok) -> None:
    assert compare(actual, expected).ok is ok


def test_scalar_mismatch_shows_both_values() -> None:
    result = compare(41, 42)
    assert "42" in result.headline and "41" in result.headline

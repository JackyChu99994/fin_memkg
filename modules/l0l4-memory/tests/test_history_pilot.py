"""Historical outcomes must preserve the predeclared benchmark calendar."""
import pandas as pd
import pytest

from experiments.history_pilot import outcome


def prices():
    return pd.DataFrame({"date": ["2024-10-25", "2024-10-28", "2024-10-29", "2024-10-30", "2024-10-31", "2024-11-01", "2024-11-04"],
                         "close": [90., 100., 101., 102., 103., 104., 110.]})


def test_weekend_and_five_intervals():
    stock = prices()
    benchmark = prices().assign(close=100.)
    result = outcome(stock, benchmark, "2024-10-25")
    assert result["entry_date"] == "2024-10-28"
    assert result["exit_date"] == "2024-11-04"
    assert result["arithmetic_excess_return"] == pytest.approx(.1)


def test_missing_stock_bar_does_not_silently_shift_window():
    with pytest.raises(ValueError, match="Missing stock"):
        outcome(prices().drop(index=3), prices(), "2024-10-25")


def test_incomplete_window_is_rejected():
    with pytest.raises(ValueError, match="Incomplete"):
        outcome(prices().iloc[:-1], prices().iloc[:-1], "2024-10-25")


def test_duplicate_dates_and_invalid_prices_are_rejected():
    frame = prices()
    with pytest.raises(ValueError, match="Duplicate"):
        outcome(pd.concat([frame, frame.iloc[:1]]), frame, "2024-10-25")
    with pytest.raises(ValueError, match="Invalid"):
        outcome(frame.assign(close=0.), frame, "2024-10-25")
